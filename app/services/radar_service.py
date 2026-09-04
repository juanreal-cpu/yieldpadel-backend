import csv
from collections import Counter
from datetime import datetime
import os
import re
from typing import Any, Dict, List, Optional

RAW_DIR = os.path.join("data", "radar", "raw")
PROCESSED_DIR = os.path.join("data", "radar", "processed")

# Ensure base directories exist
os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

# Regex patterns for WhatsApp message headers
HEADER_REGEX_IOS = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?\s*[APMapm]*)\]\s+([^:]+):\s*(.*)$"
)
HEADER_REGEX_ANDROID = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?\s*[APMapm]*)\s*-\s+([^:]+):\s*(.*)$"
)

# Text and call-to-action blacklist for player name cleaning
DISCARD_PATTERNS = [
    "CUPOS LIMITADOS",
    "INSCRÍBETE YA",
    "INSCRIBETE YA",
    "INSCRÍBETE",
    "INSCRIBETE",
    "LIBRE",
    "DISPONIBLE",
    "CUPO LIBRE",
    "POR CONFIRMAR",
    "CONFIRMADO",
    "PARTIDO CERRADO",
    "PARTIDO ABIERTO",
    "ABIERTO",
    "CERRADO",
    "COMPLETO",
    "ESPERA",
    "LISTA DE ESPERA",
    "CANCELADO",
    "REGLAS",
    "PAGO",
    "TRANSFERENCIA",
]


def clean_text_line(line: str) -> str:
    """Removes invisible Unicode marks commonly found in WhatsApp exports."""
    return line.replace("\u200e", "").replace("\u200f", "").replace("\u202f", " ").replace("\ufeff", "")


def parse_price(text: str) -> int:
    """
    Extracts and normalizes currency value in Colombian Pesos (COP).
    Handles:
      - '22.5 k', '22.5k', '60k', '60 k' -> 22500, 60000
      - '35.000', '35000', '$35.000' -> 35000
      - Any value < 1000 (e.g. 22.5, 60, 35) is automatically multiplied by 1000.
    """
    has_k = False
    num_str = ""

    # 1. Search for price after 💰 or $ with optional 'k' / 'mil'
    m = re.search(
        r"(?:💰|\$)\s*([0-9]+(?:[\.\,][0-9]+)?)\s*(k|mil)?",
        text,
        re.IGNORECASE,
    )
    if m:
        num_str = m.group(1).strip()
        if m.group(2):
            has_k = True
    else:
        # 2. Search for explicit 'XX k' or 'XX.X k' or 'XX mil' anywhere in text
        m2 = re.search(r"\b([0-9]+(?:[\.\,][0-9]+)?)\s*(k|mil)\b", text, re.IGNORECASE)
        if m2:
            num_str = m2.group(1).strip()
            has_k = True
        else:
            # 3. Search for 💰 followed by raw digits/dots
            m3 = re.search(r"💰\s*([0-9\.\,]+)", text)
            if m3:
                num_str = m3.group(1).strip()

    if not num_str:
        return 0

    # Colombian thousand separator format: 35.000 or 120.000 (3 digits after dot, no 'k')
    clean_str = num_str.replace(",", ".")
    parts = clean_str.split(".")
    if len(parts) == 2 and len(parts[1]) == 3 and not has_k:
        try:
            val = float(parts[0] + parts[1])
        except ValueError:
            val = 0.0
    else:
        try:
            val = float(clean_str)
        except ValueError:
            val = 0.0

    if has_k:
        val *= 1000.0

    # Rule: If detected value is < 1000 (e.g. 22.5, 60, 35), multiply by 1000
    if 0 < val < 1000.0:
        val *= 1000.0

    return int(round(val))


def parse_time_slot(text: str) -> Optional[str]:
    """Extracts match time range from text (e.g. 6:00pm - 7:30pm)."""
    watch_match = re.search(r"⌚\s*([^\n\r]+)", text)
    if watch_match:
        slot_candidate = watch_match.group(1).strip()
        slot_candidate = re.split(r"[📍💰🎾\n\r]", slot_candidate)[0].strip()
        if slot_candidate:
            return slot_candidate

    range_match = re.search(
        r"((?:1[0-2]|[1-9])(?::[0-5][0-9])?\s*(?:am|pm)?\s*-\s*(?:1[0-2]|[1-9])(?::[0-5][0-9])?\s*(?:am|pm))",
        text,
        re.IGNORECASE,
    )
    if range_match:
        return range_match.group(1).strip()

    return None


