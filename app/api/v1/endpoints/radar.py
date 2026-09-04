from datetime import datetime
import os
import re
from typing import List
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.schemas.radar import RadarBatchConsolidatedResponse, RadarUploadResponse
from app.services.radar_service import (
    RAW_DIR,
    parse_whatsapp_export,
    process_batch_files,
    process_batch_raw_folder,
)

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


@router.post(
    "/process-batch-folder",
    response_model=RadarBatchConsolidatedResponse,
    status_code=status.HTTP_200_OK,
    summary="Procesar por lote todos los historiales en data/radar/raw/",
    description="Escanea todos los archivos .txt acumulados en data/radar/raw/, extrae convocatorias multiclub, genera radar_master_consolidated.csv y devuelve métricas comparativas y globales.",
)
async def process_batch_folder_endpoint():
    result = process_batch_raw_folder(RAW_DIR)
    if result["total_records"] == 0 and result.get("status") == "no_files_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontraron archivos .txt en la carpeta data/radar/raw/. Por favor sube archivos primero.",
        )
    return result


@router.post(
    "/upload-multiple",
    response_model=RadarBatchConsolidatedResponse,
    status_code=status.HTTP_200_OK,
    summary="Subir y procesar múltiples historiales de WhatsApp en lote",
    description="Recibe una lista de archivos .txt de varios clubes de pádel, los guarda en data/radar/raw/, consolida los datos en radar_master_consolidated.csv y retorna KPIs por club y globales.",
)
async def upload_multiple_chats(
    files: List[UploadFile] = File(..., description="Lista de archivos .txt exportados de WhatsApp"),
):
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Se debe proporcionar al menos un archivo .txt.",
        )

    files_data: List[tuple] = []
    timestamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")

    for file in files:
        filename = file.filename or "chat.txt"
        if not filename.lower().endswith(".txt"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El archivo '{filename}' no tiene extensión .txt. Todos los archivos deben ser .txt.",
            )

        raw_bytes = await file.read()
        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content = raw_bytes.decode("latin-1", errors="replace")

        # Guardar en raw
        clean_name = re.sub(r"[^\w\.\-]", "_", filename)
        raw_filename = f"{timestamp_prefix}_{clean_name}"
        raw_path = os.path.join(RAW_DIR, raw_filename)
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(content)

        files_data.append((filename, content))

    try:
        result = process_batch_files(files_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error procesando el lote de chats: {str(e)}",
        )

    return result