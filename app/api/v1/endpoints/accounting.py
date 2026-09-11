import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.timezone import get_bogota_today
from app.models.accounting import DailyAccountingLedger

logger = logging.getLogger("yieldpadel.accounting")
router = APIRouter()


class RecordTransactionRequest(BaseModel):
    customer_name: str = "Cliente General"
    customer_phone: Optional[str] = None
    concept: str = "CANCHAS"  # CANCHAS, TIENDA, AMERICANOS, CLASES, MEMBRESIA, OTROS
    details: Optional[str] = None
    payment_method: str = "EFECTIVO"  # EFECTIVO, DATAFONO, TRANSFERENCIA, SPLIT, BOLD_WOMPI, SALDO_A_FAVOR
    amount_cash: float = 0.0
    amount_card: float = 0.0
    amount_digital: float = 0.0
    total_amount: float
    operator: Optional[str] = "Recepcionista Turno"
    slot_id: Optional[int] = None
    order_id: Optional[int] = None
    target_date: Optional[str] = None


@router.get("/daily-ledger", summary="Consultar libro de arqueo diario consolidado")
async def get_daily_ledger(
    target_date: Optional[str] = Query(None, alias="date"),
    concept: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna el libro contable de arqueo diario y la sumatoria consolidada
    por medio de pago (Total Facturado, Efectivo, Datáfono, Transferencias).
    """
    try:
        if target_date:
            try:
                parsed_date = date.fromisoformat(target_date.strip())
            except ValueError:
                parsed_date = get_bogota_today()
        else:
            parsed_date = get_bogota_today()

        stmt = select(DailyAccountingLedger).where(DailyAccountingLedger.date == parsed_date)
        if concept and concept.upper() != "TODOS":
            stmt = stmt.where(DailyAccountingLedger.concept == concept.upper())

        stmt = stmt.order_by(desc(DailyAccountingLedger.created_at))
        res = await db.execute(stmt)
        transactions = list(res.scalars().all())

        total_billed = sum(float(t.total_amount or 0) for t in transactions)
        total_cash = sum(float(t.amount_cash or 0) for t in transactions)
        total_card = sum(float(t.amount_card or 0) for t in transactions)
        total_digital = sum(float(t.amount_digital or 0) for t in transactions)

        return {
            "date": str(parsed_date),
            "total_transactions": len(transactions),
            "kpis": {
                "total_billed_cop": total_billed,
                "total_cash_cop": total_cash,
                "total_card_cop": total_card,
                "total_digital_cop": total_digital,
            },
            "transactions": [
                {
                    "id": t.id,
                    "transaction_id": t.transaction_id,
                    "date": str(t.date),
                    "time": t.created_at.strftime("%H:%M") if t.created_at else "--:--",
                    "customer_name": t.customer_name,
                    "customer_phone": t.customer_phone,
                    "concept": t.concept,
                    "details": t.details,
                    "payment_method": t.payment_method,
                    "amount_cash": float(t.amount_cash or 0),
                    "amount_card": float(t.amount_card or 0),
                    "amount_digital": float(t.amount_digital or 0),
                    "total_amount": float(t.total_amount or 0),
                    "operator": t.operator,
                    "slot_id": t.slot_id,
                    "order_id": t.order_id,
                }
                for t in transactions
            ],
        }
    except Exception as e:
        logger.exception("Error al consultar libro contable")
        raise HTTPException(status_code=500, detail=f"Error consultando arqueo: {str(e)}")


@router.post("/record-transaction", status_code=status.HTTP_201_CREATED, summary="Registrar movimiento contable en arqueo")
async def record_transaction(
    payload: RecordTransactionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Inserta una fila en el libro contable (daily_accounting_ledger)
    cada vez que se liquida una cancha, producto, americano o cobro manual.
    """
    try:
        rec_date = get_bogota_today()
        if payload.target_date:
            try:
                rec_date = date.fromisoformat(payload.target_date.strip())
            except ValueError:
                pass

        # Autocalcular montos si es medio único
        cash = Decimal(str(payload.amount_cash))
        card = Decimal(str(payload.amount_card))
        dig = Decimal(str(payload.amount_digital))
        tot = Decimal(str(payload.total_amount))
        pm = payload.payment_method.upper()

        if pm == "EFECTIVO" and cash == 0:
            cash = tot
        elif pm == "DATAFONO" and card == 0:
            card = tot
        elif pm in ("TRANSFERENCIA", "BOLD_WOMPI") and dig == 0:
            dig = tot

        ledger_item = DailyAccountingLedger(
            date=rec_date,
            customer_name=payload.customer_name.strip() or "Cliente General",
            customer_phone=payload.customer_phone,
            concept=payload.concept.upper(),
            details=payload.details,
            payment_method=pm,
            amount_cash=cash,
            amount_card=card,
            amount_digital=dig,
            total_amount=tot,
            operator=payload.operator or "Recepcionista Turno",
            slot_id=payload.slot_id,
            order_id=payload.order_id,
        )
        db.add(ledger_item)
        await db.commit()
        await db.refresh(ledger_item)

        return {
            "status": "recorded",
            "transaction_id": ledger_item.transaction_id,
            "id": ledger_item.id,
            "total_amount": float(ledger_item.total_amount),
            "payment_method": ledger_item.payment_method,
        }
    except Exception as e:
        await db.rollback()
        logger.exception("Error al registrar transacción contable")
        raise HTTPException(status_code=500, detail=f"Error registrando movimiento: {str(e)}")
