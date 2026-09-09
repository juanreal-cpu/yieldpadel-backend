import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app

def test_membership_perks_and_autodetection():
    with TestClient(app) as client:
        # 1. Customer search returns perk and membership fields
        res_search = client.get("/api/v1/customers/search?q=Camilo")
        assert res_search.status_code == 200
        customers = res_search.json()
        assert isinstance(customers, list) and len(customers) > 0
        c0 = customers[0]
        assert "plan_name" in c0
        assert "americano_discount_pct" in c0
        assert "includes_beverage_perk" in c0
        print(f"[OK] Customer search verified: name={c0.get('name')}, tier={c0.get('membership_tier')}, plan={c0.get('plan_name')}, desc_tourn={c0.get('americano_discount_pct')}%, beverage_perk={c0.get('includes_beverage_perk')}")
        assert c0.get("membership_tier") == "TAPIA"
        assert c0.get("includes_beverage_perk") is True
        assert c0.get("americano_discount_pct") in (30, 40)

        # 2. Manual booking with Member Exempt auto-detection
        res_courts = client.get("/api/v1/courts/")
        courts = res_courts.json() if res_courts.status_code == 200 else []
        court_id = courts[0]["id"] if courts else 1

        import time as _time
        unique_date = f"2026-11-{int(_time.time() % 25) + 1:02d}"

        booking_payload = {
            "court_id": court_id,
            "date": unique_date,
            "start_time": "11:00",
            "duration_minutes": 90,
            "mode": "FULL_COURT",
            "client_name": "Camilo Real",
            "client_phone": "+573001234567",
            "client_tier": "TAPIA",
            "price": 0.0,
            "category": "1ra"
        }
        res_booking = client.post("/api/v1/slots/manual-booking", json=booking_payload)
        assert res_booking.status_code == 200
        b_data = res_booking.json()
        assert b_data.get("status") in ("ok", "success")
        print(f"[OK] Manual booking with VIP tier TAPIA succeeded: {b_data.get('message')}")

        # Test collision guard: booking the same slot again must return 409 Conflict
        res_collision = client.post("/api/v1/slots/manual-booking", json={
            "court_id": court_id,
            "date": unique_date,
            "start_time": "11:00",
            "duration_minutes": 90,
            "mode": "FULL_COURT",
            "client_name": "Juan Perez",
            "client_phone": "+573009998877",
            "price": 100000.0,
        })
        assert res_collision.status_code == 409
        assert "Cancha ocupada" in res_collision.json().get("detail", "")
        print("[OK] Collision Guard anti-overbooking verified: HTTP 409 Conflict returned on occupied court.")

        # 3. Tournament registration with auto-detected membership discount
        res_t_list = client.get("/api/v1/tournaments/?sport=PADEL")
        assert res_t_list.status_code == 200
        t_data_list = res_t_list.json()
        upcoming = t_data_list.get("upcoming", [])
        if upcoming:
            t_item = upcoming[0]
            tourn_payload = {
                "tournament_name": t_item.get("tournament_name"),
                "date": t_item.get("date"),
                "start_time": t_item.get("start_time"),
                "slot_ids": t_item.get("slot_ids"),
                "player1_name": "Camilo Real",
                "player1_phone": "+573001234567",
                "membership_tier": "TAPIA"
            }
            res_tourn = client.post("/api/v1/tournaments/register-player", json=tourn_payload)
            assert res_tourn.status_code == 200
            t_data = res_tourn.json()
            assert t_data.get("status") in ("ok", "success")
            print(f"[OK] Tournament registration succeeded: message={t_data.get('message')}")
            assert "30%" in t_data.get("message", "") or "40%" in t_data.get("message", "") or "TAPIA" in t_data.get("message", "")

        # 4. POS Order with perk product auto-discounted to $0 for VIP member
        res_prods = client.get("/api/v1/pos/products")
        assert res_prods.status_code == 200
        prods = res_prods.json()
        perk_prod = next((p for p in prods if p.get("is_membership_perk")), prods[0])

        pos_payload = {
            "slot_id": None,
            "items": [
                {
                    "product_id": perk_prod["id"],
                    "quantity": 1,
                    "is_perk": False
                }
            ],
            "customer_name": "Camilo Real",
            "customer_phone": "+573001234567",
            "customer_tier": "TAPIA",
            "payment_status": "PAID"
        }
        res_pos = client.post("/api/v1/pos/orders/create", json=pos_payload)
        assert res_pos.status_code in (200, 201)
        p_data = res_pos.json()
        print(f"[OK] POS order with membership perk created: total={p_data.get('total_amount')}, order_id={p_data.get('order_id')}")
        assert p_data.get("total_amount") == 0.0

if __name__ == "__main__":
    test_membership_perks_and_autodetection()
    print("ALL CUSTOMER PERKS AND MEMBERSHIP AUTO-DETECTION TESTS PASSED!")
