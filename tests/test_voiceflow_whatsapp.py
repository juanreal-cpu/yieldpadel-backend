from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.v1.endpoints.whatsapp import (
    VOICEFLOW_FALLBACK_MESSAGE,
    _extract_voiceflow_text_messages,
)
from app.main import app


def test_extract_voiceflow_text_and_speak_traces():
    traces = [
        {"type": "text", "payload": {"message": "Hola Juan"}},
        {"type": "choice"},
        {"type": "speak", "payload": {"message": "¿Quieres reservar?"}},
        {"type": "end"},
    ]
    assert _extract_voiceflow_text_messages(traces) == ["Hola Juan", "¿Quieres reservar?"]
    assert _extract_voiceflow_text_messages({"traces": traces[:1]}) == ["Hola Juan"]


def _webhook_payload(body: str, wa_id: str = "573132058547"):
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{"wa_id": wa_id, "profile": {"name": "Juan"}}],
                    "messages": [{
                        "id": "wamid.1",
                        "from": wa_id,
                        "type": "text",
                        "text": {"body": body},
                    }],
                }
            }]
        }]
    }


def test_whatsapp_webhook_returns_200_and_fallback_when_voiceflow_fails():
    with patch(
        "app.api.v1.endpoints.whatsapp.interact_with_voiceflow",
        new=AsyncMock(side_effect=Exception("vf down")),
    ), patch(
        "app.api.v1.endpoints.whatsapp.send_whatsapp_message",
        new=AsyncMock(return_value=True),
    ) as send_mock, patch(
        "app.api.v1.endpoints.whatsapp.is_conversation_paused",
        new=AsyncMock(return_value=False),
    ), patch(
        "app.api.v1.endpoints.whatsapp.log_conversation_message",
        new=AsyncMock(),
    ), patch(
        "app.api.v1.endpoints.whatsapp.process_incoming_whatsapp_message",
        new=AsyncMock(),
    ) as native_mock:
        client = TestClient(app)
        res = client.post("/api/v1/whatsapp/webhook", json=_webhook_payload("Cuántos puntos tengo?"))
        assert res.status_code == 200
        assert res.json()["status"] == "received"
        native_mock.assert_not_awaited()
        send_mock.assert_awaited()
        sent_body = send_mock.await_args.kwargs.get("message_body") or send_mock.await_args.args[1]
        assert sent_body == VOICEFLOW_FALLBACK_MESSAGE


def test_text_messages_never_download_audio_and_persist_immediately():
    payload = _webhook_payload("Hola, hay cancha?")
    payload["entry"][0]["changes"][0]["value"]["messages"][0]["audio"] = None
    with patch(
        "app.api.v1.endpoints.whatsapp.download_whatsapp_media_by_id",
        new=AsyncMock(side_effect=AssertionError("no debe descargar audio en type=text")),
    ) as audio_mock, patch(
        "app.api.v1.endpoints.whatsapp.interact_with_voiceflow",
        new=AsyncMock(return_value=["Hola desde VF"]),
    ), patch(
        "app.api.v1.endpoints.whatsapp.send_whatsapp_message",
        new=AsyncMock(return_value=True),
    ), patch(
        "app.api.v1.endpoints.whatsapp.is_conversation_paused",
        new=AsyncMock(return_value=False),
    ), patch(
        "app.api.v1.endpoints.whatsapp.log_conversation_message",
        new=AsyncMock(),
    ) as log_mock:
        client = TestClient(app)
        res = client.post("/api/v1/whatsapp/webhook", json=payload)
        assert res.status_code == 200
        audio_mock.assert_not_awaited()
        assert log_mock.await_count >= 1
        first_body = log_mock.await_args_list[0].kwargs.get("body") or log_mock.await_args_list[0].args[2]
        assert first_body == "Hola, hay cancha?"
        assert log_mock.await_args_list[0].kwargs.get("direction") == "incoming"


def test_hola_reaches_voiceflow_even_if_inbox_persist_fails():
    with patch(
        "app.api.v1.endpoints.whatsapp.log_conversation_message",
        new=AsyncMock(side_effect=Exception("supabase down")),
    ), patch(
        "app.api.v1.endpoints.whatsapp.interact_with_voiceflow",
        new=AsyncMock(return_value=["Hola, ¿en qué te ayudo?"]),
    ) as vf_mock, patch(
        "app.api.v1.endpoints.whatsapp.send_whatsapp_message",
        new=AsyncMock(return_value=True),
    ) as send_mock, patch(
        "app.api.v1.endpoints.whatsapp.is_conversation_paused",
        new=AsyncMock(side_effect=Exception("db paused check down")),
    ):
        client = TestClient(app)
        res = client.post("/api/v1/whatsapp/webhook", json=_webhook_payload("Hola"))
        assert res.status_code == 200
        assert res.json()["status"] == "received"
        vf_mock.assert_awaited()
        sent_body = send_mock.await_args.kwargs.get("message_body") or send_mock.await_args.args[1]
        assert sent_body == "Hola, ¿en qué te ayudo?"
        assert sent_body != VOICEFLOW_FALLBACK_MESSAGE


def test_transactional_messages_skip_voiceflow():
    with patch(
        "app.api.v1.endpoints.whatsapp.interact_with_voiceflow",
        new=AsyncMock(return_value=["no debe llamarse"]),
    ) as vf_mock, patch(
        "app.api.v1.endpoints.whatsapp.process_incoming_whatsapp_message",
        new=AsyncMock(return_value="Turno confirmado"),
    ) as native_mock, patch(
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
        res = client.post("/api/v1/whatsapp/webhook", json=_webhook_payload("🎾 voy"))
        assert res.status_code == 200
        vf_mock.assert_not_awaited()
        native_mock.assert_awaited()
