from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    pass


class WhatsAppConversation(Base):
    """Bandeja de conversaciones de WhatsApp: estado de pausa del bot y resumen para el inbox del Dashboard."""
    __tablename__ = "whatsapp_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_phone: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    player_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    last_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unread_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_bot_paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    messages: Mapped[List["WhatsAppMessage"]] = relationship(
        "WhatsAppMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="WhatsAppMessage.created_at",
    )


class WhatsAppMessage(Base):
    """Historial de mensajes de una conversación (entrante del cliente, del bot, o del asesor humano)."""
    __tablename__ = "whatsapp_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("whatsapp_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(20), default="incoming", nullable=False)  # incoming, bot, staff
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    conversation: Mapped["WhatsAppConversation"] = relationship("WhatsAppConversation", back_populates="messages")
