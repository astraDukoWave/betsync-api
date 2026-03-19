"""shadow_aggregate_tables_pick_settlement_columns

Revision ID: b7e8f9a0c1d2
Revises: a1b2c3d4e5f6
Create Date: 2026-03-19 12:00:00.000000+00:00

Phase 1 shadow aggregates (scaling_strategy.md):
- picks: settled_return, profit, computation_version
- agg_pick_daily, agg_pick_dimension_daily

Staleness SLA (initial): rows updated by backfill / future async workers;
monitor updated_at once mutation-driven tasks exist.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e8f9a0c1d2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "picks",
        sa.Column("settled_return", sa.Numeric(precision=10, scale=2), nullable=True),
    )
    op.add_column(
        "picks",
        sa.Column("profit", sa.Numeric(precision=10, scale=2), nullable=True),
    )
    op.add_column(
        "picks",
        sa.Column(
            "computation_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )

    op.create_table(
        "agg_pick_daily",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("pick_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "total_stake", sa.Numeric(precision=14, scale=2),
            server_default="0", nullable=False,
        ),
        sa.Column(
            "total_profit", sa.Numeric(precision=14, scale=2),
            server_default="0", nullable=False,
        ),
        sa.Column(
            "total_settled_return", sa.Numeric(precision=14, scale=2),
            server_default="0", nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "computation_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("day"),
    )

    op.create_table(
        "agg_pick_dimension_daily",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("dimension", sa.String(length=200), nullable=False),
        sa.Column("pick_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "total_stake", sa.Numeric(precision=14, scale=2),
            server_default="0", nullable=False,
        ),
        sa.Column(
            "total_profit", sa.Numeric(precision=14, scale=2),
            server_default="0", nullable=False,
        ),
        sa.Column(
            "total_settled_return", sa.Numeric(precision=14, scale=2),
            server_default="0", nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "computation_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("day", "dimension"),
    )


def downgrade() -> None:
    op.drop_table("agg_pick_dimension_daily")
    op.drop_table("agg_pick_daily")
    op.drop_column("picks", "computation_version")
    op.drop_column("picks", "profit")
    op.drop_column("picks", "settled_return")