def is_valid_player_name(name: str) -> bool:
    """Verifies that a player name does not contain CTAs or system text."""
    if not name or len(name) < 2:
        return False
    upper = name.upper()
    for pattern in DISCARD_PATTERNS:
        if pattern in upper:
            return False
    # Must contain at least one letter
    if not re.search(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]", name):
        return False
    return True


def split_player_pair(raw_name: str) -> List[str]:
    """
    If a player string indicates a pair (e.g. 'Sebas - Partner' or 'Diego C - Tapia' or 'Juan / David'),
    splits into individual player names so each accounts for 1 spot.
    """
    # Split on separators: ' - ', ' / ', ' & ', ' + ', or ' y ' / ' Y ' surrounded by spaces
    parts = re.split(r"\s+(?:[-/&+]|[yY])\s+", raw_name)
    cleaned_players = []
    for part in parts:
        clean = re.sub(r"^[\d\.\-\)\s]+", "", part).strip()
        clean = re.sub(r"[\.\-\)\s]+$", "", clean).strip()
        if is_valid_player_name(clean):
            cleaned_players.append(clean)
    return cleaned_players


def extract_match_date(body: str, message_date: Optional[str]) -> str:
    """Extracts match date mentioned in body or falls back to message header date."""
    m_body = re.search(
        r"(?:HOY|MAÑANA|FECHA)?\s*(\d{1,2}(?:/\d{1,2}(?:/\d{2,4})?|\s+de\s+[A-Za-z]+|\s+[A-Za-z]+))",
        body,
        re.IGNORECASE,
    )
    if m_body:
        cand = m_body.group(1).strip().upper()
        # Avoid times like 6:00
        if not re.match(r"^\d{1,2}:\d{2}", cand):
            return f"{message_date or ''}_{cand}"
    return message_date or "fecha_desconocida"


