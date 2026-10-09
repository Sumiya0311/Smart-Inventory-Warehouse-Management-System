from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    status
)
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_roles
from app.database import get_db

from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.sales_order import SalesOrder, SalesOrderItem
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.models.warehouse import Warehouse

from app.schemas.sales_order import (
    DispatchRequest,
    SalesOrderCreate,
    SalesOrderResponse,
)

from app.utils.audit import create_audit_log
from app.utils.email import queue_email


router = APIRouter(
    prefix="/sales-orders",
    tags=["Sales Orders"]
)


# =========================================================
# GENERATE SALES ORDER NUMBER
# =========================================================

def generate_so_number(db: Session) -> str:

    last_so = (
        db.query(SalesOrder)
        .order_by(SalesOrder.id.desc())
        .first()
    )

    number = 1 if not last_so else last_so.id + 1

    return f"SO-{number:04d}"


# =========================================================
# CREATE SALES ORDER
# =========================================================

@router.post(
    "",
    response_model=SalesOrderResponse,
    status_code=status.HTTP_201_CREATED
)
def create_sales_order(
    data: SalesOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Inventory Manager",
            "Warehouse Staff"
        )
    )
):

    customer = (
        db.query(Customer)
        .filter(
            Customer.id == data.customer_id,
            Customer.is_active == True
        )
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Active customer not found"
        )

    warehouse = (
        db.query(Warehouse)
        .filter(
            Warehouse.id == data.warehouse_id,
            Warehouse.is_active == True
        )
        .first()
    )

    if not warehouse:
        raise HTTPException(
            status_code=404,
            detail="Active warehouse not found"
        )

    if (
        current_user.role == "Warehouse Staff"
        and current_user.warehouse_id != data.warehouse_id
    ):
        raise HTTPException(
            status_code=403,
            detail="You are not assigned to this warehouse"
        )

    subtotal = 0

    for item in data.items:

        product = (
            db.query(Product)
            .filter(
                Product.id == item.product_id,
                Product.is_active == True
            )
            .first()
        )

        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Active product {item.product_id} not found"
            )

        inventory = (
            db.query(Inventory)
            .filter(
                Inventory.product_id == item.product_id,
                Inventory.warehouse_id == data.warehouse_id
            )
            .first()
        )

        available_quantity = 0

        if inventory:
            available_quantity = (
                inventory.quantity_on_hand
                - inventory.quantity_reserved
            )

        if item.quantity > available_quantity:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Insufficient stock for product {item.product_id}. "
                    f"Available quantity: {available_quantity}"
                )
            )

        subtotal += item.quantity * product.selling_price

    tax_amount = round(subtotal * 0.18, 2)

    grand_total = round(
        subtotal + tax_amount,
        2
    )

    if grand_total > customer.credit_limit:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Order total exceeds customer credit limit. "
                f"Credit limit: {customer.credit_limit}"
            )
        )

    sales_order = SalesOrder(
        so_number=generate_so_number(db),
        customer_id=data.customer_id,
        warehouse_id=data.warehouse_id,
        subtotal=subtotal,
        tax_amount=tax_amount,
        grand_total=grand_total,
        status="Draft",
        created_by=current_user.id
    )

    db.add(sales_order)

    db.flush()

    # =====================================================
    # AUDIT: CREATE SALES ORDER
    # =====================================================

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="CREATE",
        entity_type="SalesOrder",
        entity_id=sales_order.id,
        old_value=None,
        new_value={
            "status": "Draft",
            "so_number": sales_order.so_number,
            "customer_id": sales_order.customer_id,
            "warehouse_id": sales_order.warehouse_id,
            "grand_total": sales_order.grand_total
        }
    )

    for item in data.items:

        product = (
            db.query(Product)
            .filter(
                Product.id == item.product_id
            )
            .first()
        )

        line_total = (
            item.quantity *
            product.selling_price
        )

        sales_order_item = SalesOrderItem(
            sales_order_id=sales_order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=product.selling_price,
            line_total=line_total
        )

        db.add(sales_order_item)

    db.commit()

    db.refresh(sales_order)

    return sales_order


# =========================================================
# GET ALL SALES ORDERS
# =========================================================

@router.get(
    "",
    response_model=list[SalesOrderResponse]
)
def get_sales_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return (
        db.query(SalesOrder)
        .order_by(SalesOrder.id.desc())
        .all()
    )


# =========================================================
# GET SALES ORDER
# =========================================================

