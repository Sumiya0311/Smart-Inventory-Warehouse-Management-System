from datetime import datetime, timedelta

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

from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.models.inventory import Inventory
from app.models.stock_movement import StockMovement
from app.models.user import User

from app.schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderReceiveRequest,
    PurchaseOrderResponse,
)

from app.utils.audit import create_audit_log
from app.utils.email import queue_email


router = APIRouter(
    prefix="/purchase-orders",
    tags=["Purchase Orders"]
)


# =========================================================
# GENERATE PO NUMBER
# =========================================================

def generate_po_number(db: Session) -> str:

    last_po = (
        db.query(PurchaseOrder)
        .order_by(PurchaseOrder.id.desc())
        .first()
    )

    if not last_po:
        number = 1
    else:
        number = last_po.id + 1

    return f"PO-{number:04d}"


# =========================================================
# CREATE PURCHASE ORDER
# =========================================================

@router.post(
    "",
    response_model=PurchaseOrderResponse,
    status_code=status.HTTP_201_CREATED
)
def create_purchase_order(
    data: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "Inventory Manager")
    )
):

    supplier = (
        db.query(Supplier)
        .filter(
            Supplier.id == data.supplier_id,
            Supplier.is_active == True
        )
        .first()
    )

    if not supplier:
        raise HTTPException(
            status_code=404,
            detail="Active supplier not found"
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

    total_amount = 0

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

        total_amount += (
            item.quantity_ordered *
            item.unit_cost
        )

    expected_delivery_date = data.expected_delivery_date

    if expected_delivery_date is None:
        expected_delivery_date = (
            datetime.utcnow().date()
            + timedelta(days=supplier.lead_time_days)
        )

    po = PurchaseOrder(
        po_number=generate_po_number(db),
        supplier_id=data.supplier_id,
        warehouse_id=data.warehouse_id,
        expected_delivery_date=expected_delivery_date,
        total_amount=total_amount,
        status="Draft",
        created_by=current_user.id
    )

    db.add(po)
    db.flush()

    # =====================================================
    # AUDIT: CREATE PURCHASE ORDER
    # =====================================================

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="CREATE",
        entity_type="PurchaseOrder",
        entity_id=po.id,
        old_value=None,
        new_value={
            "status": "Draft",
            "po_number": po.po_number,
            "supplier_id": po.supplier_id,
            "warehouse_id": po.warehouse_id,
            "total_amount": po.total_amount
        }
    )

    for item in data.items:

        po_item = PurchaseOrderItem(
            purchase_order_id=po.id,
            product_id=item.product_id,
            quantity_ordered=item.quantity_ordered,
            quantity_received=0,
            unit_cost=item.unit_cost
        )

        db.add(po_item)

    db.commit()
    db.refresh(po)

    return po


# =========================================================
# GET ALL PURCHASE ORDERS
# =========================================================

@router.get(
    "",
    response_model=list[PurchaseOrderResponse]
)
def get_purchase_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    return (
        db.query(PurchaseOrder)
        .order_by(PurchaseOrder.id.desc())
        .all()
    )


# =========================================================
# GET PURCHASE ORDER BY ID
# =========================================================

@router.get(
    "/{po_id}",
    response_model=PurchaseOrderResponse
)
def get_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    po = (
        db.query(PurchaseOrder)
        .filter(
            PurchaseOrder.id == po_id
        )
        .first()
    )

    if not po:
        raise HTTPException(
            status_code=404,
            detail="Purchase order not found"
        )

    return po


# =========================================================
# APPROVE PURCHASE ORDER
# =========================================================

@router.put(
    "/{po_id}/approve",
    response_model=PurchaseOrderResponse
)
def approve_purchase_order(
    po_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Inventory Manager"
        )
    )
):

    po = (
        db.query(PurchaseOrder)
        .filter(
            PurchaseOrder.id == po_id
        )
        .first()
    )

    if not po:
        raise HTTPException(
            status_code=404,
            detail="Purchase order not found"
        )

    if po.status != "Draft":
        raise HTTPException(
            status_code=400,
            detail="Only Draft purchase orders can be approved"
        )

    old_status = po.status

    po.status = "Approved"

    # =====================================================
    # AUDIT: APPROVE PURCHASE ORDER
    # =====================================================

    create_audit_log(
        db=db,
        user_id=current_user.id,
        action="UPDATE",
        entity_type="PurchaseOrder",
        entity_id=po.id,
        old_value={
            "status": old_status
        },
        new_value={
            "status": "Approved"
        }
    )

    db.commit()
    db.refresh(po)

    # =====================================================
    # EMAIL: PURCHASE ORDER APPROVED
    # =====================================================

    supplier = (
        db.query(Supplier)
        .filter(
            Supplier.id == po.supplier_id
        )
        .first()
    )

    if supplier:

        queue_email(
            background_tasks,
            supplier.email,
            f"Purchase Order {po.po_number} Approved",
            f"""
Dear {supplier.name},

Purchase order {po.po_number} has been approved.

Purchase Order Number: {po.po_number}
Total Amount: ₹{po.total_amount:.2f}
Expected Delivery Date: {po.expected_delivery_date}
Status: Approved

Please proceed with the order.

Regards,
Smart Inventory Management System
"""
        )

    return po


