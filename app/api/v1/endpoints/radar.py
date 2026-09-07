from datetime import datetime
import os
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.competitor import CompetitorClub
from app.schemas.radar import (
    CompetitorClubItem,
    RadarBatchConsolidatedResponse,
    RadarClubsResponse,
    RadarUploadResponse,
)
from app.services.radar_loader import ensure_competitor_clubs, normalize_text
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


@router.get(
    "/clubs",
    response_model=RadarClubsResponse,
    status_code=status.HTTP_200_OK,
    summary="Listado georreferenciado de clubes competidores y benchmarking de precios",
    description="Devuelve el radar de clubes de pádel en Colombia, filtrables por ciudad y franja (VALLE/PICO), con métricas comparativas frente a Capital Pádel Club.",
)
async def get_radar_clubs(
    city: str = Query("Bogota", description="Ciudad a filtrar ('Bogota', 'Medellin', 'Cali', 'all')"),
    franja: str = Query("PICO", description="Franja horaria ('PICO' o 'VALLE')"),
    db: AsyncSession = Depends(get_db),
):
    all_db_clubs = await ensure_competitor_clubs(db)
    franja_mode = franja.upper().strip()
    if franja_mode not in ["PICO", "VALLE"]:
        franja_mode = "PICO"

    city_clean = city.strip()
    norm_filter = normalize_text(city_clean)
    filter_all = norm_filter in ["all", "todos", "nacional", "colombia", ""]

    target_club = next((c for c in all_db_clubs if c.is_target_partner), None)
    if target_club:
        target_price = float(target_club.price_pico if franja_mode == "PICO" else target_club.price_valle)
    else:
        target_price = 120000.0 if franja_mode == "PICO" else 80000.0

    filtered_clubs = []
    competitor_prices = []

    for c in all_db_clubs:
        c_city_norm = normalize_text(c.city)
        if filter_all or norm_filter in c_city_norm:
            filtered_clubs.append(c)
            if not c.is_target_partner:
                c_price = float(c.price_pico if franja_mode == "PICO" else c.price_valle)
                competitor_prices.append(c_price)

    if competitor_prices:
        avg_competitor_price = round(sum(competitor_prices) / len(competitor_prices), 2)
    else:
        avg_competitor_price = target_price

    if avg_competitor_price > 0:
        competitiveness_pct = round(((avg_competitor_price - target_price) / avg_competitor_price) * 100, 1)
    else:
        competitiveness_pct = 0.0

    club_items: List[CompetitorClubItem] = []
    for c in filtered_clubs:
        curr_p = float(c.price_pico if franja_mode == "PICO" else c.price_valle)
        diff_cop = round(curr_p - target_price, 2)
        diff_pct = round(((curr_p - target_price) / curr_p) * 100, 1) if curr_p > 0 else 0.0

        club_items.append(
            CompetitorClubItem(
                id=c.id,
                name=c.name,
                city=c.city,
                zone=c.zone,
                address=c.address,
                latitude=c.latitude,
                longitude=c.longitude,
                courts_count=c.courts_count or 4,
                rating=c.rating or 4.5,
                phone=c.phone,
                website=c.website,
                price_valle=float(c.price_valle),
                price_pico=float(c.price_pico),
                current_price=curr_p,
                is_target_partner=bool(c.is_target_partner),
                diff_pct=diff_pct,
                diff_cop=diff_cop,
            )
        )

    return RadarClubsResponse(
        status="success",
        city=city_clean,
        franja=franja_mode,
        target_price=target_price,
        avg_competitor_price=avg_competitor_price,
        competitiveness_pct=competitiveness_pct,
        total_clubs=len(filtered_clubs),
        total_national_clubs=len(all_db_clubs),
        clubs=club_items,
    )