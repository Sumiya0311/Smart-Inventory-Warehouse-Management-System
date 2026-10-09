from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.user import User
from app.utils.email import queue_email


router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"]
)


# =========================================================
# CHECK LOW STOCK AND NOTIFY INVENTORY MANAGER
# =========================================================

@router.post("/low-stock/check")
def check_low_stock(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Inventory Manager"
        )
    )
):

    low_stock_items = (
        db.query(Inventory, Product)
        .join(
            Product,
            Product.id == Inventory.product_id
        )
        .filter(
            Product.is_active == True,
            Inventory.quantity_on_hand
            - Inventory.quantity_reserved
            <= Product.reorder_level
        )
        .all()
    )

    managers = (
        db.query(User)
        .filter(
            User.role == "Inventory Manager"
        )
        .all()
    )

    notifications_sent = 0

    for manager in managers:

        if not manager.email:
            continue

        for inventory, product in low_stock_items:

            available_quantity = (
                inventory.quantity_on_hand
                - inventory.quantity_reserved
            )

            queue_email(
                background_tasks,
                manager.email,
                f"Low Stock Alert - {product.name}",
                f"""
Low Stock Alert

Product: {product.name}
SKU: {product.sku}

Warehouse ID: {inventory.warehouse_id}

Quantity on Hand: {inventory.quantity_on_hand}
Quantity Reserved: {inventory.quantity_reserved}
Available Quantity: {available_quantity}

Reorder Level: {product.reorder_level}
Recommended Reorder Quantity: {product.reorder_quantity}

Please arrange replenishment.

Regards,
Smart Inventory Management System
"""
            )

            notifications_sent += 1

    return {
        "message": "Low stock check completed",
        "low_stock_items": len(low_stock_items),
        "notifications_queued": notifications_sent
    }