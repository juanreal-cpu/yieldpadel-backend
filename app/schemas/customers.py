from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class BotRegisterCustomerRequest(BaseModel):
    phone: str = Field(..., description="Telefono del jugador (obligatorio)")
    name: str = Field(..., description="Nombre completo del jugador (obligatorio)")
    email: Optional[str] = Field(None, description="Correo electronico (opcional)")
    category_level: Optional[str] = Field(None, description="Categoria o nivel de juego (opcional, ej. '6ta', 'Principiante')")

    model_config = ConfigDict(extra="ignore")


class BotRegisterData(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    category: Optional[str] = None
    client_type: Optional[str] = None
    membership_tier: Optional[str] = None
    email: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class BotRegisterResponse(BaseModel):
    status: str = "success"
    message: str
    data: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")
