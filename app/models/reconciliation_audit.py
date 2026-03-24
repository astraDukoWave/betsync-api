import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReconciliationAudit(Base):
    """Append-only audit rows for financial reconciliation anomalies (WARNING / CRITICAL only)."""

    __tablename__ = "reconciliation_audits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("user_balances.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    escrow_drift: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    ledger_drift: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
