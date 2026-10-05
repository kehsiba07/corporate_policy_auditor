import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from app.schemas import ErrorMessage, LogMessage, ReportMessage


@dataclass
class Job:
    id: str
    filename: str
    status: str = "queued"  # queued | running | done | error
    messages: list = field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    subscribers: list = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return self.status in ("done", "error")


class JobStore:
    MAX_JOBS = 200

    def __init__(self):
        self._jobs: dict[str, Job] = {}

    def create(self, job_id: str, filename: str) -> Job:
        self._evict()
        job = Job(id=job_id, filename=filename)
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def _evict(self):
        if len(self._jobs) < self.MAX_JOBS:
            return
        finished = sorted(
            (j for j in self._jobs.values() if j.finished), key=lambda j: j.created_at
        )
        for job in finished[: max(1, len(self._jobs) - self.MAX_JOBS + 1)]:
            self._jobs.pop(job.id, None)

    def _publish(self, job: Job, message: dict):
        job.messages.append(message)
        for q in job.subscribers:
            q.put_nowait(message)

    def _close(self, job: Job):
        for q in job.subscribers:
            q.put_nowait(None)

    def set_status(self, job_id: str, status: str):
        job = self._jobs[job_id]
        job.status = status

    def log(self, job_id: str, message: str):
        job = self._jobs[job_id]
        self._publish(job, LogMessage(message=message).model_dump())

    def set_result(self, job_id: str, result: dict):
        job = self._jobs[job_id]
        job.result = result
        job.status = "done"
        self._publish(job, ReportMessage(report=result).model_dump(mode="json"))
        self._close(job)

    def set_error(self, job_id: str, message: str):
        job = self._jobs[job_id]
        job.error = message
        job.status = "error"
        self._publish(job, ErrorMessage(message=message).model_dump())
        self._close(job)

    def subscribe(self, job_id: str):
        """Returns (backlog, queue). queue is None if the job already finished."""
        job = self._jobs[job_id]
        backlog = list(job.messages)
        if job.finished:
            return backlog, None
        queue: asyncio.Queue = asyncio.Queue()
        job.subscribers.append(queue)
        return backlog, queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue):
        job = self._jobs.get(job_id)
        if job and queue in job.subscribers:
            job.subscribers.remove(queue)


store = JobStore()