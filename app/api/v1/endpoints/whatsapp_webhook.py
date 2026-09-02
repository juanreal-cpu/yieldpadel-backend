import logging
import re
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.slot import TimeSlot
from app.schemas.slot import (
    DropPlayerRequest,
    WhatsAppConvocatoriaRequest,
)
from app.api.v1.endpoints.slots import (
    drop_player,
    normalize_phone,
    parse_open_match,
    to_participants_list,
)

logger = logging.getLogger(__name__)

router = APIRouter()

VERIFY_TOKEN = "yieldpadel_secret_token_2026"


@router.get("/webhook")
async def verify_webhook(request: Request):
    hub_mode = request.query_params.get("hub.mode")
    hub_token = request.query_params.get("hub.verify_token")
    hub_challenge = request.query_params.get("hub.challenge")

    if hub_mode == "subscribe" and hub_token == "yieldpadel_secret_token_2026":
        return PlainTextResponse(content=str(hub_challenge), status_code=200)

    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Recepción de eventos de WhatsApp Cloud API (Meta).
    Procesa mensajes de convocatorias con 🎾 y solicitudes de baja ('me bajo', 'cancelo').
    Siempre responde HTTP 200 {"status": "received"} a Meta.
    """
    try:
        body = await request.json()
        logger.info(f"Incoming WhatsApp webhook payload: {body}")

        entries = body.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])
                
                for msg in messages:
                    # Extraer teléfono del remitente
                    raw_from = msg.get("from", "")
                    if not raw_from:
                        continue
                    sender_phone = f"+{raw_from}" if not raw_from.startswith("+") else raw_from

                    # Extraer texto del mensaje
                    text_obj = msg.get("text", {})
                    message_text = text_obj.get("body", "").strip()
                    if not message_text:
                        continue

                    # Lógica de enrutamiento:
                    # a) Convocatoria con 🎾
                    if "🎾" in message_text:
                        logger.info(f"Processing open match convocatoria from {sender_phone}")
                        await parse_open_match(
                            payload=WhatsAppConvocatoriaRequest(
                                raw_text=message_text,
                                sender_phone=sender_phone,
                            ),
                            db=db,
                        )

                    # b) Baja o cancelación de cupo
                    elif any(keyword in message_text.lower() for keyword in ["me bajo", "cancelo", "cancelar"]):
                        logger.info(f"Processing drop request from {sender_phone}")
                        
                        target_slot_id = None
                        # Verificar si el mensaje especifica el número o ID de slot
                        slot_match = re.search(r"(?:slot|turno|cancha|id)?\s*#?\s*(\d+)", message_text, re.IGNORECASE)
                        if slot_match:
                            target_slot_id = int(slot_match.group(1))
                        else:
                            # Buscar el primer slot activo donde este teléfono esté registrado
                            today = date.today()
                            slot_stmt = select(TimeSlot).where(TimeSlot.date >= today).order_by(TimeSlot.date, TimeSlot.start_time)
                            slots_res = await db.execute(slot_stmt)
                            cand_slots = slots_res.scalars().all()
                            norm_sender = normalize_phone(sender_phone)
                            
                            for s in cand_slots:
                                participants = to_participants_list(s.players_names)
                                for p in participants:
                                    if normalize_phone(p.get("phone")) == norm_sender or normalize_phone(p.get("host_phone")) == norm_sender:
                                        target_slot_id = s.id
                                        break
                                if target_slot_id:
                                    break

                        if target_slot_id:
                            try:
                                await drop_player(
                                    payload=DropPlayerRequest(
                                        slot_id=target_slot_id,
                                        sender_phone=sender_phone,
                                    ),
                                    db=db,
                                )
                                logger.info(f"Player {sender_phone} dropped successfully from slot {target_slot_id}")
                            except HTTPException as he:
                                logger.warning(f"Drop player rejected: {he.detail}")
                        else:
                            logger.warning(f"Could not find any active slot for {sender_phone} to drop")

    except Exception as e:
        logger.error(f"Error handling WhatsApp webhook: {e}", exc_info=True)

    # Responder siempre HTTP 200 a Meta
    return {"status": "received"}
