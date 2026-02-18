from __future__ import annotations

from typing import List

from pydantic import ValidationError

from app.schemas.ai_trading_manager import MonitorJob


def validate_monitor_job(job: MonitorJob) -> List[str]:
    errors: List[str] = []
    if not job.symbols:
        errors.append("SYMBOLS_REQUIRED")
    if job.cadence_sec <= 0:
        errors.append("CADENCE_MUST_BE_POSITIVE")
    return errors


def validate_monitor_job_payload(payload: dict) -> MonitorJob:
    try:
        job = MonitorJob.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    errs = validate_monitor_job(job)
    if errs:
        raise ValueError(",".join(errs))
    return job

