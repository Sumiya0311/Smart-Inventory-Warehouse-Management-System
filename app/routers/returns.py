from datetime import datetime, timedelta
from typing import List

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import get_current_user

from app.models.return_model import SalesReturn, SalesReturnItem
from app.models.sales_order import SalesOrder, SalesOrderItem
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.stock_movement import StockMovement

from app.schemas.return_schema import (
    ReturnCreate,
    ReturnInspect,
    ReturnReject,
    ReturnResponse,
)

from app.utils.audit import create_audit_log
from app.utils.email import queue_email


router = APIRouter(tags=["Returns"])


# ============================================================
# 1. CREATE RETURN
# POST /sales-orders/{so_id}/returns
# ============================================================

@router.post(
    "/sales-orders/{so_id}/returns",
    response_model=ReturnResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_return(
    so_id: int,
    data: ReturnCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role != "Inventory Manager":
        raise HTTPException(
            status_code=403,
            detail="Only Inventory Manager can create return requests",
        )

    order = (
        db.query(SalesOrder)
        .filter(SalesOrder.id == so_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Sales order not found",
        )

    if order.status != "Delivered":
        raise HTTPException(
            status_code=400,
            detail="Returns are allowed only for Delivered orders",
        )

    if not order.delivered_at:
        raise HTTPException(
            status_code=400,
            detail="Delivery date is not available",
        )

    # Handle both timezone-aware and timezone-naive timestamps.
    delivered_at = order.delivered_at
    now = datetime.now(delivered_at.tzinfo) if delivered_at.tzinfo else datetime.utcnow()

    if now > delivered_at + timedelta(days=7):
        raise HTTPException(
            status_code=400,
            detail="Return period of 7 days has expired",
        )

    if not data.items:
        raise HTTPException(
            status_code=422,
            detail="At least one return item is required",
        )

    product_ids = [item.product_id for item in data.items]

    if len(product_ids) != len(set(product_ids)):
        raise HTTPException(
            status_code=422,
            detail="Duplicate product IDs are not allowed",
        )

    # Query order items directly instead of relying on order.items.
    db_order_items = (
        db.query(SalesOrderItem)
        .filter(SalesOrderItem.sales_order_id == so_id)
        .all()
    )

    # Aggregate quantities in case a product appears on multiple lines.
    ordered_quantities = {}
    for order_item in db_order_items:
        ordered_quantities[order_item.product_id] = (
            ordered_quantities.get(order_item.product_id, 0)
            + order_item.quantity
        )

    for requested_item in data.items:
        product_id = requested_item.product_id

        if product_id not in ordered_quantities:
            raise HTTPException(
                status_code=400,
                detail=f"Product {product_id} was not part of this sales order",
            )

        previous_returns = (
            db.query(SalesReturnItem)
            .join(
                SalesReturn,
                SalesReturn.id == SalesReturnItem.return_id,
            )
            .filter(
                SalesReturn.so_id == so_id,
                SalesReturnItem.product_id == product_id,
                SalesReturn.status != "Rejected",
            )
            .all()
        )

        already_returned = sum(
            item.quantity for item in previous_returns
        )

        remaining_quantity = (
            ordered_quantities[product_id] - already_returned
        )
        print("DEBUG:", product_id, ordered_quantities, already_returned)

        if requested_item.quantity > remaining_quantity:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Return quantity for product {product_id} "
                    f"cannot exceed {remaining_quantity}"
                ),
            )

    try:
        sales_return = SalesReturn(
            so_id=so_id,
            reason=data.reason,
            status="Requested",
            refund_amount=0,
            created_by=current_user.id,
        )

        db.add(sales_return)
        db.flush()

        for requested_item in data.items:
            db.add(
                SalesReturnItem(
                    return_id=sales_return.id,
                    product_id=requested_item.product_id,
                    quantity=requested_item.quantity,
                    condition=None,
                )
            )

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="CREATE",
            entity_type="SalesReturn",
            entity_id=sales_return.id,
            old_value=None,
            new_value={
                "so_id": so_id,
                "status": "Requested",
                "reason": data.reason,
                "items": [
                    {
                        "product_id": item.product_id,
                        "quantity": item.quantity,
                    }
                    for item in data.items
                ],
            },
        )

        db.commit()
        db.refresh(sales_return)
        return sales_return

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create return request",
        )


