import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.balance import UserBalance


class LedgerEntryType(str, enum.Enum):
    """Append-only ledger line types. Extend with reversals/settlements as needed."""

    PICK_STAKE_LOCK = "PICK_STAKE_LOCK"
    PICK_PAYOUT = "PICK_PAYOUT"
    PICK_LOSS = "PICK_LOSS"
    PICK_REFUND = "PICK_REFUND"


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    ledger_entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_balances.user_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    type: Mapped[LedgerEntryType] = mapped_column(
        SAEnum(LedgerEntryType, name="ledger_entry_type"),
        nullable=False,
    )
    reference_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    locked_after: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user_balance: Mapped["UserBalance"] = relationship(
        back_populates="ledger_entries",
    )
