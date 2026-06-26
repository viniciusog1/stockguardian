"""stock alerts

Revision ID: 0002_stock_alerts
Revises: 0001_initial
Create Date: 2026-06-26 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_stock_alerts"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    alert_status = postgresql.ENUM("open", "acknowledged", "resolved", name="alert_status")
    alert_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "stock_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "open", "acknowledged", "resolved", name="alert_status", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("triggered_quantity", sa.Integer(), nullable=False),
        sa.Column("min_stock_at_trigger", sa.Integer(), nullable=False),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_alerts_product_id", "stock_alerts", ["product_id"])
    op.create_index(
        "uq_stock_alerts_active_per_product",
        "stock_alerts",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'resolved'"),
    )


def downgrade() -> None:
    op.drop_table("stock_alerts")
    op.execute("DROP TYPE IF EXISTS alert_status")
