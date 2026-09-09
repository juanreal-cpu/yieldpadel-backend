import sys
import os
import time as _time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.models.user import UserRole

def test_rbac_roles():
    assert UserRole.GERENTE == "GERENTE"
    assert UserRole.ADMIN == "ADMIN"
    assert UserRole.STAFF == "STAFF"
    assert UserRole.RECEPCION == "RECEPCION"
    assert UserRole.AUXILIAR == "AUXILIAR"
    assert UserRole.SUPERADMIN == "SUPERADMIN"
    print("[OK] UserRole enum successfully includes SUPERADMIN, GERENTE, ADMIN, STAFF, RECEPCION, AUXILIAR.")

def test_collision_guard_overlapping():
    with TestClient(app) as client:
        res_courts = client.get("/api/v1/courts/")
        courts = res_courts.json() if res_courts.status_code == 200 else []
        court_id = courts[0]["id"] if (courts and isinstance(courts, list) and len(courts) > 0) else 1

        unique_date = f"2026-12-{int(_time.time() % 25) + 1:02d}"

        res1 = client.post("/api/v1/slots/manual-booking", json={
            "court_id": court_id,
            "date": unique_date,
            "start_time": "10:00",
            "duration_minutes": 90,
            "mode": "FULL_COURT",
            "client_name": "Jugador Inicial",
            "client_phone": "+573111111111",
            "price": 80000.0,
        })
        assert res1.status_code == 200
        print("[OK] Initial booking from 10:00 to 11:30 confirmed.")

        res_overlap = client.post("/api/v1/slots/manual-booking", json={
            "court_id": court_id,
            "date": unique_date,
            "start_time": "10:30",
            "duration_minutes": 90,
            "mode": "FULL_COURT",
            "client_name": "Jugador Solapado",
            "client_phone": "+573222222222",
            "price": 80000.0,
        })
        assert res_overlap.status_code == 409
        detail = res_overlap.json().get("detail", "")
        assert "Cancha ocupada" in detail
        print(f"[OK] Overlapping collision prevented with HTTP 409: {detail}")

        res_exact = client.post("/api/v1/slots/manual-booking", json={
            "court_id": court_id,
            "date": unique_date,
            "start_time": "10:00",
            "duration_minutes": 90,
            "mode": "FULL_COURT",
            "client_name": "Tercer Jugador",
            "client_phone": "+573333333333",
            "price": 80000.0,
        })
        assert res_exact.status_code == 409
        print("[OK] Exact rebooking collision prevented with HTTP 409.")

if __name__ == "__main__":
    test_rbac_roles()
    test_collision_guard_overlapping()
    print("ALL RBAC AND COLLISION TESTS PASSED!")
