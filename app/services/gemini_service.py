import logging
import os
from typing import Optional, Tuple
from urllib.parse import urljoin
import httpx

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from app.core.config import settings

logger = logging.getLogger("yieldpadel.gemini_service")

# Mensaje amigable cuando falla la descarga o la transcripción de una nota de voz
AUDIO_PROCESSING_ERROR_MESSAGE = (
    "Lo siento, tuve un problema procesando tu nota de voz 😅. ¿Podrías escribírmelo por favor?"
)

TRANSCRIPTION_PROMPT = (
    "Transcribe exactamente lo que dice el usuario en este audio en español, "
    "sin agregar comentarios adicionales, resúmenes ni saltos de línea extra."
)


def _whatsapp_access_token() -> Optional[str]:
    return (
        os.getenv("WHATSAPP_ACCESS_TOKEN")
        or os.getenv("WHATSAPP_TOKEN")
        or getattr(settings, "WHATSAPP_ACCESS_TOKEN", None)
    )


def _graph_api_version() -> str:
    raw = (os.getenv("WHATSAPP_GRAPH_API_VERSION") or "v20.0").strip()
    return raw if raw.startswith("v") else f"v{raw}"


def _meta_auth_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "YieldPadel-WhatsApp/1.0",
    }


async def _get_preserving_bearer(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    step_label: str,
) -> httpx.Response:
    """GET que reenvía el Bearer en cada redirect (httpx lo elimina en hops cross-host)."""
    current = url
    for _ in range(6):
        resp = await client.get(current, headers=headers)
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location")
            if not location:
                logger.error("[%s REJECT %s] Redirect sin Location. Body: %s", step_label, resp.status_code, resp.text)
                resp.raise_for_status()
            current = urljoin(current, location)
            continue
        if resp.status_code != 200:
            logger.error("[%s REJECT %s] Body: %s", step_label, resp.status_code, resp.text)
        return resp
    raise ValueError(f"{step_label}: demasiados redirects al descargar media de WhatsApp")


async def download_whatsapp_media(media_url: str, mime_type: Optional[str] = None) -> bytes:
    """
    Paso 2 del flujo Meta: GET a la URL temporal del media con Bearer.
    Conserva Authorization en redirects al CDN (lookaside.fbsbx.com / mmg.whatsapp.net).
    """
    access_token = _whatsapp_access_token()
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID") or getattr(settings, "TWILIO_ACCOUNT_SID", None)
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN") or getattr(settings, "TWILIO_AUTH_TOKEN", None)

    headers = {}
    auth = None
    is_twilio = "twilio.com" in media_url or (twilio_sid and twilio_token and "api.twilio" in media_url)

    if is_twilio and twilio_sid and twilio_token:
        auth = httpx.BasicAuth(twilio_sid, twilio_token)
        logger.info("[AUDIO DOWNLOAD] Usando Twilio HTTP Basic Auth para descarga de media.")
        async with httpx.AsyncClient(timeout=35.0, follow_redirects=True) as client:
            resp = await client.get(media_url, auth=auth)
            if resp.status_code != 200:
                logger.error("[WHATSAPP MEDIA STEP2 REJECT %s] Body: %s", resp.status_code, resp.text)
            resp.raise_for_status()
            return resp.content

    if not access_token:
        raise ValueError("Falta WHATSAPP_ACCESS_TOKEN para descargar media de Meta.")

    headers = _meta_auth_headers(access_token)
    async with httpx.AsyncClient(timeout=35.0, follow_redirects=False) as client:
        resp = await _get_preserving_bearer(client, media_url, headers, "WHATSAPP MEDIA STEP2")
        if resp.status_code != 200:
            logger.error("[WHATSAPP MEDIA STEP2 REJECT %s] Body: %s", resp.status_code, resp.text)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            data = resp.json()
            cdn_download_url = data.get("url")
            if not cdn_download_url:
                logger.error("[WHATSAPP MEDIA STEP2 REJECT] JSON sin url. Body: %s", resp.text)
                raise ValueError("Meta devolvió JSON sin URL de descarga de media.")
            cdn_resp = await _get_preserving_bearer(client, cdn_download_url, headers, "WHATSAPP MEDIA STEP2")
            if cdn_resp.status_code != 200:
                logger.error("[WHATSAPP MEDIA STEP2 REJECT %s] Body: %s", cdn_resp.status_code, cdn_resp.text)
            cdn_resp.raise_for_status()
            return cdn_resp.content
        return resp.content


