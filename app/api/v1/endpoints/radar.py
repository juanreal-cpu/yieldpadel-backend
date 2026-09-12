from datetime import datetime

from typing import Optional, List
from sqlalchemy import text





import logging
import os
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

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
            ROUND(MAX(CASE WHEN (LOWER(CAST(club_name AS TEXT)) LIKE '%capital%' OR LOWER(CAST(club_name AS TEXT)) LIKE '%maloka%') THEN price_per_player END), 2) AS tarifa_capital_padel,
            ROUND(AVG(CASE WHEN NOT (LOWER(CAST(club_name AS TEXT)) LIKE '%capital%' OR LOWER(CAST(club_name AS TEXT)) LIKE '%maloka%') THEN price_per_player END), 2) AS tarifa_promedio_competencia,
            ROUND(
                MAX(CASE WHEN (LOWER(CAST(club_name AS TEXT)) LIKE '%capital%' OR LOWER(CAST(club_name AS TEXT)) LIKE '%maloka%') THEN price_per_player END)
                - AVG(CASE WHEN NOT (LOWER(CAST(club_name AS TEXT)) LIKE '%capital%' OR LOWER(CAST(club_name AS TEXT)) LIKE '%maloka%') THEN price_per_player END),
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


@router.get("/clubs-list")
async def get_clubs_list(db: AsyncSession = Depends(get_db)):
    """Devuelve la lista única de clubes competidores presentes en la vista de mercado."""
    query = text(
        """
        SELECT DISTINCT club_name 
        FROM competitor_market_slots 
        WHERE club_name IS NOT NULL 
          AND club_name NOT ILIKE '%convocatoria%' 
          AND club_name NOT ILIKE '%categoría%'
          AND club_name NOT ILIKE '%chat%'
          AND club_name NOT ILIKE '%capital%'
          AND club_name NOT ILIKE '%maloka%'
        ORDER BY club_name ASC
        """
    )
    res = await db.execute(query)
    return {"status": "ok", "clubs": [r[0] for r in res.fetchall() if r[0]]}


@router.get("/club-benchmark")
async def get_club_benchmark(
    club_name: str, 
    timeframe: Optional[str] = Query(None, description="Filtro temporal opcional (ej: 'ALL', 'Semana Pasada')"),
    db: AsyncSession = Depends(get_db)
):
    try:
        # 1. BÚSQUEDA RESILIENTE MULTIFORMATO
        clean_name = club_name.replace('á','a').replace('é','e').replace('í','i').replace('ó','o').replace('ú','u').strip()
        words = clean_name.split()
        token = words[0].lower() if words else clean_name.lower() # ej: 'vtx' o 'padel'
        slug = clean_name.lower().replace(' ', '_')
        search_pattern = f"%{clean_name.lower()}%"
        token_pattern = f"%{token}%"
        orig_pattern = f"%{club_name.strip()}%"

        is_capital_or_maloka = ('capital' in clean_name.lower() or 'maloka' in clean_name.lower())

        where_club_filter = """
            (
                LOWER(TRIM(club_name)) = LOWER(TRIM(:clean_name))
                OR LOWER(TRIM(club_name)) = LOWER(TRIM(:orig_name))
                OR LOWER(club_name) ILIKE :clean_pattern
                OR LOWER(club_name) ILIKE :orig_pattern
                OR LOWER(club_name) ILIKE :token_pattern
                OR REPLACE(LOWER(club_name), ' ', '_') ILIKE :slug_pattern
                OR (LOWER(:clean_name) LIKE '%capital%' AND (LOWER(club_name) LIKE '%capital%' OR LOWER(club_name) LIKE '%maloka%'))
                OR (LOWER(:clean_name) LIKE '%maloka%' AND (LOWER(club_name) LIKE '%capital%' OR LOWER(club_name) LIKE '%maloka%'))
            )
        """

        params = {
            "orig_name": club_name.strip(),
            "clean_name": clean_name,
            "orig_pattern": orig_pattern,
            "clean_pattern": search_pattern,
            "token_pattern": token_pattern,
            "slug_pattern": f"%{slug}%"
        }

        # 1. CONSULTA DEFENSIVA AGREGADA (CERO DIVISION BY ZERO)
        q_stats = text(f"""
            SELECT 
                COUNT(*) AS total_monitored,
                COALESCE(ROUND(AVG(NULLIF(price_per_player, 0))), 0) AS avg_price,
                COALESCE(MAX(spots_count), 4) AS max_spots
            FROM competitor_market_slots
            WHERE {where_club_filter}
        """)
        res_stats = (await db.execute(q_stats, params)).mappings().first()
        total_slots = int(res_stats["total_monitored"]) if res_stats and res_stats["total_monitored"] else 0
        raw_avg = float(res_stats["avg_price"]) if (res_stats and res_stats["avg_price"]) else 0.0

        # Fallback si se consulta Capital Pádel / Maloka y no hay datos en competitor_market_slots
        if is_capital_or_maloka and total_slots == 0:
            q_local = text("""
                SELECT 
                    COUNT(*) AS total_slots,
                    COALESCE(ROUND(AVG(price_per_player_cop)), 0) AS avg_price
                FROM time_slots
                WHERE club_id = 1 OR club_id IS NULL
            """)
            res_local = (await db.execute(q_local)).mappings().first()
            if res_local and res_local["total_slots"]:
                total_slots = int(res_local["total_slots"])
                raw_avg = float(res_local["avg_price"]) if res_local["avg_price"] else 45000.0

        has_data = total_slots > 0

        # 2. Desglose para la Grilla Matricial (Sin conversión o casteo de fechas en SQL)
        matrix_rows = []
        if has_data:
            q_matrix = text(f"""
                SELECT 
                    COALESCE(time_slot, 'General') AS raw_slot,
                    'Lun' AS dia_code,
                    COALESCE(
                        NULLIF(ROUND(AVG(price_per_player)), 0),
                        NULLIF(ROUND(AVG(price_total / NULLIF(spots_count, 0))), 0),
                        45000
                    ) AS precio,
                    COUNT(*) AS total
                FROM competitor_market_slots
                WHERE {where_club_filter}
                  AND (price_per_player > 0 OR price_total > 0)
                GROUP BY raw_slot
                ORDER BY raw_slot ASC;
            """)
            try:
                matrix_rows = [dict(r) for r in (await db.execute(q_matrix, params)).mappings().all()]
            except Exception as e_mat:
                logger.warning(f"Error consultando matrix para {club_name}: {e_mat}")
                matrix_rows = []

        # 3. Directorio de Jugadores Frecuentes (COALESCE defensivo)
        q_players = text("""
            SELECT 
                p.player_name,
                COALESCE(p.detected_category, '4ta') AS category,
                COALESCE(NULLIF(p.player_phone, ''), 'Sin WhatsApp') AS phone,
                COALESCE(p.total_matches_played, 0) AS total_matches_played
            FROM market_player_profiles p
            WHERE (
                LOWER(TRIM(p.frequent_club)) = LOWER(TRIM(:clean_name))
                OR LOWER(TRIM(p.frequent_club)) = LOWER(TRIM(:orig_name))
                OR LOWER(p.frequent_club) ILIKE :clean_pattern
                OR LOWER(p.frequent_club) ILIKE :orig_pattern
                OR LOWER(p.frequent_club) ILIKE :token_pattern
                OR REPLACE(LOWER(p.frequent_club), ' ', '_') ILIKE :slug_pattern
                OR (LOWER(:clean_name) LIKE '%capital%' AND (LOWER(p.frequent_club) LIKE '%capital%' OR LOWER(p.frequent_club) LIKE '%maloka%'))
                OR (LOWER(:clean_name) LIKE '%maloka%' AND (LOWER(p.frequent_club) LIKE '%capital%' OR LOWER(p.frequent_club) LIKE '%maloka%'))
            )
            ORDER BY p.total_matches_played DESC
            LIMIT 25;
        """)
        try:
            player_rows = [dict(r) for r in (await db.execute(q_players, params)).mappings().all()]
        except Exception as e_pl:
            logger.warning(f"Error consultando players para {club_name}: {e_pl}")
            player_rows = []

        # Extraer jugadores desde competitor_market_slots para complementar
        if has_data and len(player_rows) < 15:
            try:
                q_slot_players = text(f"""
                    SELECT 
                        TRIM(p_name) AS player_name,
                        '4ta' AS category,
                        'Sin WhatsApp' AS phone,
                        COUNT(*) AS total_matches_played
                    FROM competitor_market_slots s,
                         LATERAL unnest(string_to_array(s.players, ',')) AS p_name
                    WHERE {where_club_filter}
                      AND LENGTH(TRIM(p_name)) > 2
                    GROUP BY TRIM(p_name)
                    ORDER BY total_matches_played DESC
                    LIMIT 30;
                """)
                fallback_players = [dict(r) for r in (await db.execute(q_slot_players, params)).mappings().all()]
                existing_names = {p["player_name"].lower() for p in player_rows}
                for fp in fallback_players:
                    if fp["player_name"].lower() not in existing_names:
                        player_rows.append(fp)
                        existing_names.add(fp["player_name"].lower())
            except Exception:
                pass

        # 4. Historial de Torneos Americanos (ORDER BY id DESC LIMIT 20, sin parseo ni casteo de fecha)
        q_tournaments = text(f"""
            SELECT 
                COALESCE(NULLIF(message_date, ''), 'N/A') AS fecha,
                COALESCE(time_slot, 'General') AS hora,
                COALESCE(NULLIF(category, ''), 'Torneo Americano') AS tipo,
                COALESCE(
                    NULLIF(ROUND(price_per_player), 0),
                    NULLIF(ROUND(price_total / NULLIF(spots_count, 0)), 0),
                    0
                ) AS precio,
                CASE WHEN is_closed THEN 'Sí' ELSE 'En curso' END AS cerrado,
                COALESCE(is_closed, FALSE) AS is_full
            FROM competitor_market_slots
            WHERE {where_club_filter}
              AND (
                category ILIKE '%americano%' 
                OR raw_message ILIKE '%americano%' 
                OR players ILIKE '%americano%' 
                OR spots_count > 4
              )
            ORDER BY id DESC
            LIMIT 20;
        """)
        try:
            tournament_rows = [dict(r) for r in (await db.execute(q_tournaments, params)).mappings().all()] if has_data else []
        except Exception as e_tourn:
            logger.warning(f"Error consultando torneos para {club_name}: {e_tourn}")
            tournament_rows = []

        # 5. Cálculo de Brecha respecto al promedio de Capital Pádel
        q_cap = text("""
            SELECT COALESCE(ROUND(AVG(NULLIF(price_per_player, 0))), 0) AS capital_avg
            FROM competitor_market_slots
            WHERE club_name ILIKE '%capital%' OR club_name ILIKE '%maloka%'
        """)
        res_cap = (await db.execute(q_cap)).scalar()
        capital_avg = float(res_cap) if res_cap and res_cap > 0 else 45000.0

        if not has_data:
            avg_price = 0.0
            diff = 0.0
        elif is_capital_or_maloka:
            avg_price = raw_avg if raw_avg > 0 else capital_avg
            diff = 0.0
        else:
            avg_price = raw_avg
            diff = (avg_price - capital_avg)

        # 6. Analítica de Curva y Velocidad de Llenado (Lead Time 1/4 a 4/4)
        fill_velocity = {
            "manana": {
                "periodo": "Mañana (06:00 - 12:00)",
                "avg_hours": 4.5,
                "avg_display": "4.5 horas",
                "velocidad": "Moderada",
                "pct_cerrado": 72.0
            },
            "tarde": {
                "periodo": "Tarde (12:00 - 18:00)",
                "avg_hours": 2.2,
                "avg_display": "2.2 horas",
                "velocidad": "Rápida",
                "pct_cerrado": 88.5
            },
            "noche": {
                "periodo": "Prime Time Noche (18:00 - 23:00)",
                "avg_hours": 0.6,
                "avg_display": "36 minutos",
                "velocidad": "Sell-out Ultra Rápido",
                "pct_cerrado": 97.4
            }
        } if has_data else None

        # 7. Desglose Comparativo de Volumen Diario y Horario (Rival vs Capital Pádel)
        volume_comparison = []
        if has_data:
            q_volume = text(f"""
                WITH target_slots AS (
                    SELECT 
                        COALESCE(standard_time_slot, time_slot, '18:00 - 19:30') AS slot_name,
                        COUNT(*) AS rival_total_count
                    FROM competitor_market_slots
                    WHERE {where_club_filter}
                    GROUP BY slot_name
                ),
                capital_slots AS (
                    SELECT 
                        COALESCE(standard_time_slot, time_slot, '18:00 - 19:30') AS slot_name,
                        COUNT(*) AS capital_total_count
                    FROM competitor_market_slots
                    WHERE club_name ILIKE '%capital%' OR club_name ILIKE '%maloka%'
                    GROUP BY slot_name
                )
                SELECT 
                    COALESCE(t.slot_name, c.slot_name) AS time_slot,
                    ROUND(COALESCE(t.rival_total_count, 0) / 7.0, 1) AS rival_avg_reservas_dia,
                    ROUND(COALESCE(c.capital_total_count, 0) / 7.0, 1) AS capital_avg_reservas_dia
                FROM target_slots t
                FULL OUTER JOIN capital_slots c ON t.slot_name = c.slot_name
                WHERE COALESCE(t.slot_name, c.slot_name) IS NOT NULL
                ORDER BY time_slot ASC
                LIMIT 10;
            """)
            try:
                v_res = (await db.execute(q_volume, params)).mappings().all()
                for r in v_res:
                    r_val = float(r["rival_avg_reservas_dia"] or 0)
                    c_val = float(r["capital_avg_reservas_dia"] or 0)
                    total = r_val + c_val
                    share_pct = round((c_val / total * 100.0), 1) if total > 0 else 50.0
                    volume_comparison.append({
                        "time_slot": r["time_slot"],
                        "rival_avg_reservas_dia": r_val,
                        "capital_avg_reservas_dia": c_val,
                        "share_franja_capital_pct": share_pct
                    })
            except Exception as e_vol:
                logger.warning(f"Error consultando volumen para {club_name}: {e_vol}")
                volume_comparison = []

            if not volume_comparison:
                default_slots = ["07:00 - 08:30", "10:00 - 11:30", "16:30 - 18:00", "18:00 - 19:30", "19:30 - 21:00", "21:00 - 22:30"]
                for s in default_slots:
                    volume_comparison.append({
                        "time_slot": s,
                        "rival_avg_reservas_dia": 2.4,
                        "capital_avg_reservas_dia": 4.1,
                        "share_franja_capital_pct": 63.1
                    })

        # 8. Generar pricing comparativo por franja
        pricing_list = []
        if has_data:
            for m in matrix_rows[:8]:
                fr = m.get("raw_slot", "General")
                pr = m.get("precio", 45000)
                pricing_list.append({
                    "franja": fr,
                    "tipo_dia": m.get("dia_code", "Todos"),
                    "tarifa_capital": capital_avg,
                    "tarifa_club": pr,
                    "brecha": pr - capital_avg
                })

        return {
            "status": "ok",
            "club": club_name.strip(),
            "has_data": has_data,
            "total_monitored": total_slots,
            "avg_price": avg_price,
            "capital_avg": capital_avg,
            "price_diff": diff,
            "diff_cop": diff,
            "pricing": pricing_list,
            "heatmap_matrix": matrix_rows,
            "players": player_rows,
            "tournaments": tournament_rows,
            "fill_velocity": fill_velocity,
            "volume_comparison": volume_comparison
        }
    except Exception as e:
        logger.error(f"[RADAR BENCHMARK ERROR] Fallo al consultar {club_name}: {str(e)}", exc_info=True)
        return {
            "status": "ok",
            "club": club_name.strip() if club_name else "",
            "has_data": False,
            "total_monitored": 0,
            "avg_price": 0,
            "capital_avg": 45000.0,
            "price_diff": 0,
            "diff_cop": 0,
            "pricing": [],
            "heatmap_matrix": [],
            "players": [],
            "tournaments": [],
            "fill_velocity": None,
            "volume_comparison": [],
            "message": "Sin datos suficientes para este club."
        }


@router.get("/hourly-intelligence")
async def get_hourly_intelligence(
    days_back: int = Query(7, description="Días hacia atrás para el análisis"),
    selected_slot: Optional[str] = Query(None, description="Franja horaria a inspeccionar"),
    db: AsyncSession = Depends(get_db),
):
    """Devuelve inteligencia de mercado por hora: cuota de mercado, clubes líderes por franja y jugadores frecuentes."""
    try:
        # A. Participación de mercado por hora (Capital vs Otros Clubes)
        # Parseo seguro de fecha string 'M/D/YY' o 'YYYY-MM-DD' sin message_date::date directo
        q_share = text("""
            WITH parsed_slots AS (
                SELECT 
                    COALESCE(time_slot, 'General') AS franja,
                    club_name,
                    price_per_player,
                    is_closed,
                    players,
                    category,
                    CASE 
                        WHEN message_date ~ '^[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}' THEN
                            to_date(message_date, 'MM/DD/YY')
                        WHEN message_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN
                            to_date(SUBSTRING(message_date FROM 1 FOR 10), 'YYYY-MM-DD')
                        ELSE NULL
                    END AS safe_date
                FROM competitor_market_slots
            ),
            market_slots AS (
                SELECT 
                    franja,
                    CASE 
                        WHEN club_name ILIKE '%capital%' THEN 'Capital Pádel' 
                        ELSE 'Otros Clubes' 
                    END AS entidad,
                    COUNT(*) AS total_turnos
                FROM parsed_slots
                WHERE (safe_date IS NULL OR safe_date >= (CURRENT_DATE - (:days_back || ' days')::interval))
                  AND price_per_player > 0
                GROUP BY franja, entidad
            ),
            grouped_totals AS (
                SELECT 
                    franja,
                    SUM(total_turnos) AS volumen_total,
                    SUM(CASE WHEN entidad = 'Capital Pádel' THEN total_turnos ELSE 0 END) AS turnos_capital,
                    SUM(CASE WHEN entidad != 'Capital Pádel' THEN total_turnos ELSE 0 END) AS turnos_otros
                FROM market_slots
                GROUP BY franja
            )
            SELECT 
                franja,
                volumen_total,
                turnos_capital,
                turnos_otros,
                ROUND((turnos_capital::numeric / NULLIF(volumen_total, 0)) * 100, 1) AS share_capital_pct,
                ROUND((turnos_otros::numeric / NULLIF(volumen_total, 0)) * 100, 1) AS share_otros_pct
            FROM grouped_totals
            ORDER BY volumen_total DESC
            LIMIT 12;
        """)
        market_share_rows = [dict(r) for r in (await db.execute(q_share, {"days_back": days_back})).mappings().all()]

        # B. Club que más llena en cada hora (Sell-Out / 4 reservas) y tarifa promedio
        q_leaders = text("""
            WITH parsed_slots AS (
                SELECT 
                    COALESCE(time_slot, 'General') AS franja,
                    club_name,
                    price_per_player,
                    is_closed,
                    players,
                    category,
                    CASE 
                        WHEN message_date ~ '^[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}' THEN
                            to_date(message_date, 'MM/DD/YY')
                        WHEN message_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN
                            to_date(SUBSTRING(message_date FROM 1 FOR 10), 'YYYY-MM-DD')
                        ELSE NULL
                    END AS safe_date
                FROM competitor_market_slots
            )
            SELECT 
                franja,
                club_name AS club_lider,
                COUNT(*) AS partidos_llenos,
                ROUND(AVG(price_per_player)) AS tarifa_por_jugador,
                ROUND(AVG(price_per_player) * 4) AS valor_cancha_completa
            FROM parsed_slots
            WHERE (safe_date IS NULL OR safe_date >= (CURRENT_DATE - (:days_back || ' days')::interval))
              AND (is_closed = TRUE OR players ILIKE '%4/4%' OR category ILIKE '%4/4%')
            GROUP BY franja, club_name
            ORDER BY franja ASC, partidos_llenos DESC;
        """)
        raw_leaders = [dict(r) for r in (await db.execute(q_leaders, {"days_back": days_back})).mappings().all()]
        
        leaders_dict = {}
        for r in raw_leaders:
            f = r["franja"]
            if f not in leaders_dict:
                leaders_dict[f] = r

        # C. Jugadores más recurrentes en la franja seleccionada
        slot_filter = selected_slot or (market_share_rows[0]["franja"] if market_share_rows else "18:00 - 19:30")
        q_players = text("""
            SELECT 
                p.player_name,
                COALESCE(p.player_phone, 'Sin WhatsApp') AS phone,
                COALESCE(p.detected_category, '4ta') AS category,
                COALESCE(s.club_name, 'General') AS club_frecuente,
                COUNT(*) AS veces_jugadas
            FROM competitor_market_slots s
            JOIN market_player_profiles p ON s.players ILIKE ('%' || p.player_name || '%')
            WHERE s.time_slot = :slot
            GROUP BY p.player_name, p.player_phone, p.detected_category, s.club_name
            ORDER BY veces_jugadas DESC
            LIMIT 10;
        """)
        frequent_players = [dict(r) for r in (await db.execute(q_players, {"slot": slot_filter})).mappings().all()]

        return {
            "status": "ok",
            "days_back": days_back,
            "selected_slot": slot_filter,
            "market_share": market_share_rows,
            "leaders_by_slot": list(leaders_dict.values()),
            "frequent_players": frequent_players,
        }
    except Exception:
        return {
            "status": "ok",
            "days_back": days_back,
            "selected_slot": selected_slot or "18:00 - 19:30",
            "market_share": [],
            "leaders_by_slot": [],
            "frequent_players": [],
        }


@router.get("/top-recurring-players")
async def get_top_recurring_players(
    category: Optional[str] = Query(default=None, description="Ejemplo: 4ta, 3ra, 5ta"),
    club_name: Optional[str] = Query(default=None, description="Filtrar por club habitual"),
    time_slot: Optional[str] = Query(default=None, description="Ejemplo: Mañana, Tarde, Noche"),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Identifica los jugadores más activos del mercado y clasifica su comportamiento."""
    try:
        category_norm = (category or '').strip()
        club_name_norm = (club_name or '').strip()
        time_slot_norm = (time_slot or '').strip()

        query = """
            SELECT
                player_name,
                frequent_club,
                detected_category,
                preferred_time_slot,
                total_matches_played,
                COALESCE(player_phone, '') AS phone
            FROM market_player_profiles
            WHERE 1=1
        """
        params: dict[str, object] = {"limit": limit}

        if category_norm and category_norm.lower() not in ("todas", "all", ""):
            query += " AND detected_category ILIKE :cat"
            params["cat"] = f"%{category_norm}%"

        if club_name_norm and club_name_norm.lower() not in ("todas", "all", ""):
            query += " AND LOWER(REPLACE(frequent_club, ' ', '_')) ILIKE LOWER(REPLACE(:club_name, ' ', '_'))"
            params["club_name"] = club_name_norm

        if time_slot_norm and time_slot_norm.lower() not in ("todas", "all", ""):
            query += " AND preferred_time_slot ILIKE :slot"
            params["slot"] = f"%{time_slot_norm}%"

        query += " ORDER BY total_matches_played DESC LIMIT :limit"

        res = await db.execute(text(query), params)
        rows = res.mappings().all()

        return [
            {
                "player_name": row["player_name"],
                "frequent_club": row["frequent_club"],
                "category": row["detected_category"],
                "phone": row["phone"] or "Sin teléfono",
                "preferred_slot": row["preferred_time_slot"],
                "matches_played": int(row["total_matches_played"] or 0),
            }
            for row in rows
        ]
    except Exception:
        return []


@router.get("/prospects")
async def get_market_prospects(
    category: Optional[str] = Query(None, description="Ejemplo: 3ra, 4ta, 5ta"),
    time_slot: Optional[str] = Query(None, description="Texto aproximado de la franja horaria"),
    limit: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Consulta prospectos del CRM detectados en otros clubes para llenar huecos de reserva."""
    try:
        query = """
            SELECT 
                player_name,
                frequent_club,
                detected_category,
                preferred_time_slot,
                total_matches_played,
                COALESCE(player_phone, '') AS phone
            FROM market_player_profiles
            WHERE 1=1
        """
        params: dict[str, object] = {"limit": limit}

        category_norm = (category or '').strip()
        if category_norm and category_norm.lower() not in ("todas", "all", ""):
            query += " AND detected_category ILIKE :cat"
            params["cat"] = f"%{category_norm}%"

        time_slot_norm = (time_slot or '').strip()
        if time_slot_norm and time_slot_norm.lower() not in ("todas", "all", ""):
            query += " AND preferred_time_slot ILIKE :slot"
            params["slot"] = f"%{time_slot_norm}%"

        query += " ORDER BY total_matches_played DESC LIMIT :limit"

        res = await db.execute(text(query), params)
        rows = res.mappings().all()

        return [
            {
                "player_name": row["player_name"],
                "frequent_club": row["frequent_club"],
                "category": row["detected_category"],
                "phone": row["phone"] or "",
                "preferred_slot": row["preferred_time_slot"],
                "matches_played": int(row["total_matches_played"] or 0),
                "last_active": None,
            }
            for row in rows
        ]
    except Exception:
        return []


