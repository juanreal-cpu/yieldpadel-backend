import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import csv
from fastapi.testclient import TestClient
from app.main import app

chat_sample = """[01/09/2026, 08:30:15 AM] Juan: Hola a todos, ¿quién juega hoy?
[01/09/2026, 09:00:22 AM] Carlos P: HOY 01 SEPTIEMBRE
Categoría: 4ta
⌚6:00pm - 7:30pm
📍Capital Pádel Club
CANCHA 2
💰30.000

🎾Carlos P
🎾Mateo R
🎾Daniel F
🎾

PARTIDO ABIERTO
[01/09/2026, 10:12:00 AM] Pedro: Yo no puedo a esa hora, suerte muchachos.
[01/09/2026, 11:15:40 AM] Juanda: HOY 01 SEPTIEMBRE
Categoría: 4ta
⌚8:00pm - 9:30pm
📍Capital Pádel Club
CANCHA 1
💰35.000

🎾Juanda
🎾Edinson
🎾Charlie
🎾Jose G

PARTIDO CERRADO
[02/09/2026, 03:20:10 PM] Felipe: MAÑANA 02 SEPTIEMBRE
Categoría: 3ra
⌚6:00pm - 7:30pm
CANCHA 3
💰40.000

🎾Felipe
🎾Andrés V
🎾Sebastián
🎾Nicolás

PARTIDO CERRADO"""

def test_radar_inmemory():
    with TestClient(app) as client:
        # 1. Invalid PDF file upload
        bad_res = client.post(
            "/api/v1/radar/upload-chat",
            files={"file": ("chat.pdf", b"fake pdf content", "application/pdf")}
        )
        assert bad_res.status_code == 400

        # 2. Valid WhatsApp export file upload
        res = client.post(
            "/api/v1/radar/upload-chat",
            files={"file": ("chat_convocatorias_septiembre.txt", chat_sample.encode("utf-8"), "text/plain")}
        )
        assert res.status_code == 200
        data = res.json()
        kpis = data["kpis"]
        assert kpis["total_matches_detected"] == 3
        assert kpis["closed_matches"] == 2
        assert kpis["open_matches"] == 1
        assert kpis["closure_rate_percent"] == 66.67
        assert "6:00pm - 7:30pm" in kpis["top_time_slots"]

if __name__ == "__main__":
    test_radar_inmemory()
    print("Radar in-memory test passed!")
