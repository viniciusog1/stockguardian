from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class LivenessResponse(BaseModel):
    status: str
    service: str


class CheckResult(BaseModel):
    status: Literal["ok", "error"]
    detail: str | None = None


class ReadinessResponse(BaseModel):
    ready: bool
    checks: dict[str, CheckResult]