@router.get(
    "/{so_id}",
    response_model=SalesOrderResponse
)
def get_sales_order(
    so_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    sales_order = (
        db.query(SalesOrder)
        .filter(
            SalesOrder.id == so_id
        )
        .first()
    )

    if not sales_order:
        raise HTTPException(
            status_code=404,
            detail="Sales order not found"
        )

    return sales_order


# =========================================================
# CONFIRM SALES ORDER
# =========================================================

@router.put(
    "/{so_id}/confirm",
    response_model=SalesOrderResponse
)
def confirm_sales_order(
    so_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Inventory Manager"
        )
    )
):

    sales_order = (
        db.query(SalesOrder)
        .filter(
            SalesOrder.id == so_id
        )
        .first()
    )

    if not sales_order:
        raise HTTPException(
            status_code=404,
            detail="Sales order not found"
        )

    if sales_order.status != "Draft":
        raise HTTPException(
            status_code=400,
            detail="Only Draft sales orders can be confirmed"
        )

    old_status = sales_order.status

    sales_order.status = "Confirmed"

    # =====================================================
    # AUDIT: CONFIRM SALES ORDER
    # =====================================================

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="UPDATE",
        entity_type="SalesOrder",
        entity_id=sales_order.id,
        old_value={
            "status": old_status
        },
        new_value={
            "status": "Confirmed"
        }
    )

    db.commit()

    db.refresh(sales_order)

    # =====================================================
    # EMAIL: SALES ORDER CONFIRMED
    # =====================================================

    customer = (
        db.query(Customer)
        .filter(
            Customer.id == sales_order.customer_id
        )
        .first()
    )

    if customer:

        queue_email(
            background_tasks,
            customer.email,
            f"Sales Order {sales_order.so_number} Confirmed",
            f"""
Dear {customer.name},

Your sales order {sales_order.so_number} has been confirmed successfully.

Order Total: ₹{sales_order.grand_total:.2f}
Status: Confirmed

Thank you for your order.

Regards,
Smart Inventory Management System
"""
        )

    return sales_order


# =========================================================
# RESERVE STOCK
# =========================================================

@router.put(
    "/{so_id}/reserve",
    response_model=SalesOrderResponse
)
def reserve_sales_order(
    so_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Inventory Manager",
            "Warehouse Staff"
        )
    )
):

    try:

        sales_order = (
            db.query(SalesOrder)
            .filter(
                SalesOrder.id == so_id
            )
            .with_for_update()
            .first()
        )

        if not sales_order:
            raise HTTPException(
                status_code=404,
                detail="Sales order not found"
            )

        if sales_order.status != "Confirmed":
            raise HTTPException(
                status_code=400,
                detail="Only Confirmed sales orders can be reserved"
            )

        if (
            current_user.role == "Warehouse Staff"
            and current_user.warehouse_id != sales_order.warehouse_id
        ):
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this warehouse"
            )

        # Check all stock first
        for item in sales_order.items:

            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.product_id == item.product_id,
                    Inventory.warehouse_id == sales_order.warehouse_id
                )
                .with_for_update()
                .first()
            )

            if not inventory:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"No inventory found for "
                        f"product {item.product_id}"
                    )
                )

            available_quantity = (
                inventory.quantity_on_hand
                - inventory.quantity_reserved
            )

            if item.quantity > available_quantity:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Insufficient available stock "
                        f"for product {item.product_id}. "
                        f"Available: {available_quantity}"
                    )
                )

        # Reserve stock
        for item in sales_order.items:

            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.product_id == item.product_id,
                    Inventory.warehouse_id == sales_order.warehouse_id
                )
                .with_for_update()
                .first()
            )

            inventory.quantity_reserved += item.quantity

        old_status = sales_order.status

        sales_order.status = "Reserved"

        # =================================================
        # AUDIT: RESERVE SALES ORDER
        # =================================================

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="UPDATE",
            entity_type="SalesOrder",
            entity_id=sales_order.id,
            old_value={
                "status": old_status
            },
            new_value={
                "status": "Reserved"
            }
        )

        db.commit()

        db.refresh(sales_order)

        return sales_order

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Failed to reserve stock"
        )


# =========================================================
# DISPATCH SALES ORDER
# =========================================================

