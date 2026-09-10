from datetime import datetime

from typing import Optional, List
from sqlalchemy import text





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


# ==========================================
# INTELIGENCIA DE MERCADO (RADAR & PROSPECCIÓN)
# ==========================================

@router.get("/market-rates")
async def get_market_rates(
    is_weekend: Optional[bool] = Query(None, description="Filtrar por fin de semana (true) o entre semana (false)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Retorna precios promedio y tasa de ocupación de competidores por franja horaria estándar.
    """
    base_query = """
        SELECT 
            standard_time_slot,
            is_weekend,
            ROUND(AVG(price_per_player), 0) AS avg_price_per_player,
            COUNT(*) AS total_matches,
            SUM(CASE WHEN is_closed THEN 1 ELSE 0 END) AS closed_matches,
            ROUND((SUM(CASE WHEN is_closed THEN 1 ELSE 0 END)::numeric / NULLIF(COUNT(*), 0)) * 100, 1) AS occupancy_rate_pct
        FROM v_competitor_market_clean
        WHERE standard_time_slot != 'Otra Franja' AND price_per_player > 0
    """
    params = {}
    if is_weekend is not None:
        base_query += " AND is_weekend = :is_weekend"
        params["is_weekend"] = is_weekend

    base_query += """
        GROUP BY standard_time_slot, is_weekend
        ORDER BY standard_time_slot ASC
    """

    res = await db.execute(text(base_query), params)
    rows = res.fetchall()

    return [
        {
            "time_slot": r[0],
            "is_weekend": r[1],
            "avg_price_per_player": float(r[2] or 0),
            "total_matches": r[3],
            "closed_matches": r[4],
            "occupancy_rate_pct": float(r[5] or 0),
        }
        for r in rows
    ]


@router.get("/price-comparison")
async def get_price_comparison(
    db: AsyncSession = Depends(get_db),
):
    """
    Compara la tarifa de Capital Pádel contra el promedio del resto de la competencia
    por franja horaria estándar y tipo de día.
    """
    query = text(
        """
        SELECT
            standard_time_slot,
            is_weekend,
            ROUND(MAX(CASE WHEN LOWER(CAST(club_name AS TEXT)) LIKE '%capital%' AND LOWER(CAST(club_name AS TEXT)) LIKE '%padel%' THEN price_per_player END), 2) AS tarifa_capital_padel,
            ROUND(AVG(CASE WHEN NOT (LOWER(CAST(club_name AS TEXT)) LIKE '%capital%' AND LOWER(CAST(club_name AS TEXT)) LIKE '%padel%') THEN price_per_player END), 2) AS tarifa_promedio_competencia,
            ROUND(
                MAX(CASE WHEN LOWER(CAST(club_name AS TEXT)) LIKE '%capital%' AND LOWER(CAST(club_name AS TEXT)) LIKE '%padel%' THEN price_per_player END)
                - AVG(CASE WHEN NOT (LOWER(CAST(club_name AS TEXT)) LIKE '%capital%' AND LOWER(CAST(club_name AS TEXT)) LIKE '%padel%') THEN price_per_player END),
                2
            ) AS brecha_precio_cop
        FROM v_competitor_market_clean
        WHERE price_per_player IS NOT NULL AND price_per_player > 0
        GROUP BY standard_time_slot, is_weekend
        ORDER BY standard_time_slot ASC, is_weekend ASC
        """
    )

    res = await db.execute(query)
    rows = res.mappings().all()

    data = []
    for row in rows:
        capital = row["tarifa_capital_padel"]
        competition = row["tarifa_promedio_competencia"]
        data.append(
            {
                "standard_time_slot": row["standard_time_slot"],
                "is_weekend": bool(row["is_weekend"]),
                "tarifa_capital_padel": float(capital) if capital is not None else None,
                "tarifa_promedio_competencia": float(competition) if competition is not None else None,
                "brecha_precio_cop": float(row["brecha_precio_cop"]) if row["brecha_precio_cop"] is not None else None,
            }
        )

    return data


@router.get("/clubs-occupancy")
async def get_clubs_occupancy(
    db: AsyncSession = Depends(get_db),
):
    """
    Calcula el porcentaje de convocatorias cerradas por cada club competidor.
    """
    query = text(
        """
        SELECT
            club_name,
            COUNT(*) AS total_convocatorias,
            SUM(CASE WHEN is_closed THEN 1 ELSE 0 END) AS partidos_llenos,
            ROUND(
                (SUM(CASE WHEN is_closed THEN 1 ELSE 0 END) * 100.0) / NULLIF(COUNT(*), 0),
                2
            ) AS ocupacion_pct
        FROM v_competitor_market_clean
        WHERE club_name IS NOT NULL AND TRIM(club_name) <> ''
        GROUP BY club_name
        ORDER BY ocupacion_pct DESC, total_convocatorias DESC
        """
    )

    res = await db.execute(query)
    rows = res.mappings().all()

    return [
        {
            "club_name": row["club_name"],
            "total_convocatorias": int(row["total_convocatorias"] or 0),
            "partidos_llenos": int(row["partidos_llenos"] or 0),
            "ocupacion_pct": float(row["ocupacion_pct"] or 0),
        }
        for row in rows
    ]


@router.get("/top-recurring-players")
async def get_top_recurring_players(
    detected_category: Optional[str] = Query(None, description="Ejemplo: 4ta, 3ra, 5ta"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Identifica los jugadores más activos del mercado y clasifica su comportamiento.
    """
    query = text(
        """
        WITH player_market_stats AS (
            SELECT
                mp.player_name,
                mp.frequent_club,
                mp.detected_category,
                mp.total_matches_played,
                COUNT(DISTINCT LOWER(TRIM(CAST(v.club_name AS TEXT)))) AS total_clubes_distintos
            FROM market_player_profiles mp
            LEFT JOIN v_competitor_market_clean v
                ON v.players IS NOT NULL
                AND LOWER(CAST(v.players AS TEXT)) LIKE '%' || LOWER(CAST(mp.player_name AS TEXT)) || '%'
            WHERE mp.player_name IS NOT NULL
            GROUP BY mp.player_name, mp.frequent_club, mp.detected_category, mp.total_matches_played
        )
        SELECT
            player_name,
            frequent_club,
            total_matches_played,
            COALESCE(total_clubes_distintos, 1) AS total_clubes_distintos,
            CASE
                WHEN COALESCE(total_clubes_distintos, 1) = 1 THEN 'Fiel (Mono-club)'
                WHEN COALESCE(total_clubes_distintos, 1) >= 3 THEN 'Cazador de Precios / Multiclub'
                ELSE 'Ocasional / Híbrido'
            END AS perfil_comportamiento
        FROM player_market_stats
        WHERE (:detected_category IS NULL OR LOWER(CAST(detected_category AS TEXT)) = LOWER(CAST(:detected_category AS TEXT)))
        ORDER BY total_matches_played DESC, total_clubes_distintos DESC, player_name ASC
        LIMIT :limit
        """
    )

    res = await db.execute(
        query,
        {"detected_category": detected_category, "limit": limit},
    )
    rows = res.mappings().all()

    return [
        {
            "player_name": row["player_name"],
            "frequent_club": row["frequent_club"],
            "total_matches_played": int(row["total_matches_played"] or 0),
            "total_clubes_distintos": int(row["total_clubes_distintos"] or 0),
            "perfil_comportamiento": row["perfil_comportamiento"],
        }
        for row in rows
    ]


@router.get("/prospects")
async def get_market_prospects(
    category: Optional[str] = Query(None, description="Ejemplo: 3ra, 4ta, 5ta"),
    time_slot: Optional[str] = Query(None, description="Texto aproximado de la franja horaria"),
    limit: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """
    Consulta prospectos del CRM detectados en otros clubes para llenar huecos de reserva.
    """
    query = """
        SELECT 
            player_name, 
            frequent_club, 
            detected_category, 
            preferred_time_slot, 
            total_matches_played, 
            last_active_date
        FROM market_player_profiles
        WHERE 1=1
    """
    params = {"limit": limit}
    
    if category:
        query += " AND detected_category ILIKE :cat"
        params["cat"] = f"%{category}%"
        
    if time_slot:
        query += " AND preferred_time_slot ILIKE :slot"
        params["slot"] = f"%{time_slot}%"

    query += " ORDER BY total_matches_played DESC LIMIT :limit"

    res = await db.execute(text(query), params)
    rows = res.fetchall()

    return [
        {
            "player_name": r[0],
            "frequent_club": r[1],
            "category": r[2],
            "preferred_slot": r[3],
            "matches_played": r[4],
            "last_active": r[5]
        }
        for r in rows
    ]


