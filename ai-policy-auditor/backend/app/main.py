import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.config import get_settings
from app.jobs import store
from app.schemas import ErrorMessage
from app.services.orchestrator import run_audit_pipeline

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()
UPLOAD_DIR = Path(settings.upload_dir)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_background_tasks: set = set()
_rate_log: dict = defaultdict(deque)


def _sweep_old_uploads(max_age_seconds: int = 3600):
    now = time.time()
    for f in UPLOAD_DIR.glob("*.pdf"):
        try:
            if now - f.stat().st_mtime > max_age_seconds:
                f.unlink()
        except OSError:
            logger.warning("Could not delete stale upload %s", f)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    _sweep_old_uploads()
    yield


app = FastAPI(title="AI Corporate Policy Auditor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _check_rate_limit(client_ip: str):
    now = time.time()
    window = _rate_log[client_ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= settings.rate_limit_per_min:
        raise HTTPException(status_code=429, detail="Too many audit requests. Try again shortly.")
    window.append(now)


async def _run_and_cleanup(job_id: str, file_path: Path):
    try:
        await run_audit_pipeline(job_id, str(file_path), store)
    finally:
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete %s", file_path)


@app.post("/api/audit")
async def start_audit(request: Request, file: UploadFile = File(...)):
    """Validates and saves the PDF, then starts the audit as a background task."""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    filename = file.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Invalid content type. Upload a PDF.")

    job_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{job_id}.pdf"
    max_bytes = settings.max_upload_mb * 1024 * 1024
    size = 0
    first_chunk = True

    try:
        with open(file_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                if first_chunk:
                    if not chunk.startswith(b"%PDF-"):
                        raise HTTPException(status_code=400, detail="File is not a valid PDF.")
                    first_chunk = False
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the {settings.max_upload_mb} MB limit.",
                    )
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    except HTTPException:
        file_path.unlink(missing_ok=True)
        raise
    except Exception:
        file_path.unlink(missing_ok=True)
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail="Upload failed.")

    store.create(job_id, filename)
    task = asyncio.create_task(_run_and_cleanup(job_id, file_path))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {"job_id": job_id, "filename": filename, "status": "queued"}


@app.get("/api/audit/{job_id}/status")
async def audit_status(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"job_id": job.id, "status": job.status, "error": job.error}


@app.get("/api/audit/{job_id}/result")
async def audit_result(job_id: str):
    job = store.get(job_id)
    if job is not None:
        if job.result is None:
            raise HTTPException(status_code=409, detail=f"Job is {job.status}.")
        return job.result
    stored = await asyncio.to_thread(db.get_audit, job_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return stored


@app.get("/api/audits")
async def audit_history():
    return await asyncio.to_thread(db.list_audits)


@app.websocket("/ws/audit/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """Subscribes to a job. Replays backlog, then streams live messages."""
    origin = websocket.headers.get("origin")
    if origin and origin not in settings.allowed_origins:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    if store.get(job_id) is None:
        await websocket.send_json(ErrorMessage(message="Job not found.").model_dump())
        await websocket.close(code=1008)
        return

    backlog, queue = store.subscribe(job_id)
    try:
        for msg in backlog:
            await websocket.send_json(msg)
        if queue is not None:
            while True:
                msg = await queue.get()
                if msg is None:
                    break
                await websocket.send_json(msg)
        await websocket.close()
    except WebSocketDisconnect:
        logger.info("Client disconnected from job %s", job_id)
    except RuntimeError:
        logger.info("Socket already closed for job %s", job_id)
    finally:
        if queue is not None:
            store.unsubscribe(job_id, queue)