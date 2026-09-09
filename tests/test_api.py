import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app

def test_all_endpoints_inmemory():
    with TestClient(app) as client:
        # 1. Health check
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        print("[OK] Health check")

        # 2. Courts
        res = client.get("/api/v1/courts/")
        assert res.status_code == 200
        courts = res.json()
        assert isinstance(courts, list)
        print(f"[OK] Courts list ({len(courts)} canchas)")

        # 3. Slots Courts
        res = client.get("/api/v1/slots/courts")
        assert res.status_code == 200
        assert isinstance(res.json(), list)
        print("[OK] Slots courts")

        # 4. Seed weekly template
        res = client.post("/api/v1/slots/seed-weekly-template", json={"date": "2026-09-08"})
        assert res.status_code == 200
        print("[OK] Seed weekly template")

        # 5. Manual booking
        if courts:
            court_id = courts[0]["id"]
            booking_payload = {
                "court_id": court_id,
                "date": "2026-09-08",
                "start_time": "18:00",
                "duration_minutes": 90,
                "mode": "FULL_COURT",
                "client_name": "Test In-Memory Player",
                "client_phone": "+573009998877",
                "price": 90000.0,
                "category": "4ta"
            }
            res_booking = client.post("/api/v1/slots/manual-booking", json=booking_payload)
            assert res_booking.status_code == 200
            data = res_booking.json()
            assert data.get("status") in ("ok", "success")
            print("[OK] Manual booking")

if __name__ == "__main__":
    test_all_endpoints_inmemory()
    print("All in-memory API tests passed!")
