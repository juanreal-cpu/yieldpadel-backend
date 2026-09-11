import logging
import os
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.timezone import get_bogota_today
from app.services.whatsapp import (
    MESSAGES_CACHE,
    generate_availability_broadcast,
    generate_concierge_reply,
    generate_promo_urgent_broadcast,
    get_player_incidents,
    is_conversation_paused,
    is_transactional_message,
    log_conversation_message,
    normalize_phone,
    process_incoming_whatsapp_message,
    send_whatsapp_message,
    set_conversation_paused,
)
from app.models.whatsapp_conversation import WhatsAppConversation
from app.models.customer import Customer
from sqlalchemy import select

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

                    # Bandeja humana: registrar el mensaje entrante y respetar la pausa del bot si un asesor está atendiendo
                    paused = await is_conversation_paused(db, sender_phone)
                    await log_conversation_message(
                        db, sender_phone, message_text, direction="incoming",
                        player_name=sender_name, increment_unread=paused,
                    )
                    if paused:
                        continue

                    # Enrutar: mensajes con raquetas (🎾) o comandos rígidos ('voy'/'me bajo')
                    # van al flujo transaccional existente; el resto lo atiende el concierge IA.
                    if is_transactional_message(message_text):
                        reply_text = await process_incoming_whatsapp_message(
                            db=db,
                            sender_phone=sender_phone,
                            sender_name=sender_name,
                            raw_text=message_text,
                            quoted_text=quoted_text,
                            context=context,
                        )
                    else:
                        reply_text = await generate_concierge_reply(
                            message_text=message_text,
                            sender_phone=sender_phone,
                            db=db,
                            sender_name=sender_name,
                        )

                    if reply_text:
                        print(f"[WHATSAPP OUTGOING PREPARED]:\n{reply_text}\n")
                        await log_conversation_message(db, sender_phone, reply_text, direction="bot")
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


from app.services import get_club_config


class BroadcastRequest(BaseModel):
    target_date: Optional[str] = None
    group_id: Optional[str] = None
    sport: Optional[str] = "PADEL"


@router.post("/broadcast-availability")
async def broadcast_availability(
    payload: Optional[BroadcastRequest] = None,
    target_date: Optional[str] = Query(None),
    group_id: Optional[str] = Query(None),
    sport: Optional[str] = Query("PADEL"),
    db: AsyncSession = Depends(get_db),
):
    """
    Despacha el resumen de turnos libres del día al grupo de WhatsApp filtrado por deporte.
    Permite enviar parámetros por JSON body o Query params.
    """
    d_str = (payload.target_date if payload and payload.target_date else None) or target_date
    parsed_date = None
    if d_str:
        try:
            parsed_date = date.fromisoformat(d_str)
        except ValueError:
            parsed_date = get_bogota_today()
    else:
        parsed_date = get_bogota_today()

    cfg = get_club_config()
    default_group = cfg.get("whatsapp_broadcast_group") or os.getenv("WHATSAPP_BROADCAST_GROUP_ID", "+573132058547")
    target_group = (
        (payload.group_id if payload and payload.group_id else None)
        or group_id
        or default_group
    )
    sport_filter = ((payload.sport if payload and payload.sport else None) or sport or "PADEL").upper().strip()

    broadcast_text, total_slots = await generate_availability_broadcast(db, target_date=parsed_date, sport=sport_filter)
    sent_success = await send_whatsapp_message(to_phone=target_group, message_body=broadcast_text)

    return {
        "status": "sent" if sent_success else "simulated",
        "sport": sport_filter,
        "target_date": str(parsed_date),
        "total_available_slots": total_slots,
        "total_slots": total_slots,
        "recipient": target_group,
        "broadcast_text": broadcast_text,
    }


@router.post("/broadcast-promo-urgent")
async def broadcast_promo_urgent(
    payload: Optional[BroadcastRequest] = None,
    target_date: Optional[str] = Query(None),
    group_id: Optional[str] = Query(None),
    sport: Optional[str] = Query("PADEL"),
    db: AsyncSession = Depends(get_db),
):
    """
    Filtra slots vacíos críticos (< 3 horas) y envía alerta con descuento Flash (-25%) al grupo de WhatsApp.
    """
    d_str = (payload.target_date if payload and payload.target_date else None) or target_date
    parsed_date = None
    if d_str:
        try:
            parsed_date = date.fromisoformat(d_str)
        except ValueError:
            parsed_date = get_bogota_today()
    else:
        parsed_date = get_bogota_today()

    cfg = get_club_config()
    default_group = cfg.get("whatsapp_broadcast_group") or os.getenv("WHATSAPP_BROADCAST_GROUP_ID", "+573132058547")
    target_group = (
        (payload.group_id if payload and payload.group_id else None)
        or group_id
        or default_group
    )
    sport_filter = ((payload.sport if payload and payload.sport else None) or sport or "PADEL").upper().strip()

    broadcast_text, total_critical = await generate_promo_urgent_broadcast(db, target_date=parsed_date, sport=sport_filter)
    sent_success = await send_whatsapp_message(to_phone=target_group, message_body=broadcast_text)

    return {
        "status": "sent" if sent_success else "simulated",
        "sport": sport_filter,
        "target_date": str(parsed_date),
        "total_critical_slots": total_critical,
        "recipient": target_group,
        "broadcast_text": broadcast_text,
    }


