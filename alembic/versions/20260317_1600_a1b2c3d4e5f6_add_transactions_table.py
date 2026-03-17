"""add_transactions_table

Revision ID: a1b2c3d4e5f6
Revises: 06e0c1a6dbd5
Create Date: 2026-03-17 16:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '06e0c1a6dbd5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Crear enum types
    transaction_type = sa.Enum(
        'deposit', 'withdrawal', 'bonus', 'commission', 'void_refund',
        name='transaction_type'
    )
    transaction_currency = sa.Enum(
        'MXN', 'EUR', 'USD', 'ARS', 'GBP',
        name='transaction_currency'
    )

    op.create_table(
        'transactions',
        sa.Column(
            'transaction_id',
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            'sportsbook_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('sportsbooks.sportsbook_id', ondelete='RESTRICT'),
            nullable=False,
        ),
        sa.Column(
            'type',
            transaction_type,
            nullable=False,
        ),
        sa.Column(
            'amount',
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column(
            'currency',
            transaction_currency,
            nullable=False,
            server_default='MXN',
        ),
        sa.Column(
            'exchange_rate',
            sa.Numeric(precision=10, scale=4),
            nullable=False,
            server_default='1.0000',
        ),
        sa.Column(
            'transaction_date',
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            'tax_year',
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            'reference_id',
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            'bank_reference',
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            'description',
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # Indices para consultas fiscales frecuentes
    op.create_index(
        'ix_transactions_sportsbook_id',
        'transactions',
        ['sportsbook_id'],
    )
    op.create_index(
        'ix_transactions_tax_year',
        'transactions',
        ['tax_year'],
    )
    op.create_index(
        'ix_transactions_type',
        'transactions',
        ['type'],
    )
    op.create_index(
        'ix_transactions_transaction_date',
        'transactions',
        ['transaction_date'],
    )


def downgrade() -> None:
    op.drop_index('ix_transactions_transaction_date', table_name='transactions')
    op.drop_index('ix_transactions_type', table_name='transactions')
    op.drop_index('ix_transactions_tax_year', table_name='transactions')
    op.drop_index('ix_transactions_sportsbook_id', table_name='transactions')
    op.drop_table('transactions')
    op.execute('DROP TYPE IF EXISTS transaction_type')
    op.execute('DROP TYPE IF EXISTS transaction_currency')