@router.put(
    "/{so_id}/dispatch",
    response_model=SalesOrderResponse
)
def dispatch_sales_order(
    so_id: int,
    data: DispatchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Inventory Manager",
            "Warehouse Staff"
        )
    )
):

    try:

        sales_order = (
            db.query(SalesOrder)
            .filter(
                SalesOrder.id == so_id
            )
            .with_for_update()
            .first()
        )

        if not sales_order:
            raise HTTPException(
                status_code=404,
                detail="Sales order not found"
            )

        if sales_order.status != "Reserved":
            raise HTTPException(
                status_code=400,
                detail="Only Reserved sales orders can be dispatched"
            )

        if (
            current_user.role == "Warehouse Staff"
            and current_user.warehouse_id != sales_order.warehouse_id
        ):
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this warehouse"
            )

        existing_tracking = (
            db.query(SalesOrder)
            .filter(
                SalesOrder.tracking_number ==
                data.tracking_number,
                SalesOrder.id != so_id
            )
            .first()
        )

        if existing_tracking:
            raise HTTPException(
                status_code=409,
                detail="Tracking number already exists"
            )

        # Check reserved stock
        for item in sales_order.items:

            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.product_id == item.product_id,
                    Inventory.warehouse_id == sales_order.warehouse_id
                )
                .with_for_update()
                .first()
            )

            if not inventory:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"No inventory found for "
                        f"product {item.product_id}"
                    )
                )

            if inventory.quantity_reserved < item.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Insufficient reserved stock "
                        f"for product {item.product_id}"
                    )
                )

        # Deduct stock
        for item in sales_order.items:

            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.product_id == item.product_id,
                    Inventory.warehouse_id == sales_order.warehouse_id
                )
                .with_for_update()
                .first()
            )

            inventory.quantity_on_hand -= item.quantity
            inventory.quantity_reserved -= item.quantity

            movement = StockMovement(
                product_id=item.product_id,
                warehouse_id=sales_order.warehouse_id,
                movement_type="Sales Dispatch",
                quantity=-item.quantity,
                reference_id=sales_order.id,
                balance_after=inventory.quantity_on_hand,
                performed_by=current_user.id,
                created_by=current_user.id
            )

            db.add(movement)

        old_status = sales_order.status

        sales_order.status = "Dispatched"
        sales_order.courier_name = data.courier_name
        sales_order.tracking_number = data.tracking_number
        sales_order.dispatched_at = datetime.utcnow()

        # =================================================
        # AUDIT: DISPATCH SALES ORDER
        # =================================================

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="UPDATE",
            entity_type="SalesOrder",
            entity_id=sales_order.id,
            old_value={
                "status": old_status
            },
            new_value={
                "status": "Dispatched",
                "courier_name": sales_order.courier_name,
                "tracking_number": sales_order.tracking_number
            }
        )

        db.commit()

        db.refresh(sales_order)

        # =================================================
        # EMAIL: SALES ORDER DISPATCHED
        # =================================================

        customer = (
            db.query(Customer)
            .filter(
                Customer.id == sales_order.customer_id
            )
            .first()
        )

        if customer:

            queue_email(
                background_tasks,
                customer.email,
                f"Sales Order {sales_order.so_number} Dispatched",
                f"""
Dear {customer.name},

Your sales order {sales_order.so_number} has been dispatched.

Courier: {sales_order.courier_name}
Tracking Number: {sales_order.tracking_number}

Order Total: ₹{sales_order.grand_total:.2f}
Status: Dispatched

Thank you.

Regards,
Smart Inventory Management System
"""
            )

        return sales_order

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Failed to dispatch sales order"
        )


# =========================================================
# DELIVER SALES ORDER
# =========================================================

@router.put(
    "/{so_id}/deliver",
    response_model=SalesOrderResponse
)
def deliver_sales_order(
    so_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Inventory Manager",
            "Warehouse Staff"
        )
    )
):

    try:

        sales_order = (
            db.query(SalesOrder)
            .filter(
                SalesOrder.id == so_id
            )
            .with_for_update()
            .first()
        )

        if not sales_order:
            raise HTTPException(
                status_code=404,
                detail="Sales order not found"
            )

        if sales_order.status != "Dispatched":
            raise HTTPException(
                status_code=400,
                detail=(
                    "Only Dispatched sales orders "
                    "can be marked as Delivered"
                )
            )

        if (
            current_user.role == "Warehouse Staff"
            and current_user.warehouse_id != sales_order.warehouse_id
        ):
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this warehouse"
            )

        old_status = sales_order.status

        sales_order.status = "Delivered"
        sales_order.delivered_at = datetime.utcnow()

        # =================================================
        # AUDIT: DELIVER SALES ORDER
        # =================================================

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="UPDATE",
            entity_type="SalesOrder",
            entity_id=sales_order.id,
            old_value={
                "status": old_status
            },
            new_value={
                "status": "Delivered",
                "delivered_at": sales_order.delivered_at.isoformat()
            }
        )

        db.commit()

        db.refresh(sales_order)

        return sales_order

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Failed to deliver sales order"
        )