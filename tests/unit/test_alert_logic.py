"""Testes unitários da decisão de alerta (função pura)."""

from __future__ import annotations

import pytest
from app.services.alert import AlertAction, decide_alert_action

pytestmark = pytest.mark.unit


def test_opens_when_crossing_minimum_and_no_active() -> None:
    assert decide_alert_action(quantity=2, min_stock=5, has_active=False) == AlertAction.OPEN


def test_noop_when_low_but_already_active() -> None:
    assert decide_alert_action(quantity=2, min_stock=5, has_active=True) == AlertAction.NOOP


def test_resolves_when_recovered_and_active() -> None:
    assert decide_alert_action(quantity=9, min_stock=5, has_active=True) == AlertAction.RESOLVE


def test_noop_when_healthy_and_no_active() -> None:
    assert decide_alert_action(quantity=9, min_stock=5, has_active=False) == AlertAction.NOOP


def test_zero_min_and_zero_qty_opens() -> None:
    assert decide_alert_action(quantity=0, min_stock=0, has_active=False) == AlertAction.OPEN
