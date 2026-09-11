from datetime import date, datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.court import Court
from app.models.customer import Customer
from app.models.product import INITIAL_DUMMY_PRODUCTS, Order, OrderItem, Product
from app.models.slot import HoldStatus, PaymentStatus, SlotStatus, TimeSlot
from app.models.accounting import DailyAccountingLedger
from app.services.audit import log_activity
from app.services.whatsapp import send_whatsapp_message, log_conversation_message, normalize_phone

logger = logging.getLogger("yieldpadel.pos")

router = APIRouter()


# ----------------------------------------------------
# Schemas
# ----------------------------------------------------
class ProductItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)
    is_perk: bool = False


class CreateOrderRequest(BaseModel):
    slot_id: Optional[int] = None
    customer_id: Optional[int] = None
    customer_name: str = "Cliente Mostrador"
    customer_phone: Optional[str] = None
    customer_tier: Optional[str] = None
    items: List[ProductItemCreate] = Field(default_factory=list)
    payment_status: str = "PENDING"  # 'PENDING', 'PAID'


class AddStockRequest(BaseModel):
    quantity: int = Field(..., ge=1)


class CreateProductRequest(BaseModel):
    name: str
    category: str = "BEBIDAS"  # 'BEBIDAS', 'SNACKS', 'EQUIPAMIENTO', 'ALQUILER'
    price: float = Field(..., ge=0)
    stock: int = Field(default=0, ge=0)
    is_membership_perk: bool = False


class AddItemToSlotRequest(BaseModel):
    slot_id: int
    product_id: int
    quantity: int = Field(default=1, ge=1)
    is_membership_perk: bool = False
    player_name: Optional[str] = None
    customer_id: Optional[int] = None


class CheckoutOrderRequest(BaseModel):
    payment_method: str = "EFECTIVO"  # EFECTIVO, DATAFONO, BOLD_WOMPI, SALDO_A_FAVOR, SPLIT
    discount_amount: float = 0.0
    amount_cash: float = 0.0
    amount_card: float = 0.0


class CheckoutResponse(BaseModel):
    order_id: int
    slot_id: Optional[int] = None
    customer_name: str
    court_price: float
    bar_total: float
    membership_discount: float = 0.0
    total_to_pay: float
    payment_method: str = "EFECTIVO"
    payment_status: str


# ----------------------------------------------------
# Helper Functions
# ----------------------------------------------------
async def ensure_seed_products(db: AsyncSession):
    """Carga los productos dummy iniciales si la tabla de productos está vacía."""
    stmt = select(func.count(Product.id))
    res = await db.execute(stmt)
    count = res.scalar() or 0
    if count == 0:
        logger.info("Poblando inventario inicial dummy...")
        for p_data in INITIAL_DUMMY_PRODUCTS:
            prod = Product(
                name=p_data["name"],
                category=p_data["category"],
                price=Decimal(str(p_data["price"])),
                stock=int(p_data["stock"]),
                is_membership_perk=bool(p_data["is_membership_perk"]),
            )
            db.add(prod)
        await db.commit()


# ----------------------------------------------------
# Endpoints de Productos e Inventario
# ----------------------------------------------------
@router.get("/products", summary="Listar productos del catálogo e inventario")
async def list_products(
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    db: AsyncSession = Depends(get_db),
):
    await ensure_seed_products(db)

    stmt = select(Product)
    if category and category.upper() != "ALL":
        stmt = stmt.where(Product.category == category.upper())
    stmt = stmt.order_by(Product.category, Product.name)

    res = await db.execute(stmt)
    products = res.scalars().all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "price": float(p.price),
            "stock": p.stock,
            "is_membership_perk": p.is_membership_perk,
        }
        for p in products
    ]


@router.post("/products", status_code=status.HTTP_201_CREATED, summary="Crear nuevo producto")
async def create_product(
    payload: CreateProductRequest,
    db: AsyncSession = Depends(get_db),
):
    prod = Product(
        name=payload.name.strip(),
        category=payload.category.upper().strip(),
        price=Decimal(str(payload.price)),
        stock=payload.stock,
        is_membership_perk=payload.is_membership_perk,
    )
    db.add(prod)
    await db.commit()
    await db.refresh(prod)
    return {
        "id": prod.id,
        "name": prod.name,
        "category": prod.category,
        "price": float(prod.price),
        "stock": prod.stock,
        "is_membership_perk": prod.is_membership_perk,
    }


