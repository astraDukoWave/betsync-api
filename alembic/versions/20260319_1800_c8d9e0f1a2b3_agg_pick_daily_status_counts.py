"""agg_pick_daily_status_counts_for_integrity_checks

Revision ID: c8d9e0f1a2b3
Revises: b7e8f9a0c1d2
Create Date: 2026-03-19 18:00:00.000000+00:00

Per-day status partition columns for AggPickDaily internal consistency:
pick_count must equal won + lost + push + pending + void.
Re-run aggregate recompute / backfill after upgrade to populate counts.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b7e8f9a0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agg_pick_daily",
        sa.Column("won_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "agg_pick_daily",
        sa.Column("lost_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "agg_pick_daily",
        sa.Column("push_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "agg_pick_daily",
        sa.Column("pending_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "agg_pick_daily",
        sa.Column("void_count", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("agg_pick_daily", "void_count")
    op.drop_column("agg_pick_daily", "pending_count")
    op.drop_column("agg_pick_daily", "push_count")
    op.drop_column("agg_pick_daily", "lost_count")
    op.drop_column("agg_pick_daily", "won_count")
