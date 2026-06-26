"""Testes unitários da normalização do resumo de movimentações (função pura)."""

from __future__ import annotations

import pytest
from app.models.stock_movement import MovementType
from app.services.report import build_movement_summary_rows

pytestmark = pytest.mark.unit


def test_all_types_present() -> None:
    counts = {
        MovementType.IN: (3, 30),
        MovementType.OUT: (2, 12),
        MovementType.ADJUSTMENT: (1, 5),
    }
    rows = build_movement_summary_rows(counts)
    assert [r.type for r in rows] == [MovementType.IN, MovementType.OUT, MovementType.ADJUSTMENT]
    assert (rows[0].movement_count, rows[0].total_quantity) == (3, 30)
    assert (rows[1].movement_count, rows[1].total_quantity) == (2, 12)


def test_missing_types_filled_with_zero() -> None:
    rows = build_movement_summary_rows({MovementType.IN: (2, 8)})
    by_type = {r.type: (r.movement_count, r.total_quantity) for r in rows}
    assert by_type[MovementType.IN] == (2, 8)
    assert by_type[MovementType.OUT] == (0, 0)
    assert by_type[MovementType.ADJUSTMENT] == (0, 0)


def test_empty_gives_three_zeroed_rows() -> None:
    rows = build_movement_summary_rows({})
    assert len(rows) == 3
    assert all(r.movement_count == 0 and r.total_quantity == 0 for r in rows)
