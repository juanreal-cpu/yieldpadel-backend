import csv
import os
from sqlalchemy import create_engine, text
from app.core.config import settings

# Conexión a Supabase
db_url = settings.DATABASE_URL.replace("+asyncpg", "")
engine = create_engine(db_url)

csv_file = "data/radar/processed/radar_master_consolidated.csv"
if not os.path.exists(csv_file):
    print(f"Error: no se encontró el archivo {csv_file}")
    exit(1)

with open(csv_file, mode="r", encoding="utf-8-sig") as f:
    records = list(csv.DictReader(f))

print(f"Leídos {len(records)} registros del CSV maestro.")

with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS competitor_market_slots (
            id SERIAL PRIMARY KEY,
            club_name VARCHAR(120),
            message_date VARCHAR(50),
            message_time VARCHAR(50),
            organizer VARCHAR(120),
            time_slot VARCHAR(100),
            category VARCHAR(50),
            court VARCHAR(50),
            match_type VARCHAR(50),
            price_per_player NUMERIC(10,2),
            spots_count INT,
            is_closed BOOLEAN,
            estimated_revenue NUMERIC(10,2),
            players TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_market_slots_dedup 
        ON competitor_market_slots (club_name, message_date, message_time, COALESCE(court, ''), COALESCE(time_slot, ''));
    """))

    insert_query = text("""
        INSERT INTO competitor_market_slots (
            club_name, message_date, message_time, organizer, time_slot, category, court,
            match_type, price_per_player, spots_count, is_closed, estimated_revenue, players
        ) VALUES (
            :club_name, :message_date, :message_time, :organizer, :time_slot, :category, :court,
            :match_type, :price_per_player, :spots_count, :is_closed, :estimated_revenue, :players
        )
        ON CONFLICT DO NOTHING;
    """)

    payload = []
    for r in records:
        payload.append({
            "club_name": r.get("club_name"),
            "message_date": r.get("message_date"),
            "message_time": r.get("message_time"),
            "organizer": r.get("organizer"),
            "time_slot": r.get("time_slot"),
            "category": r.get("category"),
            "court": r.get("court"),
            "match_type": r.get("match_type"),
            "price_per_player": float(r.get("price_per_player") or 0),
            "spots_count": int(float(r.get("spots_count") or 0)),
            "is_closed": str(r.get("is_closed")).lower() in ["true", "1", "t", "si"],
            "estimated_revenue": float(r.get("estimated_revenue") or 0),
            "players": r.get("players")
        })

    batch_size = 500
    for i in range(0, len(payload), batch_size):
        conn.execute(insert_query, payload[i:i + batch_size])
        print(f"Insertados {min(i + batch_size, len(payload))} / {len(payload)}...")

print("¡Registros de Radar sincronizados con éxito en Supabase!")