from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ReportJobState(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"
    NOT_FOUND = "not_found"


class ReportJobAccepted(BaseModel):
    job_id: str
    status: ReportJobState


class ReportJobStatus(BaseModel):
    job_id: str
    status: ReportJobState
