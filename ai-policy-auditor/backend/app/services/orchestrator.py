import asyncio
import logging
import os

from app import db
from app.jobs import JobStore
from app.schemas import AuditResult
from app.services import PipelineError
from app.services.extraction import extract_knowledge
from app.services.ingestion import extract_text_from_pdf
from app.services.logic_engine import verify_compliance_fol
from app.services.reporting import generate_report
from app.services.risk import rank_violations

logger = logging.getLogger(__name__)


async def run_audit_pipeline(job_id: str, file_path: str, store: JobStore):
    """Runs the full pipeline as a background job and writes progress to the job store."""

    def log(message: str):
        store.log(job_id, message)

    job = store.get(job_id)
    store.set_status(job_id, "running")

    try:
        log("[1/5] Starting document ingestion & OCR...")
        text = await asyncio.to_thread(extract_text_from_pdf, file_path)
        log(f"Extracted {len(text):,} characters from the PDF.")

        log("[2/5] Extracting rules and facts using LLM agent...")
        knowledge = await extract_knowledge(text, log=log)
        p_count = len(knowledge["policies"])
        t_count = len(knowledge["transactions"])
        log(f"Verified {p_count} policies and {t_count} transactions against source text.")
        for w in knowledge.get("warnings", []):
            log(f"Warning: {w}")

        log("[3/5] Running formal verification (Z3 first-order logic)...")
        verification = await asyncio.to_thread(verify_compliance_fol, knowledge)
        log(
            f"Z3 completed: {len(verification['violations'])} violation(s), "
            f"{len(verification['conflicts'])} policy conflict(s)."
        )

        log("[4/5] Scoring and ranking risks...")
        ranked = rank_violations(verification["violations"])

        log("[5/5] Generating report...")
        warnings = knowledge.get("warnings", []) + verification["warnings"]
        if p_count == 0:
            warnings.append("No policies were extracted, so no compliance checks could run.")
        report_md = await generate_report(ranked, verification["conflicts"], warnings)

        result = AuditResult(
            report_markdown=report_md,
            violations=ranked,
            conflicts=verification["conflicts"],
            warnings=warnings,
            policy_count=p_count,
            transaction_count=t_count,
        ).model_dump(mode="json")

        try:
            await asyncio.to_thread(db.save_audit, job_id, job.filename if job else "", result)
        except Exception:
            logger.exception("Could not persist audit %s", job_id)

        log("Audit pipeline completed successfully.")
        store.set_result(job_id, result)

    except PipelineError as exc:
        logger.warning("Job %s failed: %s", job_id, exc)
        store.set_error(job_id, str(exc))
    except Exception:
        logger.exception("Job %s failed unexpectedly", job_id)
        store.set_error(job_id, "The audit failed due to an internal error.")