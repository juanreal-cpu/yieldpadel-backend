import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app

def test_multisport_americano_tournaments():
    with TestClient(app) as client:
        # 1. Obtenemos las canchas de la BD para tener IDs reales
        res_courts = client.get("/api/v1/courts/")
        assert res_courts.status_code == 200
        courts = res_courts.json()
        print(f"[OK] {len(courts)} canchas cargadas.")

        pickle_courts = [c for c in courts if (c.get("sport_type") or "").upper() == "PICKLEBALL"]
        padel_courts = [c for c in courts if (c.get("sport_type") or "").upper() == "PADEL"]

        assert len(pickle_courts) >= 2, f"Se esperaban al menos 2 canchas de pickleball, encontradas: {len(pickle_courts)}"
        assert len(padel_courts) >= 2, f"Se esperaban al menos 2 canchas de padel, encontradas: {len(padel_courts)}"

        pb_ids = [c["id"] for c in pickle_courts[:2]]
        padel_ids = [c["id"] for c in padel_courts[:2]]

        # 2. Test: Validación de menos de 2 canchas
        res_fail_min = client.post(
            "/api/v1/slots/create-americano",
            json={
                "tournament_name": "Test Fail Min Courts",
                "tournament_type": "PAREJA_FIJA",
                "court_ids": [pb_ids[0]],
                "date": "2026-10-15",
                "start_time": "18:00",
                "duration_minutes": 120,
            }
        )
        assert res_fail_min.status_code == 400
        assert "al menos 2 canchas" in res_fail_min.json()["detail"]
        print("[OK] Validación mínima de canchas superada.")

        # 3. Test: Validación de cancha inexistente
        res_fail_notfound = client.post(
            "/api/v1/slots/create-americano",
            json={
                "tournament_name": "Test Fail Invalid Court",
                "tournament_type": "PAREJA_FIJA",
                "court_ids": ["cancha_que_no_existe_xyz_123", pb_ids[0]],
                "date": "2026-10-15",
                "start_time": "18:00",
                "duration_minutes": 120,
            }
        )
        assert res_fail_notfound.status_code == 400
        assert "No se encontró la cancha" in res_fail_notfound.json()["detail"]
        print("[OK] Validación de cancha inexistente superada.")

        # 4. Test: Crear Torneo Americano de PICKLEBALL con UUIDs
        pb_payload = {
            "name": "Americano Pickleball Open 2026",
            "tournament_name": "Americano Pickleball Open 2026",
            "nombre": "Americano Pickleball Open 2026",
            "modality": "PAREJA_FIJA",
            "tournament_type": "PAREJA_FIJA",
            "modalidad": "PAREJA_FIJA",
            "sport_type": "PICKLEBALL",
            "sport": "PICKLEBALL",
            "court_ids": pb_ids,
            "date": "2026-10-20",
            "start_time": "18:00",
            "duration_minutes": 150,
            "price_per_player": 40000.0,
            "precio_inscripcion": 40000.0,
            "price_total_cop": 40000.0,
            "prize_pool": 200000.0,
            "bolsa_premio": 200000.0
        }
        res_create_pb = client.post("/api/v1/slots/create-americano", json=pb_payload)
        assert res_create_pb.status_code == 200, f"Error creando torneo pickleball: {res_create_pb.text}"
        pb_slots = res_create_pb.json()
        assert len(pb_slots) == 2, f"Se esperaban 2 slots creados, obtenidos: {len(pb_slots)}"

        for s in pb_slots:
            assert s["slot_type"] == "TOURNAMENT", f"slot_type esperado TOURNAMENT, obtenido {s['slot_type']}"
            assert s["sport_type"] == "PICKLEBALL", f"sport_type esperado PICKLEBALL, obtenido {s['sport_type']}"
            assert s["tournament_name"] == "Americano Pickleball Open 2026"
            assert s["status"] == "BLOCKED"
        print("[OK] Torneo Americano de Pickleball creado exitosamente con UUIDs.")

        # 5. Test: Verificar list_tournaments con filtro sport=PICKLEBALL
        res_tourn_pb = client.get("/api/v1/tournaments/?sport=PICKLEBALL")
        assert res_tourn_pb.status_code == 200
        data_pb = res_tourn_pb.json()
        upcoming_pb = data_pb.get("upcoming", [])
        assert any(t["tournament_name"] == "Americano Pickleball Open 2026" for t in upcoming_pb), \
            f"El torneo de Pickleball no se encontró en upcoming: {upcoming_pb}"
        print("[OK] list_tournaments/?sport=PICKLEBALL lista el torneo correctamente.")

        # 6. Test: Crear Torneo Americano con aliases de Pickleball (pb1, pb2)
        alias_payload = {
            "name": "Americano Pickleball Alias Test",
            "court_ids": ["pb1", "pb2"],
            "date": "2026-10-21",
            "start_time": "14:00",
            "duration_minutes": 120,
            "modalidad": "INDIVIDUAL",
            "precio_inscripcion": 35000.0,
            "bolsa_premio": 180000.0
        }
        res_alias = client.post("/api/v1/slots/create-americano", json=alias_payload)
        assert res_alias.status_code == 200, f"Error con aliases: {res_alias.text}"
        alias_slots = res_alias.json()
        assert len(alias_slots) == 2
        assert all(s["sport_type"] == "PICKLEBALL" for s in alias_slots)
        print("[OK] Torneo con aliases 'pb1' y 'pb2' resuelto y creado correctamente.")

        # 7. Test: Crear Torneo Americano de PADEL con Cancha 1 a 3
        padel_payload = {
            "name": "Americano Padel Nocturno 4ta",
            "tournament_name": "Americano Padel Nocturno 4ta",
            "modality": "PAREJA_FIJA",
            "court_ids": padel_ids,
            "date": "2026-10-22",
            "start_time": "19:00",
            "duration_minutes": 150,
            "price_per_player": 50000.0,
            "prize_pool": 300000.0
        }
        res_create_padel = client.post("/api/v1/slots/create-americano", json=padel_payload)
        assert res_create_padel.status_code == 200
        padel_slots = res_create_padel.json()
        assert len(padel_slots) == 2
        assert all(s["sport_type"] == "PADEL" for s in padel_slots)
        assert all(s["slot_type"] == "TOURNAMENT" for s in padel_slots)
        print("[OK] Torneo Americano de Pádel creado exitosamente.")

        # 8. Test: Verificar endpoint alterno /api/v1/tournaments/create-americano
        res_alt_tourn = client.post("/api/v1/tournaments/create-americano", json=padel_payload)
        assert res_alt_tourn.status_code in (200, 201)
        print("[OK] Endpoint alterno /api/v1/tournaments/create-americano funciona correctamente.")

if __name__ == "__main__":
    test_multisport_americano_tournaments()
    print("ALL MULTISPORT AMERICANO TOURNAMENT TESTS PASSED!")
