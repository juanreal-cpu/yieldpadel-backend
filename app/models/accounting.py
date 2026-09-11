import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import Date, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DailyAccountingLedger(Base):
    __tablename__ = "daily_accounting_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    transaction_id: Mapped[str] = mapped_column(
        String(100), default=lambda: f"REC-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}", index=True
    )
    date: Mapped[date] = mapped_column(Date, default=lambda: datetime.now(timezone.utc).date(), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    customer_name: Mapped[str] = mapped_column(String(150), default="Cliente General", nullable=False)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    concept: Mapped[str] = mapped_column(
        String(50), default="CANCHAS", nullable=False, index=True
    )  # 'CANCHAS', 'TIENDA', 'AMERICANOS', 'CLASES', 'MEMBRESIA', 'OTROS'
    details: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_method: Mapped[str] = mapped_column(
        String(50), default="EFECTIVO", nullable=False
    )  # 'EFECTIVO', 'DATAFONO', 'TRANSFERENCIA', 'SPLIT', 'BOLD_WOMPI', 'SALDO_A_FAVOR'
    amount_cash: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    amount_card: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    amount_digital: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    operator: Mapped[str] = mapped_column(String(100), default="Recepcionista Turno", nullable=False)
    slot_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