# ============================================================
# 2. GET RETURNS
# GET /returns
# ============================================================

@router.get(
    "/returns",
    response_model=List[ReturnResponse],
)
def get_returns(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if skip < 0:
        raise HTTPException(
            status_code=422,
            detail="skip cannot be negative",
        )

    if limit <= 0 or limit > 100:
        raise HTTPException(
            status_code=422,
            detail="limit must be between 1 and 100",
        )

    if current_user.role not in [
        "Admin",
        "Inventory Manager",
        "Warehouse Staff",
    ]:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to view returns",
        )

    return (
        db.query(SalesReturn)
        .order_by(SalesReturn.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


# ============================================================
# 3. INSPECT RETURN
# PUT /returns/{return_id}/inspect
# ============================================================

@router.put(
    "/returns/{return_id}/inspect",
    response_model=ReturnResponse,
)
def inspect_return(
    return_id: int,
    data: ReturnInspect,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role != "Warehouse Staff":
        raise HTTPException(
            status_code=403,
            detail="Only Warehouse Staff can inspect returns",
        )

    sales_return = (
        db.query(SalesReturn)
        .filter(SalesReturn.id == return_id)
        .first()
    )

    if not sales_return:
        raise HTTPException(
            status_code=404,
            detail="Return not found",
        )

    if sales_return.status != "Requested":
        raise HTTPException(
            status_code=400,
            detail="Only Requested returns can be inspected",
        )

    order = (
        db.query(SalesOrder)
        .filter(SalesOrder.id == sales_return.so_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Sales order not found",
        )

    if current_user.warehouse_id != order.warehouse_id:
        raise HTTPException(
            status_code=403,
            detail="You are not assigned to this warehouse",
        )

    if not data.items:
        raise HTTPException(
            status_code=422,
            detail="Inspection items are required",
        )

    return_items = {
        item.product_id: item
        for item in sales_return.items
    }

    inspected_ids = [item.product_id for item in data.items]

    if len(inspected_ids) != len(set(inspected_ids)):
        raise HTTPException(
            status_code=422,
            detail="Duplicate product IDs are not allowed",
        )

    if set(inspected_ids) != set(return_items.keys()):
        raise HTTPException(
            status_code=400,
            detail="All return items must be inspected",
        )

    for inspected_item in data.items:
        if inspected_item.condition not in ["Good", "Damaged"]:
            raise HTTPException(
                status_code=422,
                detail="Condition must be Good or Damaged",
            )

    try:
        old_status = sales_return.status

        for inspected_item in data.items:
            return_items[inspected_item.product_id].condition = (
                inspected_item.condition
            )

        sales_return.status = "Inspected"

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="UPDATE",
            entity_type="SalesReturn",
            entity_id=sales_return.id,
            old_value={"status": old_status},
            new_value={
                "status": "Inspected",
                "items": [
                    {
                        "product_id": item.product_id,
                        "condition": item.condition,
                    }
                    for item in data.items
                ],
            },
        )

        db.commit()
        db.refresh(sales_return)
        return sales_return

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to inspect return",
        )


# ============================================================
# 4. APPROVE RETURN AND QUEUE CUSTOMER EMAIL
# PUT /returns/{return_id}/approve
# ============================================================

@router.put(
    "/returns/{return_id}/approve",
    response_model=ReturnResponse,
)
def approve_return(
    return_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role not in ["Admin", "Inventory Manager"]:
        raise HTTPException(
            status_code=403,
            detail="Only Admin or Inventory Manager can approve returns",
        )

    try:
        sales_return = (
            db.query(SalesReturn)
            .filter(SalesReturn.id == return_id)
            .with_for_update()
            .first()
        )

        if not sales_return:
            raise HTTPException(
                status_code=404,
                detail="Return not found",
            )

        if sales_return.status != "Inspected":
            raise HTTPException(
                status_code=400,
                detail="Only Inspected returns can be approved",
            )

        order = (
            db.query(SalesOrder)
            .filter(SalesOrder.id == sales_return.so_id)
            .first()
        )

        if not order:
            raise HTTPException(
                status_code=404,
                detail="Sales order not found",
            )

        customer = (
            db.query(Customer)
            .filter(Customer.id == order.customer_id)
            .first()
        )

        if not customer:
            raise HTTPException(
                status_code=404,
                detail="Customer not found",
            )

        order_items = (
            db.query(SalesOrderItem)
            .filter(SalesOrderItem.sales_order_id == order.id)
            .all()
        )

        unit_prices = {}
        for item in order_items:
            # Normally there is one order line per product.
            unit_prices.setdefault(item.product_id, item.unit_price)

        total_refund = 0.0

        for return_item in sales_return.items:
            if return_item.condition not in ["Good", "Damaged"]:
                raise HTTPException(
                    status_code=400,
                    detail="Every return item must be inspected before approval",
                )

            unit_price = unit_prices.get(return_item.product_id)

            if unit_price is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Original order item not found for product "
                        f"{return_item.product_id}"
                    ),
                )

            # Uses the existing 18% tax calculation.
            total_refund += (
                unit_price * return_item.quantity * 1.18
            )

            if return_item.condition == "Good":
                inventory = (
                    db.query(Inventory)
                    .filter(
                        Inventory.product_id == return_item.product_id,
                        Inventory.warehouse_id == order.warehouse_id,
                    )
                    .with_for_update()
                    .first()
                )

                if not inventory:
                    raise HTTPException(
                        status_code=404,
                        detail=(
                            "Inventory not found for product "
                            f"{return_item.product_id}"
                        ),
                    )

                inventory.quantity_on_hand += return_item.quantity

                db.add(
                    StockMovement(
                        product_id=return_item.product_id,
                        warehouse_id=order.warehouse_id,
                        movement_type="Customer Return",
                        quantity=return_item.quantity,
                        reference_id=sales_return.id,
                        balance_after=inventory.quantity_on_hand,
                        performed_by=current_user.id,
                    )
                )

            # Damaged items are not added to sellable inventory.

        old_status = sales_return.status
        old_refund_amount = sales_return.refund_amount

        sales_return.refund_amount = round(total_refund, 2)
        sales_return.status = "Refunded"

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="APPROVE",
            entity_type="SalesReturn",
            entity_id=sales_return.id,
            old_value={
                "status": old_status,
                "refund_amount": old_refund_amount,
            },
            new_value={
                "status": "Refunded",
                "refund_amount": sales_return.refund_amount,
            },
        )

        db.commit()
        db.refresh(sales_return)

        queue_email(
            background_tasks=background_tasks,
            recipient=customer.email,
            subject=f"Return Approved - {order.so_number}",
            body=f"""
Dear {customer.name},

Your return request has been approved.

Sales Order: {order.so_number}
Return ID: {sales_return.id}
Return Status: {sales_return.status}
Refund Amount: {sales_return.refund_amount:.2f}

This notification confirms that the return has been approved
and recorded in the Smart Inventory & Warehouse Management System.

Regards,
Smart Inventory Management System
""",
        )

        return sales_return

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to approve return",
        )


