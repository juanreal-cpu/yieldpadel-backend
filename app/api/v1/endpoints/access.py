import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.audit import log_activity
from app.services.access import (
    clear_debt_in_counter,
    get_active_now_data,
    perform_check_in,
    perform_check_out,
)
from app.services.whatsapp import send_whatsapp_message, log_conversation_message
from app.models.slot import TimeSlot
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger("yieldpadel.access")

router = APIRouter()


# ----------------------------------------------------
# Pydantic Schemas
# ----------------------------------------------------
class CheckInRequest(BaseModel):
    player_id: Optional[int] = None
    player_name: Optional[str] = None
    phone: Optional[str] = None
    current_slot_id: Optional[int] = None
    membership_tier: Optional[str] = None


class CheckOutRequest(BaseModel):
    presence_id: Optional[int] = None
    player_id: Optional[int] = None
    force_clear: bool = False


# ----------------------------------------------------
# Endpoints
# ----------------------------------------------------
@router.post("/check-in", summary="Registrar entrada de jugador al club")
async def check_in_endpoint(
    payload: CheckInRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        presence = await perform_check_in(
            db=db,
            player_id=payload.player_id,
            player_name=payload.player_name,
            phone=payload.phone,
            current_slot_id=payload.current_slot_id,
            membership_tier=payload.membership_tier,
        )
        try:
            await log_activity(
                db=db,
                action="ACCESO_REGISTRADO",
                entity_name="ACCESS",
                entity_id=str(presence.id),
                details=f"Check-In de {presence.player_name} (Membresía: {presence.membership_tier})",
                username_snapshot="Molinete de Entrada",
            )
        except Exception as log_err:
            logger.warning(f"Error logging check-in audit: {log_err}")

        # Mensaje de bienvenida por WhatsApp al registrar check-in
        if presence.phone:
            court_name = "Pista Asignada"
            if presence.current_slot_id:
                slot_res = await db.execute(
                    select(TimeSlot).options(selectinload(TimeSlot.court)).where(TimeSlot.id == presence.current_slot_id)
                )
                slot_obj = slot_res.scalars().first()
                if slot_obj and slot_obj.court:
                    court_name = slot_obj.court.name

            welcome_msg = (
                f"👋 *¡Bienvenido a Capital Pádel Club, {presence.player_name}!* 🎾\n\n"
                f"Tu ingreso ha sido registrado exitosamente.\n"
                f"• Cancha asignada: *{court_name}*\n"
                f"• Plan de Socio: {presence.membership_tier or 'Estándar'}\n\n"
                "Recuerda que tienes vestieres con duchas y lockers a tu disposición. "
                "¡Que tengas un excelente partido!"
            )
            try:
                await send_whatsapp_message(to_phone=presence.phone, message_body=welcome_msg)
                await log_conversation_message(db, presence.phone, welcome_msg, direction="bot", player_name=presence.player_name)
            except Exception as e:
                logger.warning(f"Error enviando WhatsApp de check-in: {e}")

        return {
            "success": True,
            "message": f"Entrada registrada para {presence.player_name}",
            "presence": {
                "id": presence.id,
                "player_id": presence.player_id,
                "player_name": presence.player_name,
                "phone": presence.phone,
                "check_in_time": presence.check_in_time.isoformat(),
                "membership_tier": presence.membership_tier,
                "current_slot_id": presence.current_slot_id,
                "is_inside": presence.is_inside,
            },
        }
    except Exception as e:
        logger.error(f"Error en check-in: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check-out", summary="Registrar y validar salida de jugador (Bloqueo Financiero)")
async def check_out_endpoint(
    payload: CheckOutRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await perform_check_out(
            db=db,
            presence_id=payload.presence_id,
            player_id=payload.player_id,
            force_clear=payload.force_clear,
        )
        try:
            await log_activity(
                db=db,
                action="ACCESO_REGISTRADO",
                entity_name="ACCESS",
                entity_id=str(result.get("presence_id") or payload.presence_id or ""),
                details=f"Check-Out {result.get('status')} para {result.get('player_name')}. Saldo pendiente: ${result.get('pending_balance', 0):,.0f} COP",
                username_snapshot="Molinete de Salida",
            )
        except Exception as log_err:
            logger.warning(f"Error logging check-out audit: {log_err}")

        # Mensaje de despedida y agradecimiento por WhatsApp si check-out fue exitoso
        player_phone = result.get("phone")
        player_name = result.get("player_name") or "Jugador"
        if result.get("status") == "SUCCESS" and player_phone:
            farewell_msg = (
                f"🎾 *¡Gracias por jugar hoy en Capital Pádel Club, {player_name}!* 🏆\n\n"
                "Esperamos que hayas disfrutado tu partido y tu estadía en el club.\n"
                "Tus puntos y estadísticas ya se encuentran actualizados en tu perfil.\n\n"
                "¡Nos vemos pronto en la pista!"
            )
            try:
                await send_whatsapp_message(to_phone=player_phone, message_body=farewell_msg)
                await log_conversation_message(db, player_phone, farewell_msg, direction="bot", player_name=player_name)
            except Exception as e:
                logger.warning(f"Error enviando WhatsApp de check-out: {e}")

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en check-out: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-debt/{presence_id}", summary="Liquidar consumos/turnos en counter y desbloquear")
async def clear_debt_endpoint(
    presence_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await clear_debt_in_counter(db=db, presence_id=presence_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error liquidando deuda: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active-now", summary="Obtener aforo activo, alertas y métricas en tiempo real")
async def active_now_endpoint(
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await get_active_now_data(db=db)
        return data
    except Exception as e:
        logger.error(f"Error obteniendo aforo activo: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
