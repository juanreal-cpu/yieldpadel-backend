import logging
import os
import re
import traceback
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, cast, String

from app.core.database import get_db
from app.core.timezone import get_bogota_today, get_bogota_now
from app.models.slot import TimeSlot
import importlib
_yield_mod = importlib.import_module("app.services.yield")
calculate_recommended_price = _yield_mod.calculate_recommended_price
from app.services.whatsapp import (
    MESSAGES_CACHE,
    generate_availability_broadcast,
    generate_concierge_reply,
    generate_promo_urgent_broadcast,
    get_player_incidents,
    get_session,
    handle_human_wait_turn,
    handle_sport_and_booking_flow,
    is_conversation_paused,
    is_transactional_message,
    log_conversation_message,
    normalize_phone,
    process_incoming_whatsapp_message,
    sanitize_phone,
    send_whatsapp_message,
    set_conversation_paused,
)
from app.models.whatsapp_conversation import WhatsAppConversation
from app.models.customer import Customer

logger = logging.getLogger(__name__)

router = APIRouter()

VERIFY_TOKEN = "yieldpadel_secret_token_2026"
VOICEFLOW_TEXT_TRACE_TYPES = {"text", "speak"}
VOICEFLOW_FALLBACK_MESSAGE = (
    "Gracias por contactar a Capital Pádel Club. En este momento no pude completar tu consulta. "
    "Un asesor del club te atenderá a la mayor brevedad. Disculpa las molestias."
)
VOICEFLOW_MEMBERSHIP_CONTEXT = (
    "[CONTEXTO CLUB] Las membresías Tapia, Coello, Galán, Chingotto y Lebrón NO son requisito para jugar. "
    "Cualquier cliente, socio con plan vencido o jugador regular puede reservar y pagar tarifa estándar. "
    "La membresía solo otorga descuentos y cortesías.\n\n"
    "Mensaje del usuario: "
)
AVAILABILITY_INTENT_REGEX = re.compile(
    r"disponib|turnos?\s+libres?|canchas?\s+libres?|qu[eé]\s+horas?\s+hay|"
    r"despu[eé]s\s+de(?:\s+las?)?\s+\d|hoy\s+despu|hay\s+(?:cancha|turno|pista)|"
    r"quiero\s+jugar|reservar?\s+(?:cancha|pista|turno)|horarios?\s+(?:libres?|hoy)",
    re.IGNORECASE,
)
SLOT_SELECTION_REGEX = re.compile(r"^\s*([1-9])\s*$")
MEMBERSHIP_BLOCK_REGEX = re.compile(r"membres[ií]a|socio|tapia|coello|gal[aá]n|chingotto|lebr[oó]n", re.IGNORECASE)


def _extract_voiceflow_text_messages(traces) -> List[str]:
    """Recorre traces de Voiceflow y extrae mensajes tipo text o speak."""
    if isinstance(traces, dict):
        traces = traces.get("traces") or traces.get("trace") or []
    if not isinstance(traces, list):
        return []

    messages: List[str] = []
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        if str(trace.get("type") or "").lower() not in VOICEFLOW_TEXT_TRACE_TYPES:
            continue
        payload_obj = trace.get("payload") or {}
        if isinstance(payload_obj, dict):
            message = payload_obj.get("message")
            if message:
                messages.append(str(message))
        elif isinstance(payload_obj, str) and payload_obj.strip():
            messages.append(payload_obj)
    return messages


