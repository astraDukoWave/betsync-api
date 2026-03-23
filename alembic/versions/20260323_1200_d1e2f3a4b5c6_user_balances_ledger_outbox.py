"""user_balances_ledger_entries_outbox_events

Revision ID: d1e2f3a4b5c6
Revises: c8d9e0f1a2b3
Create Date: 2026-03-23 12:00:00.000000+00:00

Financial core: lockable balance cache (available/locked), append-only ledger,
transactional outbox, and optional picks.user_id for staked picks.

New users get a user_balances row via application INSERT ... ON CONFLICT DO NOTHING
before SELECT FOR UPDATE (see ledger_service.lock_and_get_balance).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ledger_entry_type = sa.Enum("PICK_STAKE_LOCK", name="ledger_entry_type")
    ledger_entry_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "user_balances",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "available_balance",
            sa.Numeric(15, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "locked_balance",
            sa.Numeric(15, 2),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "ledger_entries",
        sa.Column("ledger_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("type", ledger_entry_type, nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("balance_after", sa.Numeric(15, 2), nullable=False),
        sa.Column("locked_after", sa.Numeric(15, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user_balances.user_id"],
            name="fk_ledger_entries_user_id_user_balances",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("ledger_entry_id"),
    )
    op.create_index(
        op.f("ix_ledger_entries_user_id"),
        "ledger_entries",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "outbox_events",
        sa.Column("outbox_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("outbox_event_id"),
    )

    op.add_column(
        "picks",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(op.f("ix_picks_user_id"), "picks", ["user_id"], unique=False)
    op.create_foreign_key(
        "fk_picks_user_id_user_balances",
        "picks",
        "user_balances",
        ["user_id"],
        ["user_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_picks_user_id_user_balances", "picks", type_="foreignkey")
    op.drop_index(op.f("ix_picks_user_id"), table_name="picks")
    op.drop_column("picks", "user_id")

    op.drop_table("outbox_events")

    op.drop_index(op.f("ix_ledger_entries_user_id"), table_name="ledger_entries")
    op.drop_table("ledger_entries")

    op.drop_table("user_balances")

    ledger_entry_type = sa.Enum("PICK_STAKE_LOCK", name="ledger_entry_type")
    ledger_entry_type.drop(op.get_bind(), checkfirst=True)
