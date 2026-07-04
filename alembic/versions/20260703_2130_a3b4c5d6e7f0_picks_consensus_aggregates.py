"""picks: add consensus_std, best_vs_avg, breadth_count (Sprint 1c)

Revision ID: a3b4c5d6e7f0
Revises:     f2a3b4c5d6e7
Create Date: 2026-07-03 21:30:00

Adds three market-consensus aggregate columns to the picks table.
All columns are nullable so existing rows require no backfill.
book_prices[] raw list is NOT persisted — only the derived scalars.
confidence_score is explicitly excluded (deferred to Sprint 1d).

Precision notes:
  consensus_std, best_vs_avg: Numeric(5,4) — probability space [0,1],
    same convention as implied_prob. NOT Numeric(6,4) which is reserved
    for odds-space columns (odds_decimal, closing_odds_decimal, clv).
  breadth_count: Integer — discrete bookmaker count.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql  # noqa: F401 — kept for consistency with repo style

# revision identifiers, used by Alembic.
revision = 'a3b4c5d6e7f0'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'picks',
        sa.Column('consensus_std', sa.Numeric(5, 4), nullable=True),
    )
    op.add_column(
        'picks',
        sa.Column('best_vs_avg', sa.Numeric(5, 4), nullable=True),
    )
    op.add_column(
        'picks',
        sa.Column('breadth_count', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('picks', 'breadth_count')
    op.drop_column('picks', 'best_vs_avg')
    op.drop_column('picks', 'consensus_std')