async def interact_with_voiceflow(sender_phone: str, message_text: str) -> List[str]:
    """Llama a la Dialog API de Voiceflow y retorna mensajes text/speak."""
    vf_api_key = (os.getenv("VOICEFLOW_API_KEY") or "").strip().replace('"', "").replace("'", "")
    clean_phone = str(sender_phone or "").replace("+", "").replace(" ", "").strip()
    clean_text = str(message_text or "").strip()
    url = f"https://general-runtime.voiceflow.com/state/user/{clean_phone}/interact"
    headers = {
        "Authorization": vf_api_key,
        "Content-Type": "application/json",
        "accept": "application/json",
        "versionID": os.getenv("VOICEFLOW_VERSION_ID", "main"),
    }
    payload = {
        "action": {
            "type": "text",
            "payload": clean_text,
        },
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            logger.error("[VOICEFLOW REJECT %s] Body: %s", resp.status_code, resp.text)
            resp.raise_for_status()
        try:
            data = resp.json()
        except Exception:
            logger.error("[VOICEFLOW JSON EXCEPT] body=%s", resp.text)
            logger.error(traceback.format_exc())
            return []
        return _extract_voiceflow_text_messages(data)


async def dispatch_voiceflow_replies(
    sender_phone: str,
    message_text: str,
    raw_from: str,
    db: Any = None,
    conversation_phone: Optional[str] = None,
) -> None:
    """
    Emergencia: Voiceflow → Meta. Sin persistencia SQLAlchemy/Supabase.
    """
    vf_text = str(message_text or "").strip()
    if MEMBERSHIP_BLOCK_REGEX.search(vf_text):
        vf_text = f"{VOICEFLOW_MEMBERSHIP_CONTEXT}{vf_text}"

    vf_messages: List[str] = []
    try:
        vf_messages = await interact_with_voiceflow(sender_phone, vf_text)
    except Exception as vf_err:
        logger.error("[VOICEFLOW TEXT EXCEPT] %s", vf_err)
        logger.error(traceback.format_exc())
        return

    for vf_msg in vf_messages or []:
        if not vf_msg:
            continue
        try:
            await send_whatsapp_message(to_phone=raw_from, message_body=vf_msg)
        except Exception as send_err:
            logger.error("[WHATSAPP SEND EXCEPT] %s", send_err)
            logger.error(traceback.format_exc())


def parse_availability_filters(message_text: str) -> dict:
    """Extrae fecha, hora mínima y deporte de un mensaje de disponibilidad en español."""
    text = message_text or ""
    today = get_bogota_today()
    target_date = today + timedelta(days=1) if re.search(r"\bma[ñn]ana\b", text, re.IGNORECASE) else today

    sport = "PADEL"
    sport_map = [
        ("PICKLEBALL", r"\bpickleball\b"),
        ("VOLLEYBALL", r"\bv[oó]ley(bol)?\b"),
        ("PILATES", r"\bpilates\b"),
        ("CONSOLE", r"\bconsola"),
        ("PADEL", r"\bp[aá]del\b"),
    ]
    for code, pattern in sport_map:
        if re.search(pattern, text, re.IGNORECASE):
            sport = code
            break

    after_time = None
    after_match = re.search(
        r"despu[eé]s\s+de(?:\s+las?)?\s+(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?",
        text,
        re.IGNORECASE,
    )
    hour_match = re.search(r"\b(?:a\s+las?\s+|desde\s+las?\s+)(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?", text, re.IGNORECASE)
    parsed = after_match or hour_match
    if parsed:
        hour = int(parsed.group(1))
        minute = int(parsed.group(2) or 0)
        meridiem = (parsed.group(3) or "").lower().replace(".", "")
        if "p" in meridiem and hour < 12:
            hour += 12
        elif "a" in meridiem and hour == 12:
            hour = 0
        elif not meridiem and 1 <= hour <= 7:
            hour += 12
        after_time = time(min(hour, 23), min(minute, 59))
    elif re.search(r"\bnoche\b", text, re.IGNORECASE):
        after_time = time(18, 0)
    elif re.search(r"\btarde\b", text, re.IGNORECASE):
        after_time = time(14, 0)

    return {"date": target_date, "after_time": after_time, "sport": sport}


def _slot_price_cop(slot: TimeSlot) -> int:
    try:
        yd = calculate_recommended_price(slot)
        return int(yd.get("recommended_price") or slot.total_price or 0)
    except Exception:
        return int(slot.total_price or slot.price_total_cop or 0)


async def lookup_available_slots(
    db: AsyncSession,
    sender_phone: Optional[str] = None,
    message_text: Optional[str] = None,
    target_date: Optional[date] = None,
    after_time: Optional[time] = None,
    sport: Optional[str] = "PADEL",
) -> dict:
    """Consulta time_slots AVAILABLE y arma JSON limpio + texto numerado para WhatsApp/Voiceflow."""
    filters = parse_availability_filters(message_text or "")
    d = target_date or filters["date"]
    after = after_time or filters["after_time"]
    sport_filter = (sport or filters["sport"] or "PADEL").upper().strip()

    stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.court))
        .where(TimeSlot.date == d, cast(TimeSlot.status, String) == "AVAILABLE")
        .order_by(TimeSlot.start_time.asc())
    )
    if sport_filter and sport_filter != "ALL":
        stmt = stmt.where(TimeSlot.sport_type == sport_filter)

    res = await db.execute(stmt)
    slots = list(res.scalars().all())

    now_bogota = get_bogota_now()
    if d == get_bogota_today():
        current = now_bogota.time()
        cutoff = after if after and after > current else current
        slots = [s for s in slots if s.start_time >= cutoff]
    elif after:
        slots = [s for s in slots if s.start_time >= after]

    options = []
    offered = {}
    for idx, slot in enumerate(slots[:8], start=1):
        court_name = slot.court.name if slot.court else "Cancha"
        price_cop = _slot_price_cop(slot)
        start_label = slot.start_time.strftime("%I:%M %p").lstrip("0")
        end_label = slot.end_time.strftime("%I:%M %p").lstrip("0")
        options.append({
            "index": idx,
            "slot_id": slot.id,
            "court": court_name,
            "start_time": slot.start_time.strftime("%H:%M"),
            "end_time": slot.end_time.strftime("%H:%M"),
            "start_label": start_label,
            "end_label": end_label,
            "price_cop": price_cop,
            "price_label": f"${price_cop:,}".replace(",", ".") + " COP",
            "sport": (slot.sport_type or sport_filter or "PADEL").upper(),
        })
        offered[idx] = slot.id

    if sender_phone:
        session = get_session(sender_phone)
        session["last_offered_slots"] = offered
        session["is_hold_search"] = True
        session["offered_slots_json"] = options

    after_label = after.strftime("%I:%M %p").lstrip("0") if after else None
    day_label = "hoy" if d == get_bogota_today() else d.strftime("%d/%m/%Y")
    if not options:
        whatsapp_text = (
            f"🎾 No encontré turnos *AVAILABLE* de {sport_filter.title()} para {day_label}"
            + (f" después de las {after_label}" if after_label else "")
            + ".\n\nPuedes consultar otra hora o fecha. Recuerda: *no necesitas membresía* para reservar; "
            "Tapia/Coello solo aplican descuentos."
        )
    else:
        lines = [
            f"{opt['index']}. {opt['court']} | {opt['start_label']} - {opt['end_label']} | {opt['price_label']}"
            for opt in options
        ]
        whatsapp_text = (
            f"🎾 *Turnos disponibles {day_label}*"
            + (f" (después de las {after_label})" if after_label else "")
            + f" — {sport_filter.title()}:\n\n"
            + "\n".join(lines)
            + "\n\nResponde con *1*, *2* o *3* para apartar el cupo. "
            "*No necesitas membresía para jugar*; los planes Tapia/Coello solo dan beneficios."
        )

    return {
        "status": "ok",
        "membership_required": False,
        "date": d.isoformat(),
        "sport": sport_filter,
        "after_time": after.strftime("%H:%M") if after else None,
        "options": options,
        "whatsapp_text": whatsapp_text,
    }