@router.post("/notify-expiring-memberships")
async def notify_expiring_memberships(
    db: AsyncSession = Depends(get_db),
):
    """
    Consulta socios cuya membresía vence en 2 días o menos y despacha
    recordatorio personalizado por WhatsApp con opción de renovación inmediata.
    """
    today = get_bogota_today()
    target_threshold = today + timedelta(days=2)

    stmt = (
        select(Customer)
        .where(
            Customer.membership_end_date != None,  # noqa: E711
            Customer.membership_end_date >= today,
            Customer.membership_end_date <= target_threshold,
        )
    )
    res = await db.execute(stmt)
    customers = list(res.scalars().all())

    sent_count = 0
    notified = []

    for c in customers:
        if not c.phone:
            continue
        days_left = (c.membership_end_date - today).days
        plan_name = (c.membership_tier or "Socio").title()
        day_str = "hoy mismo" if days_left == 0 else ("mañana" if days_left == 1 else f"en {days_left} días")

        msg = (
            f"👑 *¡Hola {c.name}! Recordatorio de tu Membresía Capital Pádel Club* 🎾\n\n"
            f"Te recordamos que tu *Membresía {plan_name}* vence {day_str} ({c.membership_end_date.strftime('%d/%m/%Y')}).\n\n"
            "Para no perder tus beneficios exclusivos (horas preferenciales, clases en academia y bebida de cortesía), "
            "puedes renovarla directamente respondiendo a este mensaje o acercándote al counter del club.\n\n"
            "¡Será un gusto seguir compartiendo la pista contigo!"
        )

        success = await send_whatsapp_message(to_phone=c.phone, message_body=msg)
        await log_conversation_message(db, c.phone, msg, direction="bot", player_name=c.name)
        if success:
            sent_count += 1
        notified.append({"customer_id": c.id, "name": c.name, "phone": c.phone, "days_left": days_left})

    return {
        "status": "success",
        "notified_count": len(notified),
        "messages_sent": sent_count,
        "customers": notified,
    }


class SendManualMessageRequest(BaseModel):
    sender_phone: str
    message: str


class ReactivateBotRequest(BaseModel):
    sender_phone: str


@router.get("/conversations")
async def list_conversations(db: AsyncSession = Depends(get_db)):
    """Bandeja de conversaciones de WhatsApp para el panel de Chat Recepción del Dashboard."""
    res = await db.execute(select(WhatsAppConversation).order_by(WhatsAppConversation.updated_at.desc()))
    conversations = list(res.scalars().all())
    return {
        "total_unread": sum(c.unread_count or 0 for c in conversations),
        "conversations": [
            {
                "sender_phone": c.sender_phone,
                "player_name": c.player_name,
                "last_message": c.last_message,
                "unread_count": c.unread_count,
                "is_bot_paused": c.is_bot_paused,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in conversations
        ],
    }


@router.get("/conversations/{phone}/messages")
async def get_conversation_messages(phone: str, db: AsyncSession = Depends(get_db)):
    """Historial de mensajes de una conversación; marca los mensajes como leídos al abrirla e incluye mini-perfil CRM."""
    norm_phone = normalize_phone(phone)
    res = await db.execute(select(WhatsAppConversation).where(WhatsAppConversation.sender_phone == norm_phone))
    conv = res.scalars().first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada.")

    conv.unread_count = 0
    await db.commit()

    cres = await db.execute(select(Customer).where(Customer.phone == norm_phone))
    customer = cres.scalars().first()
    crm_profile = None
    if customer:
        days_left = None
        if customer.membership_end_date:
            days_left = (customer.membership_end_date - get_bogota_today()).days
        crm_profile = {
            "category": customer.category,
            "membership_tier": customer.membership_tier,
            "membership_days_left": days_left,
            "wallet_balance": customer.wallet_balance,
        }

    return {
        "sender_phone": conv.sender_phone,
        "player_name": conv.player_name,
        "is_bot_paused": conv.is_bot_paused,
        "crm_profile": crm_profile,
        "messages": [
            {"direction": m.direction, "body": m.body, "created_at": m.created_at.isoformat()}
            for m in conv.messages
        ],
    }


@router.post("/send-manual-message")
async def send_manual_message(
    payload: SendManualMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """El asesor de recepción responde manualmente desde el Dashboard; despacha vía Graph API de Meta."""
    sent = await send_whatsapp_message(to_phone=payload.sender_phone, message_body=payload.message)
    await log_conversation_message(db, payload.sender_phone, payload.message, direction="staff")
    return {"status": "sent" if sent else "simulated", "sender_phone": payload.sender_phone}


@router.post("/reactivate")
@router.post("/resume-bot")
async def reactivate_bot(
    payload: ReactivateBotRequest,
    db: AsyncSession = Depends(get_db),
):
    """Devuelve el control al Asistente IA (is_bot_paused=False) con el mensaje formal de cierre del asesor humano."""
    farewell = (
        "👋 *El asesor de recepción ha cerrado la consulta.* A partir de este momento nuestro Asistente IA "
        "vuelve a estar activo para colaborarte con disponibilidad, reservas y servicios del club. 🎾"
    )
    await set_conversation_paused(db, payload.sender_phone, False)
    await log_conversation_message(db, payload.sender_phone, farewell, direction="bot")
    await send_whatsapp_message(to_phone=payload.sender_phone, message_body=farewell)
    return {"status": "reactivated", "sender_phone": payload.sender_phone}



