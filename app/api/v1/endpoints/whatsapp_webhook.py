import logging
import os
import re
from datetime import date
from typing import Optional
import httpx
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


async def send_whatsapp_message(to_phone: str, message_body: str) -> bool:
    """
    Despacha un mensaje de texto saliente a la Graph API de Meta (WhatsApp Cloud API v20.0).
    Lee WHATSAPP_PHONE_NUMBER_ID y WHATSAPP_ACCESS_TOKEN de variables de entorno o settings.
    """
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", None)
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN") or getattr(settings, "WHATSAPP_ACCESS_TOKEN", None)

    clean_to = to_phone.lstrip("+").strip()

    if not phone_number_id or not access_token:
        logger.warning(
            "WHATSAPP_PHONE_NUMBER_ID o WHATSAPP_ACCESS_TOKEN no están configurados. "
            "No se puede despachar la respuesta a Meta Graph API."
        )
        print(f"[WHATSAPP OUTGOING] AVISO: Faltan credenciales en entorno (WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_ACCESS_TOKEN). No se envió a {clean_to}.")
        print(f"[WHATSAPP OUTGOING PREVIEW a {clean_to}]:\n{message_body}\n")
        return False

    url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": clean_to,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": message_body,
        },
    }

    print(f"[WHATSAPP OUTGOING] Despachando mensaje a {clean_to} vía Meta Graph API v20.0...")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.is_success:
                resp_json = resp.json()
                logger.info(f"WhatsApp outgoing message sent successfully to {clean_to}: {resp_json}")
                print(f"[WHATSAPP OUTGOING] ÉXITO enviando a {clean_to} (HTTP {resp.status_code}): {resp_json}")
                return True
            else:
                logger.error(
                    f"WhatsApp outgoing message error from Meta Graph API for {clean_to} (HTTP {resp.status_code}): {resp.text}"
                )
                print(f"[WHATSAPP OUTGOING] ERROR de Meta Graph API al enviar a {clean_to} (HTTP {resp.status_code}): {resp.text}")
                return False
    except Exception as exc:
        logger.error(f"Excepción al despachar mensaje WhatsApp a {clean_to}: {exc}", exc_info=True)
        print(f"[WHATSAPP OUTGOING] EXCEPCIÓN al despachar a {clean_to}: {exc}")
        return False


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
    Despacha la respuesta formateada al usuario de WhatsApp vía Meta Graph API.
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
                    raw_from = msg.get("from", "")
                    if not raw_from:
                        continue
                    sender_phone = f"+{raw_from}" if not raw_from.startswith("+") else raw_from

                    text_obj = msg.get("text", {})
                    message_text = text_obj.get("body", "").strip()
                    if not message_text:
                        continue

                    # Lógica de enrutamiento:
                    # a) Convocatoria con 🎾
                    if "🎾" in message_text:
                        logger.info(f"Processing open match convocatoria from {sender_phone}")
                        print(f"[WHATSAPP INCOMING] Convocatoria detectada con 🎾 de {sender_phone}")

                        convocatoria_res = await parse_open_match(
                            payload=WhatsAppConvocatoriaRequest(
                                raw_text=message_text,
                                sender_phone=sender_phone,
                            ),
                            db=db,
                        )

                        if convocatoria_res and convocatoria_res.whatsapp_reply:
                            reply_text = convocatoria_res.whatsapp_reply
                            print(f"[WHATSAPP PARSER] whatsapp_reply generado para {sender_phone}:\n{reply_text}\n")
                            # Despachar respuesta a Meta Graph API
                            await send_whatsapp_message(
                                to_phone=raw_from,
                                message_body=reply_text,
                            )

                    # b) Baja o cancelación de cupo
                    elif any(keyword in message_text.lower() for keyword in ["me bajo", "cancelo", "cancelar"]):
                        logger.info(f"Processing drop request from {sender_phone}")
                        print(f"[WHATSAPP INCOMING] Solicitud de baja/cancelación de {sender_phone}")
                        
                        target_slot_id = None
                        slot_match = re.search(r"(?:slot|turno|cancha|id)?\s*#?\s*(\d+)", message_text, re.IGNORECASE)
                        if slot_match:
                            target_slot_id = int(slot_match.group(1))
                        else:
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
                                drop_res = await drop_player(
                                    payload=DropPlayerRequest(
                                        slot_id=target_slot_id,
                                        sender_phone=sender_phone,
                                    ),
                                    db=db,
                                )
                                logger.info(f"Player {sender_phone} dropped successfully from slot {target_slot_id}")
                                print(f"[WHATSAPP DROP] Éxito al dar de baja a {sender_phone} del turno #{target_slot_id}: {drop_res.message}")
                                
                                drop_reply = (
                                    f"✅ *Baja confirmada en YieldPadel*\n"
                                    f"Tu cupo en el turno #{target_slot_id} ha sido liberado exitosamente.\n"
                                    f"El turno ha sido reabierto para otros jugadores."
                                )
                                await send_whatsapp_message(to_phone=raw_from, message_body=drop_reply)
                            except HTTPException as he:
                                logger.warning(f"Drop player rejected: {he.detail}")
                                print(f"[WHATSAPP DROP] Rechazado para {sender_phone}: {he.detail}")
                                error_reply = f"⚠️ *No se pudo procesar la baja*: {he.detail}"
                                await send_whatsapp_message(to_phone=raw_from, message_body=error_reply)
                        else:
                            logger.warning(f"Could not find any active slot for {sender_phone} to drop")
                            print(f"[WHATSAPP DROP] No se encontró ningún turno activo para {sender_phone}")

    except Exception as e:
        logger.error(f"Error handling WhatsApp webhook: {e}", exc_info=True)
        print(f"[WHATSAPP WEBHOOK ERROR] Error general procesando webhook: {e}")

    # Responder siempre HTTP 200 a Meta
    return {"status": "received"}