class SimulateWhatsAppMessage(BaseModel):
    sender_phone: str
    sender_name: Optional[str] = None
    raw_text: str
    quoted_text: Optional[str] = None
    context: Optional[dict] = None


class AvailabilityLookupRequest(BaseModel):
    sender_phone: Optional[str] = None
    message_text: Optional[str] = None
    date: Optional[str] = None
    after_time: Optional[str] = None
    sport: Optional[str] = "PADEL"


class SelectSlotRequest(BaseModel):
    sender_phone: str
    option: int
    sender_name: Optional[str] = None


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _safe_text_body(msg: dict) -> str:
    """Extrae el texto de Meta/Twilio sin KeyError/TypeError (text.body, button, interactive)."""
    payload = _as_dict(msg)
    text_obj = payload.get("text")
    if isinstance(text_obj, dict):
        return str(text_obj.get("body") or text_obj.get("text") or "").strip()
    if isinstance(text_obj, str):
        return text_obj.strip()
    button = _as_dict(payload.get("button"))
    if button.get("text") or button.get("payload"):
        return str(button.get("text") or button.get("payload") or "").strip()
    interactive = _as_dict(payload.get("interactive"))
    button_reply = _as_dict(interactive.get("button_reply"))
    list_reply = _as_dict(interactive.get("list_reply"))
    nested = (
        button_reply.get("title")
        or list_reply.get("title")
        or payload.get("body")
        or payload.get("caption")
        or ""
    )
    return str(nested or "").strip()