@router.post("/products/{product_id}/stock", summary="Agregar stock a un producto")
async def add_stock(
    product_id: int,
    payload: AddStockRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Product).where(Product.id == product_id)
    res = await db.execute(stmt)
    prod = res.scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    prod.stock += payload.quantity
    await db.commit()
    await db.refresh(prod)

    return {
        "success": True,
        "product_id": prod.id,
        "name": prod.name,
        "new_stock": prod.stock,
        "added": payload.quantity,
    }


# ----------------------------------------------------
# Endpoints de Canchas Activas y Turnos en Juego
# ----------------------------------------------------
@router.get("/orders/active-slots", summary="Listar canchas activas y turnos en juego hoy")
async def get_active_slots(db: AsyncSession = Depends(get_db)):
    """Obtiene las canchas con turnos asignados u ocupados para gestionar consumos de barra."""
    try:
        await ensure_seed_products(db)
        today_date = date.today()

        # Obtener todas las canchas
        courts_stmt = select(Court).where(Court.is_active == True).order_by(Court.name)
        res_courts = await db.execute(courts_stmt)
        courts = res_courts.scalars().all()

        # Obtener slots de hoy con relaciones
        slots_stmt = (
            select(TimeSlot)
            .options(
                selectinload(TimeSlot.court),
                selectinload(TimeSlot.holds),
                selectinload(TimeSlot.bookings),
            )
            .where(TimeSlot.date == today_date)
            .order_by(TimeSlot.start_time)
        )
        res_slots = await db.execute(slots_stmt)
        slots = res_slots.scalars().all()

        # Mapear slots por cancha
        slots_by_court: Dict[str, List[TimeSlot]] = {}
        for s in slots:
            c_id = str(s.court_id)
            if c_id not in slots_by_court:
                slots_by_court[c_id] = []
            slots_by_court[c_id].append(s)

        # Pre-identificar slot seleccionado para cada cancha
        selected_slots_map: Dict[str, Optional[TimeSlot]] = {}
        all_slot_ids = []
        now_t = datetime.now().time()

        for court in courts:
            c_id = str(court.id)
            court_slots = slots_by_court.get(c_id, [])
            sel: Optional[TimeSlot] = None
            for s in court_slots:
                if s.start_time <= now_t <= s.end_time:
                    sel = s
                    break
            if not sel:
                occupied = [
                    s
                    for s in court_slots
                    if s.status in [SlotStatus.PARTIALLY_BOOKED, SlotStatus.FULLY_BOOKED]
                    or bool(s.players_names)
                ]
                sel = occupied[0] if occupied else (court_slots[0] if court_slots else None)
            selected_slots_map[c_id] = sel
            if sel:
                all_slot_ids.append(sel.id)

        # 1. Cargar todas las órdenes PENDING en un solo query
        orders_by_slot: Dict[int, Order] = {}
        if all_slot_ids:
            order_stmt = (
                select(Order)
                .options(selectinload(Order.items).selectinload(OrderItem.product))
                .where(Order.slot_id.in_(all_slot_ids), Order.payment_status == "PENDING")
                .order_by(desc(Order.created_at))
            )
            order_res = await db.execute(order_stmt)
            for ord_item in order_res.scalars().all():
                if ord_item.slot_id and ord_item.slot_id not in orders_by_slot:
                    orders_by_slot[ord_item.slot_id] = ord_item

        # 2. Cargar clientes en un solo query para resolver membresías en memoria
        cust_res = await db.execute(select(Customer))
        all_customers = cust_res.scalars().all()

        def find_customer_by_name(name_query: Optional[str]) -> Optional[Customer]:
            if not name_query:
                return None
            nq = name_query.strip().lower()
            # Coincidencia exacta o contenida
            for cust in all_customers:
                c_name = cust.name.strip().lower()
                if nq == c_name or nq in c_name or c_name in nq:
                    return cust
            return None

        active_courts_data = []

        for court in courts:
            c_id = str(court.id)
            selected_slot = selected_slots_map.get(c_id)

            court_data = {
                "court_id": c_id,
                "court_name": court.name,
                "sport_type": getattr(court, "sport_type", "PADEL") or "PADEL",
                "has_active_match": False,
                "slot_id": None,
                "time_block": None,
                "court_price": 0.0,
                "players": [],
                "main_customer": None,
                "membership_tier": "ESTANDAR",
                "pending_order": None,
            }

            if selected_slot:
                court_data["slot_id"] = selected_slot.id
                court_data["time_block"] = (
                    f"{selected_slot.start_time.strftime('%H:%M')} - {selected_slot.end_time.strftime('%H:%M')}"
                )
                court_data["court_price"] = float(selected_slot.total_price)
                court_data["has_active_match"] = selected_slot.status in [
                    SlotStatus.PARTIALLY_BOOKED,
                    SlotStatus.FULLY_BOOKED,
                ] or bool(selected_slot.players_names)

                # Extraer jugadores
                players_list = []
                if selected_slot.players_names:
                    players_list.extend(selected_slot.players_names)

                for b in selected_slot.bookings or []:
                    if b.customer_name and b.customer_name not in players_list:
                        players_list.append(b.customer_name)

                for h in selected_slot.holds or []:
                    if (
                        h.status == HoldStatus.ACTIVE
                        and h.customer_phone
                        and h.customer_phone not in players_list
                    ):
                        players_list.append(h.customer_phone)

                court_data["players"] = players_list
                titular = None
                if selected_slot.players_names and len(selected_slot.players_names) > 0:
                    titular = selected_slot.players_names[0]
                if not titular and selected_slot.bookings:
                    for b in selected_slot.bookings:
                        if b.customer_name:
                            titular = b.customer_name
                            break
                if not titular and selected_slot.holds:
                    for h in selected_slot.holds:
                        if h.customer_phone:
                            titular = h.customer_phone
                            break

                responsable = titular if titular else "Reserva Mostrador / Sin Titular"
                court_data["main_customer"] = responsable

                # Detalle de jugadores con membresías para selección individual en POS (en memoria)
                players_details = []
                for p_name in players_list:
                    p_cust = find_customer_by_name(p_name)
                    players_details.append({
                        "name": p_name,
                        "tier": p_cust.membership_tier if p_cust else "ESTANDAR",
                        "customer_id": p_cust.id if p_cust else None,
                    })
                court_data["players_details"] = players_details

                # Buscar membresía del jugador titular
                customer = find_customer_by_name(titular) if titular else None
                if customer:
                    court_data["customer_id"] = customer.id
                    court_data["membership_tier"] = customer.membership_tier
                else:
                    court_data["customer_id"] = None
                    court_data["membership_tier"] = "ESTANDAR"

                # Orden pendiente desde memoria
                active_order = orders_by_slot.get(selected_slot.id)
                if active_order:
                    court_data["pending_order"] = {
                        "order_id": active_order.id,
                        "total_amount": float(active_order.total_amount),
                        "items_count": sum(it.quantity for it in active_order.items),
                        "items": [
                            {
                                "id": it.id,
                                "product_id": it.product_id,
                                "product_name": it.product.name if it.product else "Producto",
                                "quantity": it.quantity,
                                "unit_price": float(it.unit_price),
                                "subtotal": float(it.subtotal),
                                "is_perk": it.is_perk,
                                "customer_name": getattr(it, "customer_name", "Mesa / Cuenta General") or "Mesa / Cuenta General",
                                "customer_id": getattr(it, "customer_id", None),
                            }
                            for it in active_order.items
                        ],
                    }

            active_courts_data.append(court_data)

        return active_courts_data
    except Exception:
        logger.exception("Error obteniendo active-slots; devolviendo lista vacía")
        return []


