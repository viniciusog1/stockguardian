"""Unit: counters de negócio e idempotência do setup de métricas."""

from __future__ import annotations

import pytest
from app.core.metrics import MOVEMENTS_TOTAL
from app.main import create_app

pytestmark = pytest.mark.unit


def test_counter_increments() -> None:
    before = MOVEMENTS_TOTAL.labels(type="in")._value.get()
    MOVEMENTS_TOTAL.labels(type="in").inc()
    after = MOVEMENTS_TOTAL.labels(type="in")._value.get()
    assert after == before + 1


def test_create_app_twice_is_idempotent() -> None:
    a1 = create_app()
    a2 = create_app()
    for app in (a1, a2):
        assert any(getattr(r, "path", "") == "/metrics" for r in app.routes)
