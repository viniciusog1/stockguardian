"""Unit: mapeamento de JobStatus do ARQ -> ReportJobState."""

from __future__ import annotations

import pytest
from app.schemas.report_job import ReportJobState
from app.services.report_jobs import map_job_status
from arq.jobs import JobStatus

pytestmark = pytest.mark.unit


def test_queued_states() -> None:
    assert map_job_status(JobStatus.deferred) == ReportJobState.QUEUED
    assert map_job_status(JobStatus.queued) == ReportJobState.QUEUED


def test_in_progress() -> None:
    assert map_job_status(JobStatus.in_progress) == ReportJobState.IN_PROGRESS


def test_not_found() -> None:
    assert map_job_status(JobStatus.not_found) == ReportJobState.NOT_FOUND


def test_complete_success_vs_failure() -> None:
    assert map_job_status(JobStatus.complete, success=True) == ReportJobState.COMPLETE
    assert map_job_status(JobStatus.complete, success=False) == ReportJobState.FAILED
