"""stock alerts overstock (kind + threshold rename)

Revision ID: 0003_stock_alerts_overstock
Revises: 0002_stock_alerts
Create Date: 2026-06-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_stock_alerts_overstock"
down_revision: str | None = "0002_stock_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    alert_kind = postgresql.ENUM("low_stock", "overstock", name="alert_kind")
    alert_kind.create(op.get_bind(), checkfirst=True)

    # add kind com default p/ backfill das linhas existentes; depois remove o default
    op.add_column(
        "stock_alerts",
        sa.Column(
            "kind",
            postgresql.ENUM("low_stock", "overstock", name="alert_kind", create_type=False),
            nullable=False,
            server_default="low_stock",
        ),
    )
    op.alter_column("stock_alerts", "kind", server_default=None)

    op.alter_column("stock_alerts", "min_stock_at_trigger", new_column_name="threshold_at_trigger")

    op.drop_index("uq_stock_alerts_active_per_product", table_name="stock_alerts")
    op.create_index(
        "uq_stock_alerts_active_per_product",
        "stock_alerts",
        ["product_id", "kind"],
        unique=True,
        postgresql_where=sa.text("status <> 'resolved'"),
    )


def downgrade() -> None:
    op.drop_index("uq_stock_alerts_active_per_product", table_name="stock_alerts")
    op.create_index(
        "uq_stock_alerts_active_per_product",
        "stock_alerts",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'resolved'"),
    )
    op.alter_column("stock_alerts", "threshold_at_trigger", new_column_name="min_stock_at_trigger")
    op.drop_column("stock_alerts", "kind")
    op.execute("DROP TYPE IF EXISTS alert_kind")
