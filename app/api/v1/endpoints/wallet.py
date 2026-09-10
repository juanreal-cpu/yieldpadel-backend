from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter()


class WalletTransactionRequest(BaseModel):
    amount: float = Field(..., gt=-1000000000, lt=1000000000)
    transaction_type: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)


@router.post("/{customer_id}/transaction")
async def create_wallet_transaction(
    customer_id: int,
    payload: WalletTransactionRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        customer_row = (await db.execute(
            text("SELECT id, wallet_balance FROM customers WHERE id = :customer_id"),
            {"customer_id": customer_id},
        )).mappings().first()

        if customer_row is None:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")

        current_balance = float(customer_row["wallet_balance"] or 0)
        amount = float(payload.amount)
        transaction_type = (payload.transaction_type or "").strip()
        normalized_type = transaction_type.lower()

        if normalized_type in {"credit", "credito", "ingreso", "deposit", "deposito", "topup", "add", "plus"}:
            delta = amount
        elif normalized_type in {"debit", "debito", "retiro", "withdraw", "withdrawal", "expense", "gasto", "charge", "cobro"}:
            delta = -amount
        else:
            delta = amount if amount >= 0 else -abs(amount)

        new_balance = current_balance + delta

        await db.execute(
            text("UPDATE customers SET wallet_balance = :new_balance WHERE id = :customer_id"),
            {"new_balance": new_balance, "customer_id": customer_id},
        )

        await db.execute(
            text(
                """
                INSERT INTO wallet_transactions (
                    customer_id,
                    amount,
                    transaction_type,
                    description,
                    balance_after,
                    created_at
                ) VALUES (
                    :customer_id,
                    :amount,
                    :transaction_type,
                    :description,
                    :balance_after,
                    NOW()
                )
                """
            ),
            {
                "customer_id": customer_id,
                "amount": amount,
                "transaction_type": transaction_type,
                "description": payload.description,
                "balance_after": new_balance,
            },
        )

        await db.commit()
        return {
            "status": "ok",
            "new_balance": float(new_balance),
            "customer_id": int(customer_id),
        }
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error en la transacción de wallet: {str(exc)}") from exc


@router.get("/{customer_id}/history")
async def get_wallet_history(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        rows = (await db.execute(
            text(
                """
                SELECT id, customer_id, amount, transaction_type, description, balance_after, created_at
                FROM wallet_transactions
                WHERE customer_id = :customer_id
                ORDER BY created_at DESC
                LIMIT 50
                """
            ),
            {"customer_id": customer_id},
        )).mappings().all()

        return [
            {
                "id": row["id"],
                "customer_id": row["customer_id"],
                "amount": float(row["amount"] or 0),
                "transaction_type": row["transaction_type"],
                "description": row["description"],
                "balance_after": float(row["balance_after"] or 0),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando historial de wallet: {str(exc)}") from exc


@router.get("/ledger")
async def get_wallet_ledger(
    limit: int = 50,
    offset: int = 0,
    transaction_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        params: Dict[str, Any] = {"limit": max(1, min(limit, 200)), "offset": max(0, offset)}
        base_sql = """
            SELECT
                wt.id,
                wt.created_at,
                c.name AS customer_name,
                c.phone AS customer_phone,
                wt.transaction_type,
                wt.amount,
                wt.balance_after,
                wt.description
            FROM wallet_transactions wt
            LEFT JOIN customers c ON c.id = wt.customer_id
        """

        clauses = []
        if transaction_type:
            clauses.append("wt.transaction_type = :transaction_type")
            params["transaction_type"] = transaction_type.strip()

        if clauses:
            base_sql += " WHERE " + " AND ".join(clauses)

        base_sql += " ORDER BY wt.created_at DESC LIMIT :limit OFFSET :offset"

        rows = (await db.execute(text(base_sql), params)).mappings().all()

        return [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "customer_name": row["customer_name"],
                "customer_phone": row["customer_phone"],
                "transaction_type": row["transaction_type"],
                "amount": float(row["amount"] or 0),
                "balance_after": float(row["balance_after"] or 0),
                "description": row["description"],
            }
            for row in rows
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando ledger de wallet: {str(exc)}") from exc


@router.get("/metrics")
async def get_wallet_metrics(db: AsyncSession = Depends(get_db)):
    try:
        summary = (await db.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS total_issued,
                    COALESCE(ABS(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END)), 0) AS total_redeemed,
                    COALESCE((SELECT SUM(wallet_balance) FROM customers), 0) AS circulating_liability,
                    COUNT(*) AS total_transactions
                FROM wallet_transactions
                """
            )
        )).mappings().first()

        if summary is None:
            metrics = {
                "total_issued": 0.0,
                "total_redeemed": 0.0,
                "circulating_liability": 0.0,
                "total_transactions": 0,
            }
        else:
            metrics = {
                "total_issued": float(summary["total_issued"] or 0),
                "total_redeemed": float(summary["total_redeemed"] or 0),
                "circulating_liability": float(summary["circulating_liability"] or 0),
                "total_transactions": int(summary["total_transactions"] or 0),
            }

        return {"status": "ok", "metrics": metrics}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando métricas de wallet: {str(exc)}") from exc