def _safe_sender_from_meta(msg: dict) -> Tuple[str, Optional[str]]:
    payload = _as_dict(msg)
    raw_from = str(payload.get("from") or payload.get("wa_id") or "").strip()
    sender_name = payload.get("_profile_name") or payload.get("profile_name")
    profile = _as_dict(payload.get("profile"))
    if not sender_name:
        sender_name = profile.get("name")
    return raw_from, (str(sender_name).strip() if sender_name else None)


# EMERGENCIA: persistencia Supabase/SQLAlchemy APAGADA en el webhook.
# No llamar _persist_inbox_immediately ni log_conversation_message desde receive_webhook.
# async def _persist_inbox_immediately(...):  # desactivado
#     await log_conversation_message(...)


async def _route_text_message(
    db: Any,
    sender_phone: str,
    sender_name: Optional[str],
    raw_from: str,
    message_text: str,
    msg: dict,
    msg_id: Optional[str],
) -> None:
    """Emergencia: texto limpio → Voiceflow → Meta. Sin SQLAlchemy."""
    clean_text = str(message_text or "").strip()
    if msg_id:
        MESSAGES_CACHE[msg_id] = clean_text
    logger.info("[WHATSAPP TEXT] %s (%s): '%s'", sender_phone, sender_name, clean_text)
    await dispatch_voiceflow_replies(
        sender_phone=str(raw_from or "").lstrip("+"),
        message_text=clean_text,
        raw_from=raw_from,
    )


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
async def receive_webhook(request: Request):
    """
    Emergencia texto-only: extrae from + text.body, llama Voiceflow y despacha a Meta.
    Sin persistencia SQLAlchemy. Sin audio/STT. Sin texto → HTTP 200.
    """
    try:
        body: Dict[str, Any] = {}
        form = None
        content_type = (request.headers.get("content-type") or "").lower()
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
        else:
            try:
                parsed = await request.json()
                body = parsed if isinstance(parsed, dict) else {}
            except Exception:
                try:
                    form = await request.form()
                except Exception:
                    form = None

        inbound_messages: List[dict] = []

        if form is not None and (form.get("From") or form.get("Body")):
            raw_from = str(form.get("From") or "").replace("whatsapp:", "").strip()
            body_text = str(form.get("Body") or "").strip()
            if raw_from and body_text:
                inbound_messages.append({
                    "from": raw_from,
                    "type": "text",
                    "text": {"body": body_text},
                })

        entries = body.get("entry") if isinstance(body, dict) else None
        if not isinstance(entries, list):
            entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for change in (entry.get("changes") or []):
                if not isinstance(change, dict):
                    continue
                value = change.get("value") if isinstance(change.get("value"), dict) else {}
                messages = value.get("messages")
                if messages is None:
                    messages = value.get("message")
                if isinstance(messages, dict):
                    messages = list(messages.values())
                if not isinstance(messages, list):
                    continue
                for msg in messages:
                    if isinstance(msg, dict):
                        inbound_messages.append(msg)

        logger.info("Incoming WhatsApp webhook: %s mensaje(s)", len(inbound_messages))

        for msg in inbound_messages:
            if not isinstance(msg, dict):
                continue
            raw_from = str(msg.get("from") or msg.get("wa_id") or "").strip()
            text_obj = msg.get("text") if isinstance(msg.get("text"), dict) else {}
            message_text = str((text_obj or {}).get("body") or "").strip()
            if not message_text:
                logger.info(
                    "[WHATSAPP] Ignorando mensaje sin texto (type=%s). HTTP 200.",
                    str(msg.get("type") or "unknown"),
                )
                continue
            if not raw_from:
                continue

            logger.info("[WHATSAPP TEXT] %s: '%s'", raw_from, message_text)
            vf_user_id = raw_from.lstrip("+")
            vf_messages: List[str] = []
            try:
                vf_messages = await interact_with_voiceflow(vf_user_id, message_text)
            except Exception as vf_err:
                logger.error("[VOICEFLOW TEXT EXCEPT] %s", vf_err)
                logger.error(traceback.format_exc())
                continue

            for vf_msg in vf_messages or []:
                if not vf_msg:
                    continue
                try:
                    await send_whatsapp_message(to_phone=raw_from, message_body=vf_msg)
                except Exception as send_err:
                    logger.error("[WHATSAPP SEND EXCEPT] %s", send_err)
                    logger.error(traceback.format_exc())

    except Exception as e:
        logger.error("[WHATSAPP WEBHOOK EXCEPT] %s", e)
        logger.error(traceback.format_exc())

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

    if is_transactional_message(payload.raw_text):
        reply_text = await process_incoming_whatsapp_message(
            db=db,
            sender_phone=payload.sender_phone,
            sender_name=payload.sender_name,
            raw_text=payload.raw_text,
            quoted_text=quoted_text,
            context=payload.context,
        )
    else:
        reply_text = await generate_concierge_reply(
            message_text=payload.raw_text,
            sender_phone=payload.sender_phone,
            db=db,
            sender_name=payload.sender_name,
        )
    return {
        "status": "processed",
        "sender_phone": payload.sender_phone,
        "sender_name": payload.sender_name,
        "quoted_text_received": bool(quoted_text),
        "reply": reply_text,
    }


