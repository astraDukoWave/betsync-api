import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, Numeric, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.ledger import LedgerEntry


class UserBalance(Base):
    """Lockable cache of per-user available / locked funds (escrow).

    Authoritative history is ``ledger_entries``; this row is updated only
    alongside a new ledger row under SELECT FOR UPDATE.
    """

    __tablename__ = "user_balances"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    available_balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    locked_balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2), nullable=False, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    ledger_entries: Mapped[List["LedgerEntry"]] = relationship(
        back_populates="user_balance",
    )
