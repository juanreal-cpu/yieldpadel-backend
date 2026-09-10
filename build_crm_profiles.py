import os
import re
from collections import defaultdict
from sqlalchemy import create_engine, text
from app.core.config import settings

db_url = settings.DATABASE_URL.replace("+asyncpg", "")
engine = create_engine(db_url)

with engine.begin() as conn:
    # 1. Crear tabla asegurando TEXT para nombres sin truncamiento
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS market_player_profiles (
            id SERIAL PRIMARY KEY,
            player_name TEXT NOT NULL UNIQUE,
            frequent_club VARCHAR(120),
            detected_category VARCHAR(50) DEFAULT '4ta',
            preferred_time_slot VARCHAR(100),
            total_matches_played INT DEFAULT 1,
            last_active_date VARCHAR(50),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """))

    # Ajustar por si ya se había creado como varchar(120)
    conn.execute(text("ALTER TABLE market_player_profiles ALTER COLUMN player_name TYPE TEXT;"))

    # 2. Consultar convocatorias
    rows = conn.execute(text("""
        SELECT club_name, message_date, time_slot, category, players 
        FROM competitor_market_slots 
        WHERE players IS NOT NULL AND players != ''
    """)).fetchall()

    print(f"Analizando convocatorias con jugadores: {len(rows)}...")

    player_data = defaultdict(lambda: {
        "clubs": defaultdict(int),
        "categories": defaultdict(int),
        "slots": defaultdict(int),
        "last_date": "",
        "matches_count": 0
    })

    for r in rows:
        raw_players = str(r[4])
        # Separar por coma, punto y coma, slash o salto de línea
        names = re.split(r'[,;\n/]+', raw_players)
        for name in names:
            name = name.strip()
            # Limpieza básica de filtros y palabras no deseadas
            if len(name) < 3 or len(name) > 80:
                continue
            if any(w in name.lower() for w in ['abierto', 'cancelado', 'cupo', 'pareja', 'disponible', 'cancha']):
                continue
            
            p_entry = player_data[name]
            p_entry["matches_count"] += 1
            if r[0]: p_entry["clubs"][r[0]] += 1
            if r[3]: p_entry["categories"][r[3]] += 1
            if r[2]: p_entry["slots"][r[2]] += 1
            if r[1]: p_entry["last_date"] = r[1]

    payload = []
    for name, stats in player_data.items():
        top_club = max(stats["clubs"], key=stats["clubs"].get) if stats["clubs"] else "Desconocido"
        top_cat = max(stats["categories"], key=stats["categories"].get) if stats["categories"] else "4ta"
        top_slot = max(stats["slots"], key=stats["slots"].get) if stats["slots"] else "Noche"
        
        payload.append({
            "player_name": name,
            "frequent_club": top_club,
            "detected_category": top_cat,
            "preferred_time_slot": top_slot,
            "total_matches_played": stats["matches_count"],
            "last_active_date": stats["last_date"]
        })

    print(f"Total de jugadores individuales limpios: {len(payload)}")

    upsert_q = text("""
        INSERT INTO market_player_profiles (
            player_name, frequent_club, detected_category, preferred_time_slot, total_matches_played, last_active_date
        ) VALUES (
            :player_name, :frequent_club, :detected_category, :preferred_time_slot, :total_matches_played, :last_active_date
        )
        ON CONFLICT (player_name) DO UPDATE SET
            total_matches_played = EXCLUDED.total_matches_played,
            frequent_club = EXCLUDED.frequent_club,
            detected_category = EXCLUDED.detected_category,
            preferred_time_slot = EXCLUDED.preferred_time_slot,
            last_active_date = EXCLUDED.last_active_date;
    """)

    batch_size = 500
    for i in range(0, len(payload), batch_size):
        conn.execute(upsert_q, payload[i:i+batch_size])
        print(f"Insertados perfiles {min(i+batch_size, len(payload))} / {len(payload)}...")

print("CRM de Jugadores consolidado en Supabase con exito.")