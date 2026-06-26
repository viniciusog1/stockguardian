"""Testes unitários da decisão de alerta (função pura)."""

from __future__ import annotations

import pytest
from app.services.alert import AlertAction, decide_alert_action

pytestmark = pytest.mark.unit


def test_opens_when_condition_and_no_active() -> None:
    assert decide_alert_action(condition_met=True, has_active=False) == AlertAction.OPEN


def test_noop_when_condition_but_already_active() -> None:
    assert decide_alert_action(condition_met=True, has_active=True) == AlertAction.NOOP


def test_resolves_when_condition_cleared_and_active() -> None:
    assert decide_alert_action(condition_met=False, has_active=True) == AlertAction.RESOLVE


def test_noop_when_healthy_and_no_active() -> None:
    assert decide_alert_action(condition_met=False, has_active=False) == AlertAction.NOOP
