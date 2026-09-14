from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.v1.endpoints.whatsapp import _extract_voiceflow_text_messages
from app.main import app


def test_extract_voiceflow_text_traces():
    traces = [
        {"type": "text", "payload": {"message": "Hola Juan"}},
        {"type": "choice"},
        {"type": "text", "payload": {"message": "¿Quieres reservar?"}},
        {"type": "end"},
    ]
    assert _extract_voiceflow_text_messages(traces) == ["Hola Juan", "¿Quieres reservar?"]
    assert _extract_voiceflow_text_messages({"traces": traces[:1]}) == ["Hola Juan"]


def test_whatsapp_webhook_returns_200_when_voiceflow_fails():
    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{"wa_id": "573001112233", "profile": {"name": "Juan"}}],
                    "messages": [{
                        "id": "wamid.1",
                        "from": "573001112233",
                        "type": "text",
                        "text": {"body": "Hola, hay cancha?"},
                    }],
                }
            }]
        }]
    }
    with patch(
        "app.api.v1.endpoints.whatsapp.interact_with_voiceflow",
        new=AsyncMock(side_effect=Exception("vf down")),
    ), patch(
        "app.api.v1.endpoints.whatsapp.generate_concierge_reply",
        new=AsyncMock(return_value="Hola"),
    ), patch(
        "app.api.v1.endpoints.whatsapp.send_whatsapp_message",
        new=AsyncMock(return_value=True),
    ), patch(
        "app.api.v1.endpoints.whatsapp.is_conversation_paused",
        new=AsyncMock(return_value=False),
    ), patch(
        "app.api.v1.endpoints.whatsapp.log_conversation_message",
        new=AsyncMock(),
    ):
        client = TestClient(app)
        res = client.post("/api/v1/whatsapp/webhook", json=payload)
        assert res.status_code == 200
        assert res.json()["status"] == "received"
