import logging
import os
from typing import Optional
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


async def download_whatsapp_media(media_url: str, mime_type: Optional[str] = None) -> bytes:
    """
    Descarga el archivo de audio de forma asíncrona usando httpx.
    - Meta Cloud API: envía headers={"Authorization": f"Bearer {token}"}.
      Maneja tanto la descarga de URL como la redirección firmada o endpoint de metadatos.
    - Twilio: envía HTTP Basic Auth (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) si la URL pertenece a Twilio.
    """
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN") or getattr(settings, "WHATSAPP_ACCESS_TOKEN", None)
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID") or getattr(settings, "TWILIO_ACCOUNT_SID", None)
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN") or getattr(settings, "TWILIO_AUTH_TOKEN", None)

    headers = {}
    auth = None

    is_twilio = "twilio.com" in media_url or (twilio_sid and twilio_token and "api.twilio" in media_url)
    is_meta = any(domain in media_url for domain in ["facebook.com", "meta.com", "whatsapp.net", "fbcdn.net"])

    if is_twilio and twilio_sid and twilio_token:
        auth = httpx.BasicAuth(twilio_sid, twilio_token)
        logger.info("[AUDIO DOWNLOAD] Usando Twilio HTTP Basic Auth para descarga de media.")
    elif access_token and (is_meta or not is_twilio):
        # Si es Meta o una URL directa privada de WhatsApp Cloud API, siempre inyectar el Bearer Token
        headers["Authorization"] = f"Bearer {access_token}"
        headers["User-Agent"] = "YieldPadel-WhatsApp/1.0"
        logger.info("[AUDIO DOWNLOAD] Inyectando Bearer Token de Meta para descarga de media.")

    async with httpx.AsyncClient(timeout=35.0, follow_redirects=True) as client:
        resp = await client.get(media_url, headers=headers, auth=auth)
        if resp.status_code != 200:
            logger.error(
                "[AUDIO DOWNLOAD FAIL] Status %s al descargar audio desde %s. Respuesta: %s",
                resp.status_code, media_url, resp.text[:300]
            )
        resp.raise_for_status()

        # Si Meta devuelve un JSON en lugar del binario, significa que es la respuesta de metadatos
        # que contiene la URL CDN firmada final ('url')
        content_type = resp.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                data = resp.json()
                cdn_download_url = data.get("url")
                if cdn_download_url:
                    logger.info("[AUDIO DOWNLOAD] Obtenida URL CDN de Meta, procediendo a descargar binario...")
                    # Para la URL de descarga CDN de Meta, también se requiere el Bearer token en los headers
                    cdn_headers = {"Authorization": f"Bearer {access_token}", "User-Agent": "YieldPadel-WhatsApp/1.0"} if access_token else {}
                    cdn_resp = await client.get(cdn_download_url, headers=cdn_headers)
                    cdn_resp.raise_for_status()
                    return cdn_resp.content
            except Exception as json_err:
                logger.error("[AUDIO DOWNLOAD JSON ERROR] Error parseando respuesta JSON de Meta: %s", json_err)

        return resp.content


async def fetch_media_url_from_id(media_id: str) -> Optional[str]:
    """
    Si el webhook entrega un media id (como msg['audio']['id']), consulta a Graph API para obtener la URL directa de descarga.
    """
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN") or getattr(settings, "WHATSAPP_ACCESS_TOKEN", None)
    if not access_token or not media_id:
        logger.warning("[FETCH MEDIA URL] No hay WHATSAPP_ACCESS_TOKEN o media_id está vacío: %s", media_id)
        return None

    url = f"https://graph.facebook.com/v20.0/{media_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "YieldPadel-WhatsApp/1.0",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.is_success:
                res_data = resp.json()
                return res_data.get("url")
            logger.error("[FETCH MEDIA URL ERROR] Error obteniendo media URL para id %s (status %s): %s", media_id, resp.status_code, resp.text)
    except Exception as e:
        logger.error("[FETCH MEDIA URL EXCEPTION] Excepción en fetch_media_url_from_id para %s: %s", media_id, e, exc_info=True)
    return None


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
