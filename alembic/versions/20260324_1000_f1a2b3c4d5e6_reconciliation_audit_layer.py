"""reconciliation audit table + picks index for per-user pending stake scans

Revision ID: f1a2b3c4d5e6
Revises: e2f3a4b5c6d7
Create Date: 2026-03-24 10:00:00.000000+00:00

Phase 6.2.2: continuous financial reconciliation — audit persistence and indexed
``picks (user_id, status)`` for batched ``SUM(stake)`` WHERE status = pending per user.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e2f3a4b5c6d7"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("escrow_drift", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("ledger_drift", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_balances.user_id"],
            name="fk_reconciliation_audits_user_id_user_balances",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reconciliation_audits_user_id"),
        "reconciliation_audits",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliation_audits_created_at"),
        "reconciliation_audits",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_picks_user_id_status_reconciliation",
        "picks",
        ["user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_picks_user_id_status_reconciliation", table_name="picks")
    op.drop_index(op.f("ix_reconciliation_audits_created_at"), table_name="reconciliation_audits")
    op.drop_index(op.f("ix_reconciliation_audits_user_id"), table_name="reconciliation_audits")
    op.drop_table("reconciliation_audits")