@router.get("/availability")
async def get_slot_availability(
    phone: Optional[str] = Query(None),
    message_text: Optional[str] = Query(None),
    target_date: Optional[str] = Query(None, alias="date"),
    after_time: Optional[str] = Query(None),
    sport: Optional[str] = Query("PADEL"),
    db: AsyncSession = Depends(get_db),
):
    """JSON limpio de turnos AVAILABLE para Voiceflow (cancha, horario, precio, índice 1..n)."""
    parsed_date = None
    if target_date:
        try:
            parsed_date = date.fromisoformat(target_date)
        except ValueError:
            parsed_date = None
    parsed_after = None
    if after_time:
        try:
            parsed_after = datetime.strptime(after_time.strip(), "%H:%M").time()
        except ValueError:
            parsed_after = None
    return await lookup_available_slots(
        db,
        sender_phone=phone,
        message_text=message_text,
        target_date=parsed_date,
        after_time=parsed_after,
        sport=sport,
    )


@router.post("/availability")
async def post_slot_availability(
    payload: AvailabilityLookupRequest,
    db: AsyncSession = Depends(get_db),
):
    """Misma consulta de disponibilidad, pensada para API Steps de Voiceflow."""
    parsed_date = None
    if payload.date:
        try:
            parsed_date = date.fromisoformat(payload.date)
        except ValueError:
            parsed_date = None
    parsed_after = None
    if payload.after_time:
        try:
            parsed_after = datetime.strptime(payload.after_time.strip(), "%H:%M").time()
        except ValueError:
            parsed_after = None
    return await lookup_available_slots(
        db,
        sender_phone=payload.sender_phone,
        message_text=payload.message_text,
        target_date=parsed_date,
        after_time=parsed_after,
        sport=payload.sport or "PADEL",
    )