# ============================================================
# 5. REJECT RETURN
# PUT /returns/{return_id}/reject
# ============================================================

@router.put(
    "/returns/{return_id}/reject",
    response_model=ReturnResponse,
)
def reject_return(
    return_id: int,
    data: ReturnReject,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role not in ["Admin", "Inventory Manager"]:
        raise HTTPException(
            status_code=403,
            detail="Only Admin or Inventory Manager can reject returns",
        )

    sales_return = (
        db.query(SalesReturn)
        .filter(SalesReturn.id == return_id)
        .first()
    )

    if not sales_return:
        raise HTTPException(
            status_code=404,
            detail="Return not found",
        )

    if sales_return.status != "Inspected":
        raise HTTPException(
            status_code=400,
            detail="Only Inspected returns can be rejected",
        )

    rejection_reason = data.rejection_reason.strip()

    if not rejection_reason:
        raise HTTPException(
            status_code=422,
            detail="Rejection reason is required",
        )

    try:
        old_status = sales_return.status

        sales_return.status = "Rejected"
        sales_return.rejection_reason = rejection_reason
        sales_return.refund_amount = 0

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="REJECT",
            entity_type="SalesReturn",
            entity_id=sales_return.id,
            old_value={"status": old_status},
            new_value={
                "status": "Rejected",
                "rejection_reason": rejection_reason,
                "refund_amount": 0,
            },
        )

        db.commit()
        db.refresh(sales_return)
        return sales_return

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to reject return",
        )