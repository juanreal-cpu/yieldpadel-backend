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
# 1. iOS: [DD/MM/YYYY, HH:MM:SS AM/PM] Sender: Message
HEADER_REGEX_IOS = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?\s*[APMapm]*)\]\s+([^:]+):\s*(.*)$"
)
# 2. Android: DD/MM/YYYY, HH:MM - Sender: Message
HEADER_REGEX_ANDROID = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?\s*[APMapm]*)\s*-\s+([^:]+):\s*(.*)$"
)


def clean_text_line(line: str) -> str:
    """Removes invisible Unicode marks commonly found in WhatsApp exports (LTR/RTL marks, narrow spaces)."""
    return line.replace("\u200e", "").replace("\u200f", "").replace("\u202f", " ").replace("\ufeff", "")


def parse_price(text: str) -> float:
    """Extracts numeric price value from text with 💰 or general currency format."""
    price_match = re.search(r"💰\s*\$?\s*([0-9\.\,]+)", text)
    if not price_match:
        price_match = re.search(r"\$\s*([0-9\.\,]+)", text)

    if price_match:
        raw_val = price_match.group(1).replace(".", "").replace(",", "")
        try:
            return float(raw_val)
        except ValueError:
            return 0.0
    return 0.0


def parse_time_slot(text: str) -> Optional[str]:
    """Extracts match time range from text (e.g. 6:00pm - 7:30pm)."""
    # Prefer line starting with ⌚
    watch_match = re.search(r"⌚\s*([^\n\r]+)", text)
    if watch_match:
        slot_candidate = watch_match.group(1).strip()
        # Clean up any trailing text
        slot_candidate = re.split(r"[📍💰🎾\n\r]", slot_candidate)[0].strip()
        if slot_candidate:
            return slot_candidate

    # Fallback to standard time range regex
    range_match = re.search(
        r"((?:1[0-2]|[1-9])(?::[0-5][0-9])?\s*(?:am|pm)?\s*-\s*(?:1[0-2]|[1-9])(?::[0-5][0-9])?\s*(?:am|pm))",
        text,
        re.IGNORECASE,
    )
    if range_match:
        return range_match.group(1).strip()

    return None


def parse_whatsapp_export(
    file_content: str,
    filename: str,
    raw_saved_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parses a raw WhatsApp chat export .txt content to extract paddle open match announcements (🎾),
    computes batch KPIs, and saves a processed CSV in data/radar/processed/.
    """
    lines = file_content.splitlines()
    raw_messages: List[Dict[str, str]] = []
    current_msg: Optional[Dict[str, str]] = None

    for raw_line in lines:
        line = clean_text_line(raw_line)

        # Check for message headers
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
                # Handle leading preamble before first header if it contains convocatoria
                if "🎾" in line:
                    current_msg = {
                        "date": "",
                        "time": "",
                        "sender": "Organizador",
                        "body": line,
                    }

    if current_msg:
        raw_messages.append(current_msg)

    # Filter messages containing racket emoji 🎾
    matches: List[Dict[str, Any]] = []
    unique_players_set = set()
    time_slots_counter: Counter = Counter()

    for msg in raw_messages:
        body = msg["body"]
        if "🎾" not in body:
            continue

        organizer = msg["sender"]
        message_date = msg["date"]
        message_time = msg["time"]

        time_slot = parse_time_slot(body)
        if time_slot:
            time_slots_counter[time_slot] += 1

        price_per_player = parse_price(body)

        # Court detection
        court_match = re.search(
            r"\b(CANCHA\s*#?\s*\d+|Cancha\s*#?\s*\d+|Cancha\s+Central(?:\s+\d+)?)\b",
            body,
            re.IGNORECASE,
        )
        court = court_match.group(1).strip().upper() if court_match else None

        # Category detection
        cat_match = re.search(r"Categor[íi]a:\s*([A-Za-z0-9_\-]+)", body, re.IGNORECASE)
        category = cat_match.group(1).strip() if cat_match else "4ta"

        # Players extraction
        players: List[str] = []
        for bline in body.splitlines():
            if "🎾" in bline:
                p_part = bline.split("🎾", 1)[1].strip()
                clean_player = re.sub(r"^[\d\.\-\)\s]+", "", p_part).strip()
                # Exclude header/status strings mistakenly placed after 🎾
                if (
                    clean_player
                    and not clean_player.upper().startswith("PARTIDO")
                    and clean_player.upper() not in ["CERRADO", "ABIERTO", "COMPLETO", "CONFIRMADO"]
                ):
                    players.append(clean_player)
                    if len(clean_player) > 1:
                        unique_players_set.add(clean_player.strip().title())

        spots_count = len(players)
        is_closed = ("PARTIDO CERRADO" in body.upper()) or (spots_count >= 4)
        estimated_revenue = price_per_player * 4.0 if is_closed else (price_per_player * spots_count)

        matches.append({
            "message_date": message_date or None,
            "message_time": message_time or None,
            "organizer": organizer,
            "time_slot": time_slot,
            "category": category,
            "court": court,
            "price_per_player": price_per_player,
            "spots_count": spots_count,
            "players": players,
            "is_closed": is_closed,
            "estimated_revenue": estimated_revenue,
            "raw_snippet": body[:200] + ("..." if len(body) > 200 else ""),
        })

    # Consolidated KPIs
    total_matches = len(matches)
    closed_matches = sum(1 for m in matches if m["is_closed"])
    open_matches = total_matches - closed_matches
    closure_rate = round((closed_matches / total_matches * 100.0), 2) if total_matches > 0 else 0.0
    estimated_total_revenue = sum(m["price_per_player"] * 4.0 for m in matches if m["is_closed"])
    unique_players_count = len(unique_players_set)
    top_time_slots = dict(time_slots_counter.most_common(10))

    kpis = {
        "total_matches_detected": total_matches,
        "closed_matches": closed_matches,
        "open_matches": open_matches,
        "closure_rate_percent": closure_rate,
        "estimated_total_revenue": estimated_total_revenue,
        "unique_players_count": unique_players_count,
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