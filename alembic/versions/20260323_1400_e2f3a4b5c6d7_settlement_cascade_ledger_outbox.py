"""settlement_cascade: ledger enum, unique (reference_id,type), outbox event_key, pick index

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-03-23 14:00:00.000000+00:00

Phase 6.2: strong idempotency for settlement ledger lines and outbox deduplication.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # 1.1 LedgerEntryType values (raw SQL, idempotent for asyncpg)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_catalog.pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'ledger_entry_type' AND e.enumlabel = 'PICK_PAYOUT'
            ) THEN
                ALTER TYPE ledger_entry_type ADD VALUE 'PICK_PAYOUT';
            END IF;
        END$$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_catalog.pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'ledger_entry_type' AND e.enumlabel = 'PICK_LOSS'
            ) THEN
                ALTER TYPE ledger_entry_type ADD VALUE 'PICK_LOSS';
            END IF;
        END$$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum e
                JOIN pg_catalog.pg_type t ON e.enumtypid = t.oid
                WHERE t.typname = 'ledger_entry_type' AND e.enumlabel = 'PICK_REFUND'
            ) THEN
                ALTER TYPE ledger_entry_type ADD VALUE 'PICK_REFUND';
            END IF;
        END$$;
    """)

    # 1.2 One settlement line per pick per ledger type (partial: PG allows many NULLs)
    op.create_index(
        "uq_ledger_entries_reference_id_type",
        "ledger_entries",
        ["reference_id", "type"],
        unique=True,
        postgresql_where=sa.text("reference_id IS NOT NULL"),
    )

    # 1.3 Outbox idempotent event_key
    op.add_column(
        "outbox_events",
        sa.Column("event_key", sa.String(length=128), nullable=True),
    )
    op.execute("""
        UPDATE outbox_events
        SET event_key = 'legacy:' || outbox_event_id::text
        WHERE event_key IS NULL
    """)
    op.alter_column(
        "outbox_events",
        "event_key",
        existing_type=sa.String(length=128),
        nullable=False,
    )
    op.create_index(
        "uq_outbox_events_event_key",
        "outbox_events",
        ["event_key"],
        unique=True,
    )

    # 1.4 Settlement / status queries
    op.create_index(
        "ix_picks_pick_id_status",
        "picks",
        ["pick_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_picks_pick_id_status", table_name="picks")
    op.drop_index("uq_outbox_events_event_key", table_name="outbox_events")
    op.drop_column("outbox_events", "event_key")
    op.drop_index(
        "uq_ledger_entries_reference_id_type",
        table_name="ledger_entries",
    )
    # Cannot remove enum values safely in PostgreSQL; new values remain on downgrade.