def parse_whatsapp_export(
    file_content: str,
    filename: str,
    raw_saved_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parses a raw WhatsApp chat export .txt content with advanced COP price normalization,
    player name filtering, pair splitting, match type classification (AMERICANO vs ESTANDAR_4),
    and intelligent deduplication per match slot.
    """
    lines = file_content.splitlines()
    raw_messages: List[Dict[str, str]] = []
    current_msg: Optional[Dict[str, str]] = None

    for raw_line in lines:
        line = clean_text_line(raw_line)

        m_ios = HEADER_REGEX_IOS.match(line)
        m_android = HEADER_REGEX_ANDROID.match(line) if not m_ios else None
        match = m_ios or m_android

        if match:
            if current_msg:
                raw_messages.append(current_msg)
            current_msg = {
                "date": match.group(1).strip(),
                "time": match.group(2).strip(),
                "sender": match.group(3).strip(),
                "body": match.group(4).strip(),
            }
        else:
            if current_msg is not None:
                current_msg["body"] += "\n" + line
            else:
                if "🎾" in line:
                    current_msg = {
                        "date": "",
                        "time": "",
                        "sender": "Organizador",
                        "body": line,
                    }

    if current_msg:
        raw_messages.append(current_msg)

    # Dictionary for slot deduplication: (target_date, time_slot, court_or_category) -> match_dict
    deduped_matches: Dict[tuple, Dict[str, Any]] = {}

    for msg in raw_messages:
        body = msg["body"]
        if "🎾" not in body:
            continue

        organizer = msg["sender"]
        message_date = msg["date"]
        message_time = msg["time"]

        time_slot = parse_time_slot(body)
        price_per_player = parse_price(body)

        court_match = re.search(
            r"\b(CANCHA\s*#?\s*\d+|Cancha\s*#?\s*\d+|Cancha\s+Central(?:\s+\d+)?)\b",
            body,
            re.IGNORECASE,
        )
        court = court_match.group(1).strip().upper() if court_match else None

        cat_match = re.search(r"Categor[íi]a:\s*([A-Za-z0-9_\-]+)", body, re.IGNORECASE)
        category = cat_match.group(1).strip() if cat_match else "4ta"

        # Extract and clean players, with pair splitting
        players: List[str] = []
        for bline in body.splitlines():
            if "🎾" in bline:
                p_part = bline.split("🎾", 1)[1].strip()
                p_part_clean = re.sub(r"^[\d\.\-\)\s]+", "", p_part).strip()

                if p_part_clean:
                    extracted_names = split_player_pair(p_part_clean)
                    players.extend(extracted_names)

        spots_count = len(players)

        # Distinguish match type
        is_americano = (
            ("AMERICANO" in body.upper())
            or ("REY DE PISTA" in body.upper())
            or (spots_count > 4)
        )
        match_type = "AMERICANO" if is_americano else "ESTANDAR_4"

        # Determine closure status
        if match_type == "AMERICANO":
            is_closed = ("PARTIDO CERRADO" in body.upper()) or (spots_count >= 8)
            estimated_revenue = price_per_player * spots_count
        else:
            is_closed = ("PARTIDO CERRADO" in body.upper()) or (spots_count >= 4)
            # Revenue rule: price_per_player * spots_count (or multiplied by 4 if closed)
            estimated_revenue = (price_per_player * 4) if is_closed else (price_per_player * spots_count)

        match_data = {
            "message_date": message_date or None,
            "message_time": message_time or None,
            "organizer": organizer,
            "time_slot": time_slot,
            "category": category,
            "court": court,
            "match_type": match_type,
            "price_per_player": price_per_player,
            "spots_count": spots_count,
            "players": players,
            "is_closed": is_closed,
            "estimated_revenue": int(round(estimated_revenue)),
            "raw_snippet": body[:200] + ("..." if len(body) > 200 else ""),
        }

        # Deduplication key: (target_date, normalized_time_slot, court_or_category)
        target_date = extract_match_date(body, message_date)
        norm_slot = re.sub(r"\s+", "", (time_slot or "sin_horario").lower())
        norm_resource = (court or category or "general").strip().upper()
        dedup_key = (target_date, norm_slot, norm_resource)

        # Chronological overwrite preserves the latest state of that slot announcement
        deduped_matches[dedup_key] = match_data

    # Final list of deduplicated matches
    matches = list(deduped_matches.values())

    # Calculate KPIs over deduplicated data
    unique_players_set = set()
    time_slots_counter: Counter = Counter()

    for m in matches:
        if m["time_slot"]:
            time_slots_counter[m["time_slot"]] += 1
        for p in m["players"]:
            if len(p) > 1:
                unique_players_set.add(p.strip().title())

    total_matches = len(matches)
    closed_matches = sum(1 for m in matches if m["is_closed"])
    open_matches = total_matches - closed_matches
    closure_rate = round((closed_matches / total_matches * 100.0), 2) if total_matches > 0 else 0.0
    estimated_total_revenue = sum(m["estimated_revenue"] for m in matches if m["is_closed"])
    standard_matches = sum(1 for m in matches if m["match_type"] == "ESTANDAR_4")
    americano_matches = sum(1 for m in matches if m["match_type"] == "AMERICANO")
    unique_players_count = len(unique_players_set)
    top_time_slots = dict(time_slots_counter.most_common(10))

    kpis = {
        "total_matches_detected": total_matches,
        "closed_matches": closed_matches,
        "open_matches": open_matches,
        "closure_rate_percent": closure_rate,
        "estimated_total_revenue": estimated_total_revenue,
        "unique_players_count": unique_players_count,
        "standard_matches": standard_matches,
        "americano_matches": americano_matches,
        "top_time_slots": top_time_slots,
    }

    # Export to processed CSV
    timestamp_prefix = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_clean = re.sub(r"[^\w\.\-]", "_", filename)
    if base_clean.lower().endswith(".txt"):
        base_clean = base_clean[:-4]

    csv_filename = f"{timestamp_prefix}_{base_clean}.csv"
    processed_csv_path = os.path.join(PROCESSED_DIR, csv_filename)

    csv_fieldnames = [
        "message_date",
        "message_time",
        "organizer",
        "time_slot",
        "category",
        "court",
        "match_type",
        "price_per_player",
        "spots_count",
        "is_closed",
        "estimated_revenue",
        "players",
    ]

    with open(processed_csv_path, mode="w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=csv_fieldnames)
        writer.writeheader()
        for m in matches:
            row = {
                "message_date": m["message_date"] or "",
                "message_time": m["message_time"] or "",
                "organizer": m["organizer"],
                "time_slot": m["time_slot"] or "",
                "category": m["category"] or "",
                "court": m["court"] or "",
                "match_type": m["match_type"],
                "price_per_player": m["price_per_player"],
                "spots_count": m["spots_count"],
                "is_closed": "SI" if m["is_closed"] else "NO",
                "estimated_revenue": m["estimated_revenue"],
                "players": "; ".join(m["players"]),
            }
            writer.writerow(row)

    return {
        "status": "success",
        "filename": filename,
        "raw_file_path": raw_saved_path or "",
        "processed_csv_path": processed_csv_path,
        "kpis": kpis,
        "matches": matches,
    }
