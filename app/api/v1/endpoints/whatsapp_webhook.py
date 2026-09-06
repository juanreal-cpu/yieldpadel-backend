"""
Compatibilidad hacia atrás para whatsapp_webhook.
Delega directamente al router y servicios centralizados en
app.api.v1.endpoints.whatsapp y app.services.whatsapp.
"""
from app.api.v1.endpoints.whatsapp import router, receive_webhook, verify_webhook
from app.services.whatsapp import send_whatsapp_message, process_incoming_whatsapp_message

__all__ = ["router", "receive_webhook", "verify_webhook", "send_whatsapp_message", "process_incoming_whatsapp_message"]