async def fetch_media_url_from_id(media_id: str) -> Optional[str]:
    """Paso 1: GET Graph API /{media_id} y extrae el campo url."""
    access_token = _whatsapp_access_token()
    if not access_token or not media_id:
        logger.warning("[FETCH MEDIA URL] No hay WHATSAPP_ACCESS_TOKEN o media_id está vacío: %s", media_id)
        return None

    url = f"https://graph.facebook.com/{_graph_api_version()}/{media_id}"
    headers = _meta_auth_headers(access_token)
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.error("[WHATSAPP MEDIA STEP1 REJECT %s] Body: %s", resp.status_code, resp.text)
                return None
            return (resp.json() or {}).get("url")
    except Exception as e:
        logger.error("[FETCH MEDIA URL EXCEPTION] Excepción en fetch_media_url_from_id para %s: %s", media_id, e, exc_info=True)
    return None


async def download_whatsapp_media_by_id(media_id: str) -> Tuple[bytes, Optional[str]]:
    """
    Flujo obligatorio de 2 pasos de WhatsApp Cloud API:
    1) GET https://graph.facebook.com/{version}/{media_id} + Bearer → extrae `url`
    2) GET a esa `url` + Bearer (también en redirects) → bytes del audio
    """
    access_token = _whatsapp_access_token()
    if not access_token:
        raise ValueError("Falta WHATSAPP_ACCESS_TOKEN / WHATSAPP_TOKEN para descargar media de Meta.")
    if not media_id:
        raise ValueError("media_id vacío: no se puede resolver el audio de WhatsApp.")

    headers = _meta_auth_headers(access_token)
    meta_url = f"https://graph.facebook.com/{_graph_api_version()}/{media_id}"

    async with httpx.AsyncClient(timeout=35.0, follow_redirects=False) as client:
        resp1 = await client.get(meta_url, headers=headers)
        if resp1.status_code != 200:
            logger.error("[WHATSAPP MEDIA STEP1 REJECT %s] Body: %s", resp1.status_code, resp1.text)
            resp1.raise_for_status()

        payload = resp1.json() or {}
        download_url = payload.get("url")
        mime_type = payload.get("mime_type")
        if not download_url:
            logger.error("[WHATSAPP MEDIA STEP1 REJECT] JSON sin url. Body: %s", resp1.text)
            raise ValueError(f"Meta no devolvió url para media_id={media_id}")

        logger.info("[WHATSAPP MEDIA STEP1] media_id=%s url=%s", media_id, download_url[:80])
        resp2 = await _get_preserving_bearer(client, download_url, headers, "WHATSAPP MEDIA STEP2")
        if resp2.status_code != 200:
            logger.error("[WHATSAPP MEDIA STEP2 REJECT %s] Body: %s", resp2.status_code, resp2.text)
            resp2.raise_for_status()
        return resp2.content, mime_type


async def transcribe_audio_with_gemini(
    audio_bytes: bytes,
    mime_type: Optional[str] = "audio/ogg; codecs=opus",
) -> str:
    """
    Envía el audio en bytes a gemini-1.5-flash y devuelve la transcripción literal en texto plano.
    Soporta explícitamente el formato nativo de WhatsApp 'audio/ogg; codecs=opus' así como 'audio/ogg'.
    """
    api_key = os.getenv("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise ValueError("GEMINI_API_KEY no configurado en el entorno.")
    if not genai:
        raise RuntimeError("Librería google.generativeai no instalada.")

    genai.configure(api_key=api_key)

    # Limpieza o preservación inteligente del mime_type
    effective_mime = (mime_type or "audio/ogg; codecs=opus").strip()

    part = {
        "mime_type": effective_mime,
        "data": audio_bytes,
    }

    model = genai.GenerativeModel(model_name="gemini-1.5-flash")
    try:
        response = await model.generate_content_async(
            contents=[TRANSCRIPTION_PROMPT, part]
        )
    except Exception as gemini_err:
        logger.warning(
            "[GEMINI RETRY] Falló llamada con mime '%s': %s. Reintentando con 'audio/ogg' estándar...",
            effective_mime, gemini_err
        )
        # Fallback a mime estándar si el backend de Gemini rechaza el parámetro codecs
        part["mime_type"] = "audio/ogg"
        response = await model.generate_content_async(
            contents=[TRANSCRIPTION_PROMPT, part]
        )

    transcription = (getattr(response, "text", None) or "").strip()
    if not transcription:
        raise ValueError("Gemini retornó transcripción vacía.")

    return transcription