# ----------------------------------------------------
# Endpoints de Órdenes y Consumos
# ----------------------------------------------------
@router.post("/orders", status_code=status.HTTP_201_CREATED, summary="Crear o agregar consumos a una orden")
@router.post("/orders/create", status_code=status.HTTP_201_CREATED, summary="Crear o agregar consumos a una orden (alias)")
async def create_or_add_order(
    payload: CreateOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    await ensure_seed_products(db)

    # Si hay un slot_id y ya existe una orden pendiente para ese slot, reutilizarla
    order: Optional[Order] = None
    if payload.slot_id:
        stmt_find = (
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.slot_id == payload.slot_id, Order.payment_status == "PENDING")
        )
        res_find = await db.execute(stmt_find)
        order = res_find.scalars().first()

    if not order:
        order = Order(
            slot_id=payload.slot_id,
            customer_id=payload.customer_id,
            customer_name=payload.customer_name.strip() or "Cliente Barra",
            total_amount=Decimal("0.00"),
            payment_status=payload.payment_status.upper(),
        )
        db.add(order)
        await db.flush()

    total_added = Decimal("0.00")

    # Detectar cortesía por membresía del cliente
    target_cust = None
    if payload.customer_id:
        c_res = await db.execute(select(Customer).options(selectinload(Customer.membership_plan)).where(Customer.id == payload.customer_id))
        target_cust = c_res.scalars().first()
    elif payload.customer_phone:
        c_res = await db.execute(select(Customer).options(selectinload(Customer.membership_plan)).where(Customer.phone == payload.customer_phone.strip()))
        target_cust = c_res.scalars().first()
    elif payload.customer_name and payload.customer_name.strip() not in ("Cliente Mostrador", "Cliente Barra"):
        c_res = await db.execute(select(Customer).options(selectinload(Customer.membership_plan)).where(Customer.name.ilike(payload.customer_name.strip())))
        target_cust = c_res.scalars().first()

    customer_has_beverage_perk = False
    effective_tier = (payload.customer_tier or (target_cust.membership_tier if target_cust else "") or "").strip().upper()
    if effective_tier in ("TAPIA", "COELLO", "GALAN", "CHINGOTTO", "LEBRON", "ORO", "PLATA"):
        customer_has_beverage_perk = True
    elif target_cust and target_cust.membership_plan and target_cust.membership_plan.includes_beverage_perk:
        customer_has_beverage_perk = True

    for item in payload.items:
        prod_stmt = select(Product).where(Product.id == item.product_id)
        prod_res = await db.execute(prod_stmt)
        product = prod_res.scalar_one_or_none()
        if not product:
            continue

        qty = max(1, item.quantity)
        # Descontar stock
        product.stock = max(0, product.stock - qty)

        # Regla de Membresías: cortesía a $0 COP si es perk
        is_perk_effective = bool(item.is_perk or (customer_has_beverage_perk and product.is_membership_perk))
        if is_perk_effective:
            unit_price = Decimal("0.00")
            subtotal = Decimal("0.00")
        else:
            unit_price = product.price
            subtotal = unit_price * qty

        total_added += subtotal

        order_item = OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=qty,
            unit_price=unit_price,
            subtotal=subtotal,
            is_perk=is_perk_effective,
        )
        db.add(order_item)

    order.total_amount += total_added
    await db.commit()
    await db.refresh(order)

    # Log de Auditoría Operativa
    try:
        await log_activity(
            db=db,
            action="VENTA_POS",
            entity_name="ORDER",
            entity_id=str(order.id),
            details=f"Venta POS ({order.payment_status}) por ${float(order.total_amount):,.0f} COP para {order.customer_name}",
            username_snapshot="Camilo Real (Recepción)",
        )
    except Exception as e:
        logger.warning(f"Error logging POS order audit: {e}")

    # Cargar relaciones completas para respuesta
    stmt_full = (
        select(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
        .where(Order.id == order.id)
    )
    res_full = await db.execute(stmt_full)
    order_full = res_full.scalar_one()

    return {
        "success": True,
        "order_id": order_full.id,
        "slot_id": order_full.slot_id,
        "customer_name": order_full.customer_name,
        "total_amount": float(order_full.total_amount),
        "payment_status": order_full.payment_status,
        "items": [
            {
                "id": it.id,
                "product_id": it.product_id,
                "product_name": it.product.name if it.product else "Producto",
                "quantity": it.quantity,
                "unit_price": float(it.unit_price),
                "subtotal": float(it.subtotal),
                "is_perk": it.is_perk,
            }
            for it in order_full.items
        ],
    }


@router.post(
    "/orders/add-item",
    status_code=status.HTTP_200_OK,
    summary="Añadir consumo a la orden de una cancha/slot",
)
async def add_item_to_slot_order(
    payload: AddItemToSlotRequest,
    db: AsyncSession = Depends(get_db),
):
    await ensure_seed_products(db)

    # 1. Buscar o crear la orden PENDING para el slot_id
    stmt_find = (
        select(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
        .where(Order.slot_id == payload.slot_id, Order.payment_status == "PENDING")
        .order_by(desc(Order.created_at))
    )
    res_find = await db.execute(stmt_find)
    order = res_find.scalars().first()

    if not order:
        cust_name = payload.player_name.strip() if payload.player_name else "Cliente Cancha"
        order = Order(
            slot_id=payload.slot_id,
            customer_name=cust_name,
            total_amount=Decimal("0.00"),
            payment_status="PENDING",
        )
        db.add(order)
        await db.flush()
    elif payload.player_name and order.customer_name in ["Cliente Barra", "Cliente Cancha", "Reserva Mostrador / Sin Titular"]:
        order.customer_name = payload.player_name.strip()

    # 2. Buscar producto
    prod_stmt = select(Product).where(Product.id == payload.product_id)
    prod_res = await db.execute(prod_stmt)
    product = prod_res.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    qty = max(1, payload.quantity)
    # Descontar stock
    product.stock = max(0, product.stock - qty)

    # Detectar cortesía de bebida por membresía
    player_has_beverage_perk = False
    if payload.player_name:
        p_res = await db.execute(
            select(Customer)
            .options(selectinload(Customer.membership_plan))
            .where(Customer.name.ilike(payload.player_name.strip()))
        )
        target_p = p_res.scalars().first()
        if target_p:
            if target_p.membership_plan and target_p.membership_plan.includes_beverage_perk:
                player_has_beverage_perk = True
            elif target_p.membership_tier and target_p.membership_tier.upper() in ("TAPIA", "COELLO", "GALAN", "CHINGOTTO", "LEBRON", "ORO", "PLATA"):
                player_has_beverage_perk = True

    is_perk_effective = bool(payload.is_membership_perk or (player_has_beverage_perk and product.is_membership_perk))

    # Regla de cortesía por membresía ($0)
    if is_perk_effective:
        unit_price = Decimal("0.00")
        subtotal = Decimal("0.00")
    else:
        unit_price = product.price
        subtotal = unit_price * qty

    cust_player_name = payload.player_name.strip() if payload.player_name else (order.customer_name or "Mesa / Cuenta General")
    order_item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        quantity=qty,
        unit_price=unit_price,
        subtotal=subtotal,
        is_perk=is_perk_effective,
        customer_id=payload.customer_id,
        customer_name=cust_player_name,
    )
    db.add(order_item)
    order.total_amount += subtotal

    await db.commit()
    await db.refresh(order)

    # Notificación transaccional de consumo / hidratación por WhatsApp
    target_phone = None
    if payload.customer_id:
        c_stmt = select(Customer).where(Customer.id == payload.customer_id)
        c_ent = (await db.execute(c_stmt)).scalars().first()
        if c_ent and c_ent.phone:
            target_phone = c_ent.phone
    elif payload.player_name and payload.player_name not in ("Mesa / Cuenta General", "Cliente Cancha"):
        c_stmt = select(Customer).where(Customer.name.ilike(payload.player_name.strip()))
        c_ent = (await db.execute(c_stmt)).scalars().first()
        if c_ent and c_ent.phone:
            target_phone = c_ent.phone

    if target_phone:
        sub_cop = f"${int(subtotal):,}".replace(",", ".")
        item_msg = (
            f"🥤 *¡Qué bien que te hidrates!* 🎾\n\n"
            f"Hola {cust_player_name}, registramos en tu cuenta:\n"
            f"• Consumo: {qty}x {product.name}\n"
            f"• Subtotal: {sub_cop} COP\n"
            f"• Turno #{payload.slot_id}\n\n"
            f"¡Sigue dándolo todo en la pista!"
        )
        try:
            await send_whatsapp_message(to_phone=target_phone, message_body=item_msg)
            await log_conversation_message(db, target_phone, item_msg, direction="bot", player_name=cust_player_name)
        except Exception as e:
            logger.warning(f"Error enviando WhatsApp de consumo: {e}")

    # Cargar relaciones completas para respuesta
    stmt_full = (
        select(Order)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
        .where(Order.id == order.id)
    )
    res_full = await db.execute(stmt_full)
    order_full = res_full.scalar_one()

    return {
        "success": True,
        "order_id": order_full.id,
        "slot_id": order_full.slot_id,
        "customer_name": order_full.customer_name,
        "total_amount": float(order_full.total_amount),
        "payment_status": order_full.payment_status,
        "items_count": sum(it.quantity for it in order_full.items),
        "items": [
            {
                "id": it.id,
                "product_id": it.product_id,
                "product_name": it.product.name if it.product else "Producto",
                "quantity": it.quantity,
                "unit_price": float(it.unit_price),
                "subtotal": float(it.subtotal),
                "is_perk": it.is_perk,
                "customer_name": getattr(it, "customer_name", "Mesa / Cuenta General") or "Mesa / Cuenta General",
                "customer_id": getattr(it, "customer_id", None),
            }
            for it in order_full.items
        ],
    }


@router.post(
    "/orders/{order_id}/checkout",
    response_model=CheckoutResponse,
    summary="Cerrar partido y liquidar consumos + cancha",
)
async def checkout_order(
    order_id: int,
    payload: Optional[CheckoutOrderRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    bar_total = float(order.total_amount)
    court_price = 0.0

    discount = float(payload.discount_amount) if payload and payload.discount_amount else 0.0
    payment_method = payload.payment_method if payload and payload.payment_method else "EFECTIVO"

    if order.slot_id:
        slot_stmt = (
            select(TimeSlot)
            .options(selectinload(TimeSlot.bookings))
            .where(TimeSlot.id == order.slot_id)
        )
        slot_res = await db.execute(slot_stmt)
        slot = slot_res.scalar_one_or_none()
        if slot:
            court_price = float(slot.total_price)
            slot.status = SlotStatus.AVAILABLE  # Liberar la cancha según requerimiento
            slot.closed_at = datetime.now(timezone.utc)
            for b in slot.bookings or []:
                b.payment_status = PaymentStatus.PAID

    total_to_pay = max(0.0, (court_price + bar_total) - discount)

    order.payment_status = "PAID"

    # Registro en DailyAccountingLedger
    try:
        from app.core.timezone import get_bogota_today
        pm = payment_method.upper()
        cash = Decimal(str(payload.amount_cash if payload else 0))
        card = Decimal(str(payload.amount_card if payload else 0))
        tot = Decimal(str(total_to_pay))
        dig = Decimal("0.00")

        if pm == "EFECTIVO":
            cash = tot
        elif pm == "DATAFONO":
            card = tot
        elif pm in ("BOLD_WOMPI", "TRANSFERENCIA"):
            dig = tot
        elif pm == "SPLIT":
            if cash == 0 and card == 0:
                cash = tot

        ledger_entry = DailyAccountingLedger(
            date=get_bogota_today(),
            customer_name=order.customer_name or "Cliente Cancha",
            concept="CANCHAS" if court_price > 0 else "TIENDA",
            details=f"Liquidación Orden #{order.id}: Cancha ${court_price:,.0f} + Barra ${bar_total:,.0f}",
            payment_method=pm,
            amount_cash=cash,
            amount_card=card,
            amount_digital=dig,
            total_amount=tot,
            operator="Recepcionista Turno",
            slot_id=order.slot_id,
            order_id=order.id,
        )
        db.add(ledger_entry)
    except Exception as e:
        logger.warning(f"Error registrando cierre en DailyAccountingLedger: {e}")

    await db.commit()
    await db.refresh(order)

    # Enviar recibo digital por WhatsApp al cliente titular
    cust_receipt_phone = None
    if order.customer_id:
        c_stmt = select(Customer).where(Customer.id == order.customer_id)
        c_ent = (await db.execute(c_stmt)).scalars().first()
        if c_ent and c_ent.phone:
            cust_receipt_phone = c_ent.phone
    elif order.customer_name and order.customer_name not in ("Cliente Mostrador", "Cliente Cancha", "Cliente Barra"):
        c_stmt = select(Customer).where(Customer.name.ilike(order.customer_name.strip()))
        c_ent = (await db.execute(c_stmt)).scalars().first()
        if c_ent and c_ent.phone:
            cust_receipt_phone = c_ent.phone

    if cust_receipt_phone:
        tot_cop = f"${int(total_to_pay):,}".replace(",", ".")
        receipt_msg = (
            f"🧾 *RECIBO DE PAGO DIGITAL - CAPITAL PÁDEL CLUB* 🎾\n\n"
            f"Hola {order.customer_name}, confirmamos el pago de tu cuenta:\n"
            f"• Recibo #: REC-ORD-{order.id}\n"
            f"• Cancha: ${int(court_price):,} COP\n"
            f"• Consumos Tienda/Barra: ${int(bar_total):,} COP\n"
            f"• Descuento: -${int(discount):,} COP\n"
            f"• *TOTAL PAGADO: {tot_cop} COP*\n"
            f"• Medio de Pago: {payment_method}\n\n"
            f"¡Gracias por jugar en Capital Pádel Club! Nos vemos en la próxima."
        ).replace(",", ".")
        try:
            await send_whatsapp_message(to_phone=cust_receipt_phone, message_body=receipt_msg)
            await log_conversation_message(db, cust_receipt_phone, receipt_msg, direction="bot", player_name=order.customer_name)
        except Exception as e:
            logger.warning(f"Error enviando recibo WhatsApp: {e}")

    return CheckoutResponse(
        order_id=order.id,
        slot_id=order.slot_id,
        customer_name=order.customer_name,
        court_price=court_price,
        bar_total=bar_total,
        membership_discount=discount,
        total_to_pay=total_to_pay,
        payment_method=payment_method,
        payment_status=order.payment_status,
    )


@router.post(
    "/slots/{slot_id}/checkout",
    response_model=CheckoutResponse,
    summary="Cerrar partido y liquidar directamente por slot",
)
async def checkout_slot(
    slot_id: int,
    payload: Optional[CheckoutOrderRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.slot_id == slot_id, Order.payment_status == "PENDING")
        .order_by(desc(Order.created_at))
    )
    res = await db.execute(stmt)
    order = res.scalars().first()

    court_price = 0.0
    slot_stmt = (
        select(TimeSlot)
        .options(selectinload(TimeSlot.bookings))
        .where(TimeSlot.id == slot_id)
    )
    slot_res = await db.execute(slot_stmt)
    slot = slot_res.scalar_one_or_none()
    if not slot:
        raise HTTPException(status_code=404, detail="Turno no encontrado")

    court_price = float(slot.total_price)
    slot.status = SlotStatus.AVAILABLE  # Liberar la cancha
    slot.closed_at = datetime.now(timezone.utc)
    for b in slot.bookings or []:
        b.payment_status = PaymentStatus.PAID

    bar_total = float(order.total_amount) if order else 0.0
    discount = float(payload.discount_amount) if payload and payload.discount_amount else 0.0
    payment_method = payload.payment_method if payload and payload.payment_method else "EFECTIVO"
    total_to_pay = max(0.0, (court_price + bar_total) - discount)

    if order:
        order.payment_status = "PAID"
        order_id = order.id
        customer_name = order.customer_name
    else:
        order_id = 0
        customer_name = "Cliente Cancha"

    # Registro en DailyAccountingLedger
    try:
        from app.core.timezone import get_bogota_today
        pm = payment_method.upper()
        cash = Decimal(str(payload.amount_cash if payload else 0))
        card = Decimal(str(payload.amount_card if payload else 0))
        tot = Decimal(str(total_to_pay))
        dig = Decimal("0.00")

        if pm == "EFECTIVO":
            cash = tot
        elif pm == "DATAFONO":
            card = tot
        elif pm in ("BOLD_WOMPI", "TRANSFERENCIA"):
            dig = tot
        elif pm == "SPLIT":
            if cash == 0 and card == 0:
                cash = tot

        ledger_entry = DailyAccountingLedger(
            date=get_bogota_today(),
            customer_name=customer_name or "Cliente Cancha",
            concept="CANCHAS",
            details=f"Liquidación Slot #{slot.id}: Cancha ${court_price:,.0f} + Consumos ${bar_total:,.0f}",
            payment_method=pm,
            amount_cash=cash,
            amount_card=card,
            amount_digital=dig,
            total_amount=tot,
            operator="Recepcionista Turno",
            slot_id=slot.id,
            order_id=order_id if order_id != 0 else None,
        )
        db.add(ledger_entry)
    except Exception as e:
        logger.warning(f"Error registrando cierre en DailyAccountingLedger: {e}")

    await db.commit()

    # Enviar recibo digital por WhatsApp al cliente del turno
    cust_receipt_phone = None
    if customer_name and customer_name not in ("Cliente Cancha", "Cliente Mostrador", "Cliente Barra"):
        c_stmt = select(Customer).where(Customer.name.ilike(customer_name.strip()))
        c_ent = (await db.execute(c_stmt)).scalars().first()
        if c_ent and c_ent.phone:
            cust_receipt_phone = c_ent.phone

    if cust_receipt_phone:
        tot_cop = f"${int(total_to_pay):,}".replace(",", ".")
        receipt_msg = (
            f"🧾 *RECIBO DE PAGO DIGITAL - CAPITAL PÁDEL CLUB* 🎾\n\n"
            f"Hola {customer_name}, confirmamos la liquidación de tu turno:\n"
            f"• Turno #{slot.id}\n"
            f"• Cancha: ${int(court_price):,} COP\n"
            f"• Consumos Tienda/Barra: ${int(bar_total):,} COP\n"
            f"• Descuento: -${int(discount):,} COP\n"
            f"• *TOTAL PAGADO: {tot_cop} COP*\n"
            f"• Medio de Pago: {payment_method}\n\n"
            f"¡Gracias por visitarnos en Capital Pádel Club!"
        ).replace(",", ".")
        try:
            await send_whatsapp_message(to_phone=cust_receipt_phone, message_body=receipt_msg)
            await log_conversation_message(db, cust_receipt_phone, receipt_msg, direction="bot", player_name=customer_name)
        except Exception as e:
            logger.warning(f"Error enviando recibo WhatsApp en checkout_slot: {e}")

    # Log de Auditoría Operativa
    try:
        await log_activity(
            db=db,
            action="VENTA_POS",
            entity_name="ORDER",
            entity_id=str(order_id),
            details=f"Liquidación y Checkout Partido ({payment_method}). Total: ${total_to_pay:,.0f} COP para {customer_name}",
            username_snapshot="Camilo Real (Recepción)",
        )
    except Exception as e:
        logger.warning(f"Error logging POS checkout audit: {e}")

    return CheckoutResponse(
        order_id=order_id,
        slot_id=slot.id,
        customer_name=customer_name,
        court_price=court_price,
        bar_total=bar_total,
        membership_discount=discount,
        total_to_pay=total_to_pay,
        payment_method=payment_method,
        payment_status="PAID",
    )


# ----------------------------------------------------
# Endpoints de Analítica de Barra POS
# ----------------------------------------------------
@router.get("/analytics/today", summary="Métricas analíticas de ventas en barra de hoy")
async def get_pos_analytics_today(db: AsyncSession = Depends(get_db)):
    await ensure_seed_products(db)

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. Total Facturado en Barra Hoy
    rev_stmt = select(func.sum(Order.total_amount)).where(
        Order.payment_status == "PAID", Order.created_at >= today_start
    )
    res_rev = await db.execute(rev_stmt)
    total_rev = res_rev.scalar() or Decimal("0.00")

    # 2. Número de Órdenes Hoy
    count_stmt = select(func.count(Order.id)).where(
        Order.payment_status == "PAID", Order.created_at >= today_start
    )
    res_count = await db.execute(count_stmt)
    orders_count = res_count.scalar() or 0

    # 3. Ticket Promedio
    avg_ticket = float(total_rev / orders_count) if orders_count > 0 else 0.0

    # 4. Producto Más Vendido
    top_stmt = (
        select(
            Product.name,
            func.sum(OrderItem.quantity).label("total_sold"),
        )
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.payment_status == "PAID", Order.created_at >= today_start)
        .group_by(Product.id, Product.name)
        .order_by(desc("total_sold"))
        .limit(1)
    )
    res_top = await db.execute(top_stmt)
    top_row = res_top.first()

    top_product_name = top_row[0] if top_row else "Sin ventas aún"
    top_product_units = int(top_row[1]) if top_row else 0

    return {
        "total_revenue_today": float(total_rev),
        "total_orders_today": orders_count,
        "average_ticket": avg_ticket,
        "top_selling_product": {
            "name": top_product_name,
            "units": top_product_units,
        },
    }