@router.post("/select-slot")
async def select_offered_slot(
    payload: SelectSlotRequest,
    db: AsyncSession = Depends(get_db),
):
    """Aparta de forma atómica el turno elegido (1, 2, 3...) almacenado en CONVERSATION_SESSIONS."""
    session = get_session(payload.sender_phone)
    reply_text = await handle_sport_and_booking_flow(
        db,
        payload.sender_phone,
        payload.sender_name,
        str(payload.option),
        session,
    )
    if not reply_text:
        raise HTTPException(status_code=404, detail="No hay turnos ofertados en sesión para ese número.")
    return {
        "status": "ok",
        "membership_required": False,
        "sender_phone": payload.sender_phone,
        "option": payload.option,
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


class TargetedBroadcastRequest(BaseModel):
    mode: str = "AVAILABILITY"  # "AVAILABILITY" | "FLASH_PROMO"
    target_phones: List[str]
    custom_message: Optional[str] = None
    slot_id: Optional[int] = None
    sport: Optional[str] = "PADEL"
    target_date: Optional[str] = None


@router.post("/broadcast-targeted")
async def broadcast_targeted(
    payload: TargetedBroadcastRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Despacha difusión de WhatsApp con filtro de audiencia a una lista de números seleccionados.
    Permite enviar mensaje personalizado, disponibilidad de turnos o remate flash (-25%).
    """
    if not payload.target_phones:
        raise HTTPException(status_code=400, detail="Debe especificar al menos un teléfono de destino.")

    # 1. Determinar el mensaje a despachar
    broadcast_text = (payload.custom_message or "").strip()
    if not broadcast_text:
        parsed_date = None
        if payload.target_date:
            try:
                parsed_date = date.fromisoformat(payload.target_date)
            except ValueError:
                parsed_date = get_bogota_today()
        else:
            parsed_date = get_bogota_today()

        sport_val = (payload.sport or "PADEL").upper().strip()

        if payload.mode == "FLASH_PROMO":
            if payload.slot_id:
                # Generar mensaje específico para el slot_id indicado
                stmt = select(TimeSlot).options(selectinload(TimeSlot.court)).where(TimeSlot.id == payload.slot_id)
                res = await db.execute(stmt)
                slot = res.scalars().first()
                if slot:
                    c_name = slot.court.name if slot.court else "Cancha"
                    st = slot.start_time.strftime("%I:%M%p").lower()
                    et = slot.end_time.strftime("%I:%M%p").lower()
                    orig_p = f"${int(slot.total_price or 80000):,}".replace(",", ".")
                    disc_p = f"${int((slot.total_price or 80000) * 0.75):,}".replace(",", ".")
                    broadcast_text = (
                        f"⚡ *¡REMATE FLASH YIELD -25% EN CAPITAL PÁDEL CLUB!* ⚡\n\n"
                        f"🚨 *¡Turno Liberado de Última Hora!*\n"
                        f"📍 {c_name} | ⌚ *{st} - {et}* ({slot.date.strftime('%d/%m/%Y')})\n"
                        f"💰 Tarifa Regular: ~{orig_p}~ ➔ *PROMO FLASH: {disc_p} COP* (-25% OFF)\n\n"
                        f"🏃‍♂️ Responde de inmediato con *'VOY'* a este chat para asegurar tu pista."
                    )
            if not broadcast_text:
                broadcast_text, _ = await generate_promo_urgent_broadcast(db, target_date=parsed_date, sport=sport_val)
        else:
            broadcast_text, _ = await generate_availability_broadcast(db, target_date=parsed_date, sport=sport_val)

    # 2. Despachar a cada teléfono de la lista
    sent_count = 0
    clean_phones = []
    for ph in payload.target_phones:
        s_phone = sanitize_phone(ph)
        if s_phone and s_phone not in clean_phones:
            clean_phones.append(s_phone)

    for ph in clean_phones:
        try:
            ok = await send_whatsapp_message(to_phone=ph, message_body=broadcast_text)
            await log_conversation_message(db, ph, broadcast_text, direction="bot")
            if ok:
                sent_count += 1
        except Exception as exc:
            logger.warning(f"Fallo al despachar difusión a {ph}: {exc}")

    return {
        "status": "ok",
        "sent_count": len(clean_phones),
        "successful_deliveries": sent_count,
        "message": f"Difusión entregada exitosamente a {len(clean_phones)} clientes.",
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


@router.get("/inbox/pending-count")
async def get_inbox_pending_count(db: AsyncSession = Depends(get_db)):
    """
    Cuenta en la base de datos todas las conversaciones activas donde
    is_bot_paused == True o unread_count > 0.
    """
    from sqlalchemy import func, or_
    stmt = (
        select(func.count(WhatsAppConversation.id))
        .where(
            or_(
                WhatsAppConversation.is_bot_paused == True,  # noqa: E712
                WhatsAppConversation.unread_count > 0,
            )
        )
    )
    res = await db.execute(stmt)
    total = res.scalar() or 0
    return {"pending_count": int(total)}


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


@router.get("/challenges-lookup", summary="Lookup de retos y partidos para WhatsApp")
async def whatsapp_challenges_lookup_route(
    phone: Optional[str] = Query(None, description="Teléfono del cliente que consulta"),
    db: AsyncSession = Depends(get_db),
):
    """Retorna duelos pendientes y partidos confirmados 4/4 para pronóstico y apuestas."""
    from app.api.v1.endpoints.challenges import challenges_lookup
    return await challenges_lookup(phone=phone, db=db)