# =========================================================
# RECEIVE PURCHASE ORDER
# =========================================================

@router.put(
    "/{po_id}/receive",
    response_model=PurchaseOrderResponse
)
def receive_purchase_order(
    po_id: int,
    data: PurchaseOrderReceiveRequest,
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

        po = (
            db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.id == po_id
            )
            .with_for_update()
            .first()
        )

        if not po:
            raise HTTPException(
                status_code=404,
                detail="Purchase order not found"
            )

        if po.status not in [
            "Approved",
            "Partially Received"
        ]:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Only Approved or Partially Received "
                    "purchase orders can be received"
                )
            )

        warehouse = (
            db.query(Warehouse)
            .filter(
                Warehouse.id == po.warehouse_id
            )
            .first()
        )

        if not warehouse:
            raise HTTPException(
                status_code=404,
                detail="Warehouse not found"
            )

        if not warehouse.is_active:
            raise HTTPException(
                status_code=400,
                detail="Inactive warehouse cannot receive stock"
            )

        if (
            current_user.role == "Warehouse Staff"
            and current_user.warehouse_id != po.warehouse_id
        ):
            raise HTTPException(
                status_code=403,
                detail="You are not assigned to this warehouse"
            )

        received_any = False

        received_items_for_audit = []

        for receive_item in data.items:

            po_item = (
                db.query(PurchaseOrderItem)
                .filter(
                    PurchaseOrderItem.id ==
                    receive_item.item_id,
                    PurchaseOrderItem.purchase_order_id ==
                    po_id
                )
                .with_for_update()
                .first()
            )

            if not po_item:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Purchase order item "
                        f"{receive_item.item_id} not found"
                    )
                )

            remaining_quantity = (
                po_item.quantity_ordered
                - po_item.quantity_received
            )

            if receive_item.quantity_received > remaining_quantity:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Cannot receive "
                        f"{receive_item.quantity_received} "
                        f"units. Remaining quantity is "
                        f"{remaining_quantity}"
                    )
                )

            inventory = (
                db.query(Inventory)
                .filter(
                    Inventory.product_id ==
                    po_item.product_id,
                    Inventory.warehouse_id ==
                    po.warehouse_id
                )
                .with_for_update()
                .first()
            )

            if not inventory:

                inventory = Inventory(
                    product_id=po_item.product_id,
                    warehouse_id=po.warehouse_id,
                    quantity_on_hand=0,
                    quantity_reserved=0,
                    created_by=current_user.id
                )

                db.add(inventory)
                db.flush()

            inventory.quantity_on_hand += (
                receive_item.quantity_received
            )

            po_item.quantity_received += (
                receive_item.quantity_received
            )

            movement = StockMovement(
                product_id=po_item.product_id,
                warehouse_id=po.warehouse_id,
                movement_type="Purchase Receipt",
                quantity=receive_item.quantity_received,
                reference_id=po.id,
                balance_after=inventory.quantity_on_hand,
                performed_by=current_user.id,
                created_by=current_user.id
            )

            db.add(movement)

            received_items_for_audit.append({
                "item_id": receive_item.item_id,
                "product_id": po_item.product_id,
                "quantity_received":
                    receive_item.quantity_received
            })

            received_any = True

        if not received_any:
            raise HTTPException(
                status_code=400,
                detail="No items were received"
            )

        old_status = po.status

        all_received = all(
            item.quantity_received >=
            item.quantity_ordered
            for item in po.items
        )

        if all_received:

            po.status = "Received"
            po.received_at = datetime.utcnow()

        else:

            po.status = "Partially Received"

        # =================================================
        # AUDIT: RECEIVE PURCHASE ORDER
        # =================================================

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="UPDATE",
            entity_type="PurchaseOrder",
            entity_id=po.id,
            old_value={
                "status": old_status
            },
            new_value={
                "status": po.status,
                "received_items":
                    received_items_for_audit
            }
        )

        db.commit()
        db.refresh(po)

        return po

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Failed to receive purchase order"
        )