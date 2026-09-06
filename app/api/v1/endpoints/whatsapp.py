import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.whatsapp import (
    MESSAGES_CACHE,
    get_player_incidents,
    normalize_phone,
    process_incoming_whatsapp_message,
    send_whatsapp_message,
)

logger = logging.getLogger(__name__)

router = APIRouter()

VERIFY_TOKEN = "yieldpadel_secret_token_2026"


class SimulateWhatsAppMessage(BaseModel):
    sender_phone: str
    sender_name: Optional[str] = None
    raw_text: str
    quoted_text: Optional[str] = None
    context: Optional[dict] = None


@router.get("/webhook")
async def verify_webhook(request: Request):
    """Verificación de webhook requerida por Meta Cloud API."""
    hub_mode = request.query_params.get("hub.mode")
    hub_token = request.query_params.get("hub.verify_token")
    hub_challenge = request.query_params.get("hub.challenge")

    if hub_mode == "subscribe" and hub_token == VERIFY_TOKEN:
        return PlainTextResponse(content=str(hub_challenge), status_code=200)

    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Recepción de eventos de WhatsApp Cloud API (Meta).
    Extrae contexto de mensaje citado ('context') y despacha intenciones con mutabilidad estricta.
    """
    try:
        body = await request.json()
        logger.info(f"Incoming WhatsApp webhook payload: {body}")

        entries = body.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                contacts = value.get("contacts", [])
                contact_map = {}
                for c in contacts:
                    wa_id = c.get("wa_id")
                    profile_name = c.get("profile", {}).get("name")
                    if wa_id and profile_name:
                        contact_map[wa_id] = profile_name

                messages = value.get("messages", [])
                for msg in messages:
                    msg_id = msg.get("id")
                    raw_from = msg.get("from", "")
                    if not raw_from:
                        continue
                    sender_phone = f"+{raw_from}" if not raw_from.startswith("+") else raw_from
                    sender_name = contact_map.get(raw_from) or contact_map.get(raw_from.lstrip("+"))

                    text_obj = msg.get("text", {})
                    message_text = text_obj.get("body", "").strip()
                    if not message_text:
                        continue

                    # Guardar mensaje entrante en cache si tiene ID
                    if msg_id:
                        MESSAGES_CACHE[msg_id] = message_text

                    # Extracción precisa del contexto de cita ('context')
                    context = msg.get("context", {})
                    quoted_text = None
                    if context:
                        quoted_text = (
                            context.get("quoted_message", {}).get("body")
                            or context.get("quoted_message", {}).get("text", {}).get("body")
                            or context.get("body")
                            or context.get("text")
                        )
                        if not quoted_text and context.get("id"):
                            quoted_text = MESSAGES_CACHE.get(context.get("id"))

                    print(f"[WHATSAPP INCOMING] Mensaje de {sender_phone} ({sender_name}): '{message_text}' | Quoted: {bool(quoted_text)}")

                    # Procesar mensaje a través del servicio con contexto de cita
                    reply_text = await process_incoming_whatsapp_message(
                        db=db,
                        sender_phone=sender_phone,
                        sender_name=sender_name,
                        raw_text=message_text,
                        quoted_text=quoted_text,
                        context=context,
                    )

                    if reply_text:
                        print(f"[WHATSAPP OUTGOING PREPARED]:\n{reply_text}\n")
                        await send_whatsapp_message(
                            to_phone=raw_from,
                            message_body=reply_text,
                        )

    except Exception as e:
        logger.error(f"Error handling WhatsApp webhook: {e}", exc_info=True)
        print(f"[WHATSAPP WEBHOOK ERROR] Error procesando webhook: {e}")

    return {"status": "received"}


@router.post("/simulate")
async def simulate_incoming_message(
    payload: SimulateWhatsAppMessage,
    db: AsyncSession = Depends(get_db),
):
    """
    Endpoint de simulación para pruebas del flujo de WhatsApp con soporte de mensajes citados.
    """
    # Resolver quoted_text si viene en context
    quoted_text = payload.quoted_text
    if not quoted_text and payload.context:
        ctx = payload.context
        quoted_text = (
            ctx.get("quoted_message", {}).get("body")
            or ctx.get("quoted_message", {}).get("text", {}).get("body")
            or ctx.get("body")
            or ctx.get("text")
            or (MESSAGES_CACHE.get(ctx.get("id")) if ctx.get("id") else None)
        )

    reply_text = await process_incoming_whatsapp_message(
        db=db,
        sender_phone=payload.sender_phone,
        sender_name=payload.sender_name,
        raw_text=payload.raw_text,
        quoted_text=quoted_text,
        context=payload.context,
    )
    return {
        "status": "processed",
        "sender_phone": payload.sender_phone,
        "sender_name": payload.sender_name,
        "quoted_text_received": bool(quoted_text),
        "reply": reply_text,
    }


@router.get("/player-history/{phone}")
async def get_player_history(
    phone: str,
    db: AsyncSession = Depends(get_db),
):
    """Consulta el historial de incidencias y bajas tardías de un jugador."""
    norm_phone = normalize_phone(phone)
    incidents = await get_player_incidents(db, norm_phone)
    return {
        "phone": norm_phone,
        "total_incidents": len(incidents),
        "incidents": incidents,
    }

