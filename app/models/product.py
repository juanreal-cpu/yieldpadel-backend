from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="BEBIDAS"
    )  # 'BEBIDAS', 'SNACKS', 'EQUIPAMIENTO', 'ALQUILER'
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0.00"))
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_membership_perk: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    slot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("time_slots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_name: Mapped[str] = mapped_column(String(150), default="Cliente Barra", nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    payment_status: Mapped[str] = mapped_column(
        String(50), default="PENDING", nullable=False
    )  # 'PENDING', 'PAID'
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    items: Mapped[List["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    is_perk: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    customer_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    customer_name: Mapped[str] = mapped_column(String(150), default="Mesa / Cuenta General", nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    product: Mapped["Product"] = relationship("Product", lazy="joined")


# Alias for compatibility
Sale = Order

INITIAL_DUMMY_PRODUCTS = [
    {
        "name": "Alquiler Pala",
        "category": "ALQUILER",
        "price": Decimal("15000.00"),
        "stock": 12,
        "is_membership_perk": False,
    },
    {
        "name": "Tubo de Bolas",
        "category": "EQUIPAMIENTO",
        "price": Decimal("28000.00"),
        "stock": 30,
        "is_membership_perk": False,
    },
    {
        "name": "Gatorade 500ml",
        "category": "BEBIDAS",
        "price": Decimal("7000.00"),
        "stock": 48,
        "is_membership_perk": True,
    },
    {
        "name": "Agua Cristal 600ml",
        "category": "BEBIDAS",
        "price": Decimal("4000.00"),
        "stock": 60,
        "is_membership_perk": False,
    },
    {
        "name": "Gaseosa Coca-Cola / Postobón",
        "category": "BEBIDAS",
        "price": Decimal("5000.00"),
        "stock": 36,
        "is_membership_perk": False,
    },
    {
        "name": "Paquete Papas / Snacks",
        "category": "SNACKS",
        "price": Decimal("5000.00"),
        "stock": 40,
        "is_membership_perk": False,
    },
]
