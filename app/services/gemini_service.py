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
    Si la URL es de Meta Graph API o similar, se inyecta el token Bearer correspondiente.
    """
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN") or getattr(settings, "WHATSAPP_ACCESS_TOKEN", None)
    headers = {}
    if access_token and ("facebook.com" in media_url or "meta.com" in media_url or "whatsapp.net" in media_url):
        headers["Authorization"] = f"Bearer {access_token}"

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # En WhatsApp Cloud API, si se recibe media_id o url de media de Graph API,
        # primero puede ser un endpoint de metadatos que retorna url descargable
        resp = await client.get(media_url, headers=headers)
        resp.raise_for_status()

        # Si el content-type retornado es JSON, Meta devolvió el objeto Media con la url final
        content_type = resp.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            data = resp.json()
            download_url = data.get("url")
            if download_url:
                resp = await client.get(download_url, headers=headers)
                resp.raise_for_status()

        return resp.content


async def fetch_media_url_from_id(media_id: str) -> Optional[str]:
    """
    Si el webhook entrega un media id (como msg['audio']['id']), consulta a Graph API para obtener la URL directa de descarga.
    """
    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN") or getattr(settings, "WHATSAPP_ACCESS_TOKEN", None)
    if not access_token or not media_id:
        return None

    url = f"https://graph.facebook.com/v20.0/{media_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.is_success:
                return resp.json().get("url")
            logger.error("Error obteniendo media URL para %s: %s", media_id, resp.text)
    except Exception as e:
        logger.error("Excepción en fetch_media_url_from_id para %s: %s", media_id, e, exc_info=True)
    return None


async def transcribe_audio_with_gemini(
    audio_bytes: bytes,
    mime_type: Optional[str] = "audio/ogg",
) -> str:
    """
    Envía el audio en bytes a gemini-1.5-flash y devuelve la transcripción literal en texto plano.
    """
    api_key = os.getenv("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        raise ValueError("GEMINI_API_KEY no configurado en el entorno.")
    if not genai:
        raise RuntimeError("Librería google.generativeai no instalada.")

    genai.configure(api_key=api_key)

    # Limpiar mime_type si viene con parámetros (ej: audio/ogg; codecs=opus)
    effective_mime = "audio/ogg"
    if mime_type:
        effective_mime = mime_type.split(";")[0].strip().lower()

    # Si es audio/ogg o no reconocido, Gemini soporta audio/ogg, audio/mp3, audio/wav, audio/aac, audio/m4a, etc.
    part = {
        "mime_type": effective_mime,
        "data": audio_bytes,
    }

    model = genai.GenerativeModel(model_name="gemini-1.5-flash")
    response = await model.generate_content_async(
        contents=[TRANSCRIPTION_PROMPT, part]
    )

    transcription = (getattr(response, "text", None) or "").strip()
    if not transcription:
        raise ValueError("Gemini retornó transcripción vacía.")

    return transcription
