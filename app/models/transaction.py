import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    String, Numeric, Date, DateTime, Integer, ForeignKey, func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.sportsbook import Sportsbook


class TransactionType(str, enum.Enum):
    deposit = "deposit"
    withdrawal = "withdrawal"
    bonus = "bonus"
    commission = "commission"
    void_refund = "void_refund"


class TransactionCurrency(str, enum.Enum):
    MXN = "MXN"
    EUR = "EUR"
    USD = "USD"
    ARS = "ARS"
    GBP = "GBP"


class Transaction(Base):
    """Registro de movimientos de dinero FUERA de las apuestas.

    Captura depósitos, retiros, bonos y comisiones por casa de
    apuestas. Es la pieza central para calcular el flujo de caja
    real y la base imponible para SAT/AEAT/AFIP.
    """

    __tablename__ = "transactions"

    # --- Identidad ---
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )

    # --- Relación con casa de apuestas ---
    sportsbook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sportsbooks.sportsbook_id"), nullable=False
    )

    # --- Tipo y monto ---
    type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, name="transaction_type"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False
    )

    # --- Divisas y tipo de cambio ---
    # currency: moneda en que se realizó el movimiento en la casa
    currency: Mapped[TransactionCurrency] = mapped_column(
        SAEnum(TransactionCurrency, name="transaction_currency"),
        default=TransactionCurrency.MXN,
        nullable=False,
    )
    # exchange_rate: TC al día del movimiento (base siempre MXN).
    # Ejemplo: si la transacción fue en EUR y 1 EUR = 20.5 MXN, exchange_rate = 20.5
    # Si la moneda es MXN, exchange_rate = 1.0
    exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("1.0000"), nullable=False
    )

    # --- Fechas fiscales ---
    # transaction_date: fecha real del movimiento en la casa/banco
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    # tax_year: año fiscal al que pertenece este movimiento (YYYY).
    # Calculado automáticamente desde transaction_date, pero sobreescribible
    # en casos de declaración suplementaria.
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- Referencias externas ---
    # reference_id: ID o número de transacción de la casa de apuestas
    reference_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    # bank_reference: número de transferencia bancaria o de wallet
    bank_reference: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    # --- Descripción libre ---
    description: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )

    # --- Auditoría ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # --- Relaciones ORM ---
    sportsbook: Mapped["Sportsbook"] = relationship(
        back_populates="transactions"
    )

    @property
    def amount_mxn(self) -> Decimal:
        """Monto convertido a MXN usando el TC registrado.
        Útil para la agregación fiscal en moneda base.
        """
        return self.amount * self.exchange_rate

    def __repr__(self) -> str:
        return (
            f"<Transaction id={self.transaction_id} "
            f"type={self.type} amount={self.amount} "
            f"{self.currency} tax_year={self.tax_year}>"
        )
