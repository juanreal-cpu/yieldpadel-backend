from datetime import datetime
import os
import re
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.schemas.radar import RadarUploadResponse
from app.services.radar_service import RAW_DIR, parse_whatsapp_export

router = APIRouter()


@router.post(
    "/upload-chat",
    response_model=RadarUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Procesar exportación .txt de WhatsApp (Batch Radar)",
    description="Recibe un historial de chat de WhatsApp (.txt), extrae todas las convocatorias con raqueta (🎾), genera KPIs consolidados y exporta un CSV procesado.",
)
async def upload_chat_export(
    file: UploadFile = File(..., description="Archivo de texto exportado de WhatsApp (.txt)"),
):
    # 1. Validar extensión .txt
    filename = file.filename or "whatsapp_chat.txt"
    if not filename.lower().endswith(".txt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de archivo no admitido. Se requiere un archivo .txt con la exportación del chat de WhatsApp.",
        )

    # 2. Leer contenido
    raw_bytes = await file.read()
    try:
        content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = raw_bytes.decode("latin-1", errors="replace")

    # 3. Guardar archivo crudo en data/radar/raw/
    timestamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_name = re.sub(r"[^\w\.\-]", "_", filename)
    raw_filename = f"{timestamp_prefix}_{clean_name}"
    raw_file_path = os.path.join(RAW_DIR, raw_filename)

    with open(raw_file_path, "w", encoding="utf-8") as f:
        f.write(content)

    # 4. Parsear y generar analítica y CSV
    try:
        result = parse_whatsapp_export(
            file_content=content,
            filename=filename,
            raw_saved_path=raw_file_path,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno procesando el historial de WhatsApp: {str(e)}",
        )

    return result