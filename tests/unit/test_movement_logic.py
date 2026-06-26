"""Testes unitários da regra de cálculo de saldo (função pura)."""

from __future__ import annotations

import pytest
from app.exceptions.domain import InsufficientStockError
from app.models.stock_movement import MovementType
from app.services.movement import _apply_movement

pytestmark = pytest.mark.unit


def test_in_adds_to_balance() -> None:
    assert _apply_movement(10, MovementType.IN, 5) == 15


def test_out_subtracts_from_balance() -> None:
    assert _apply_movement(10, MovementType.OUT, 4) == 6


def test_out_to_exact_zero_is_allowed() -> None:
    assert _apply_movement(10, MovementType.OUT, 10) == 0


def test_out_below_zero_raises() -> None:
    with pytest.raises(InsufficientStockError) as exc:
        _apply_movement(3, MovementType.OUT, 5)
    assert exc.value.details["available"] == 3
    assert exc.value.details["requested"] == 5


def test_adjustment_sets_absolute_value() -> None:
    assert _apply_movement(10, MovementType.ADJUSTMENT, 2) == 2
    assert _apply_movement(0, MovementType.ADJUSTMENT, 99) == 99
