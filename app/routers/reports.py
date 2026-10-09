from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.stock_movement import StockMovement
from app.models.purchase_order import PurchaseOrder
from app.models.sales_order import SalesOrder, SalesOrderItem
from app.models.return_model import SalesReturn
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse

router = APIRouter(prefix="/reports", tags=["Reports"])


def check_report_access(current_user: User):
    if current_user.role not in ["Admin", "Inventory Manager"]:
        raise HTTPException(
            status_code=403,
            detail="Only Admin and Inventory Manager can access reports",
        )


def date_range_filter(column, start_date: date, end_date: date):
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must not be after end_date",
        )
    return column >= datetime.combine(start_date, datetime.min.time()), (
        column < datetime.combine(
            end_date + timedelta(days=1), datetime.min.time()
        )
    )


# 1. Dashboard
@router.get("/dashboard")
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_report_access(current_user)

    total_products = db.query(func.count(Product.id)).filter(
        Product.is_active.is_(True)
    ).scalar() or 0

    total_stock_value = db.query(
        func.coalesce(
            func.sum(Inventory.quantity_on_hand * Product.cost_price), 0
        )
    ).join(Product, Product.id == Inventory.product_id).scalar() or 0

    low_stock_count = db.query(func.count()).select_from(
        db.query(Inventory.product_id, Inventory.warehouse_id)
        .join(Product, Product.id == Inventory.product_id)
        .filter(
            Inventory.quantity_on_hand - Inventory.quantity_reserved
            <= Product.reorder_level
        )
        .subquery()
    ).scalar() or 0

    pending_purchase_orders = db.query(func.count(PurchaseOrder.id)).filter(
        PurchaseOrder.status.notin_(["Received", "Cancelled", "Rejected"])
    ).scalar() or 0

    pending_sales_orders = db.query(func.count(SalesOrder.id)).filter(
        SalesOrder.status.notin_(["Delivered", "Cancelled", "Rejected"])
    ).scalar() or 0

    today = date.today()
    today_dispatches = db.query(func.count(SalesOrder.id)).filter(
        SalesOrder.dispatched_at >= datetime.combine(today, datetime.min.time()),
        SalesOrder.dispatched_at < datetime.combine(
            today + timedelta(days=1), datetime.min.time()
        ),
    ).scalar() or 0

    return {
        "total_products": total_products,
        "total_stock_value": round(float(total_stock_value), 2),
        "low_stock_count": low_stock_count,
        "pending_purchase_orders": pending_purchase_orders,
        "pending_sales_orders": pending_sales_orders,
        "today_dispatches": today_dispatches,
    }


# 2. Stock valuation by warehouse
@router.get("/stock-valuation")
def stock_valuation(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_report_access(current_user)

    rows = (
        db.query(
            Warehouse.id.label("warehouse_id"),
            Warehouse.name.label("warehouse_name"),
            func.coalesce(
                func.sum(Inventory.quantity_on_hand * Product.cost_price), 0
            ).label("stock_value"),
        )
        .outerjoin(Inventory, Inventory.warehouse_id == Warehouse.id)
        .outerjoin(Product, Product.id == Inventory.product_id)
        .group_by(Warehouse.id, Warehouse.name)
        .order_by(Warehouse.name)
        .all()
    )

    return {
        "count": len(rows),
        "items": [
            {
                "warehouse_id": row.warehouse_id,
                "warehouse_name": row.warehouse_name,
                "stock_value": round(float(row.stock_value), 2),
            }
            for row in rows
        ],
    }


# 3. Low-stock report with reorder suggestion and supplier
@router.get("/low-stock")
def low_stock_report(
    warehouse_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_report_access(current_user)

    query = (
        db.query(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            Product.reorder_level,
            Product.reorder_quantity,
            Product.preferred_supplier_id,
            Supplier.name.label("preferred_supplier"),
            Inventory.warehouse_id,
            Inventory.quantity_on_hand,
            Inventory.quantity_reserved,
        )
        .join(Inventory, Inventory.product_id == Product.id)
        .outerjoin(Supplier, Supplier.id == Product.preferred_supplier_id)
        .filter(
            Inventory.quantity_on_hand - Inventory.quantity_reserved
            <= Product.reorder_level
        )
    )

    if warehouse_id is not None:
        query = query.filter(Inventory.warehouse_id == warehouse_id)

    rows = query.order_by(Product.name).all()

    return {
        "count": len(rows),
        "items": [
            {
                "product_id": row.product_id,
                "product_name": row.product_name,
                "warehouse_id": row.warehouse_id,
                "quantity_on_hand": row.quantity_on_hand,
                "reserved_quantity": row.quantity_reserved,
                "available_quantity": (
                    row.quantity_on_hand - row.quantity_reserved
                ),
                "reorder_level": row.reorder_level,
                "suggested_reorder_quantity": row.reorder_quantity,
                "preferred_supplier_id": row.preferred_supplier_id,
                "preferred_supplier": row.preferred_supplier,
            }
            for row in rows
        ],
    }


# 4. Sales report with revenue and returns for a date range
@router.get("/sales")
def sales_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    warehouse_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_report_access(current_user)

    start_dt, end_dt = date_range_filter(
        SalesOrder.created_at, start_date, end_date
    )

    query = db.query(
        func.count(SalesOrder.id).label("sales_count"),
        func.coalesce(func.sum(SalesOrder.grand_total), 0).label("revenue"),
    ).filter(
        start_dt,
        end_dt,
        SalesOrder.status.in_(["Confirmed", "Dispatched", "Delivered"]),
    )

    if warehouse_id is not None:
        query = query.filter(SalesOrder.warehouse_id == warehouse_id)

    sales = query.one()

    return_query = db.query(
        func.count(SalesReturn.id).label("return_count"),
        func.coalesce(func.sum(SalesReturn.refund_amount), 0).label(
            "total_refunds"
        ),
    ).join(
        SalesOrder, SalesOrder.id == SalesReturn.so_id
    ).filter(
        SalesReturn.created_at >= datetime.combine(
            start_date, datetime.min.time()
        ),
        SalesReturn.created_at < datetime.combine(
            end_date + timedelta(days=1), datetime.min.time()
        ),
        SalesReturn.status == "Refunded",
    )

    if warehouse_id is not None:
        return_query = return_query.filter(
            SalesOrder.warehouse_id == warehouse_id
        )

    returns = return_query.one()

    return {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "warehouse_id": warehouse_id,
        "sales_count": sales.sales_count,
        "revenue": round(float(sales.revenue), 2),
        "return_count": returns.return_count,
        "total_refunds": round(float(returns.total_refunds), 2),
    }


# 5. Top 10 products by quantity sold
@router.get("/top-products")
def top_products(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_report_access(current_user)

    query = (
        db.query(
            Product.id.label("product_id"),
            Product.name.label("product_name"),
            func.coalesce(func.sum(SalesOrderItem.quantity), 0).label(
                "quantity_sold"
            ),
        )
        .join(SalesOrderItem, SalesOrderItem.product_id == Product.id)
        .join(SalesOrder, SalesOrder.id == SalesOrderItem.sales_order_id)
        .filter(SalesOrder.status.in_(["Dispatched", "Delivered"]))
    )

    if start_date and end_date:
        if start_date > end_date:
            raise HTTPException(
                status_code=400,
                detail="start_date must not be after end_date",
            )
        query = query.filter(
            SalesOrder.dispatched_at >= datetime.combine(
                start_date, datetime.min.time()
            ),
            SalesOrder.dispatched_at < datetime.combine(
                end_date + timedelta(days=1), datetime.min.time()
            ),
        )
    elif start_date or end_date:
        raise HTTPException(
            status_code=400,
            detail="Provide both start_date and end_date",
        )

    rows = query.group_by(
        Product.id, Product.name
    ).order_by(
        func.sum(SalesOrderItem.quantity).desc()
    ).limit(10).all()

    return {
        "count": len(rows),
        "items": [
            {
                "product_id": row.product_id,
                "product_name": row.product_name,
                "quantity_sold": float(row.quantity_sold),
            }
            for row in rows
        ],
    }


# 6. Dead stock: no dispatched or delivered sales in the last 90 days
@router.get("/dead-stock")
def dead_stock(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_report_access(current_user)

    cutoff = datetime.utcnow() - timedelta(days=90)

    recent_sales = (
        db.query(SalesOrderItem.product_id)
        .join(SalesOrder, SalesOrder.id == SalesOrderItem.sales_order_id)
        .filter(
            SalesOrder.status.in_(["Dispatched", "Delivered"]),
            SalesOrder.dispatched_at >= cutoff,
        )
        .distinct()
        .subquery()
    )

    rows = (
        db.query(Product)
        .filter(
            Product.is_active.is_(True),
            ~Product.id.in_(db.query(recent_sales.c.product_id)),
        )
        .order_by(Product.name)
        .all()
    )

    return {
        "count": len(rows),
        "items": [
            {
                "product_id": product.id,
                "product_name": product.name,
                "sku": product.sku,
                "reorder_level": product.reorder_level,
            }
            for product in rows
        ],
        "period_days": 90,
    }


# 7. Supplier on-time delivery performance
@router.get("/supplier-performance")
def supplier_performance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_report_access(current_user)

    rows = (
        db.query(
            Supplier.id.label("supplier_id"),
            Supplier.name.label("supplier_name"),
            func.count(PurchaseOrder.id).label("received_orders"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            PurchaseOrder.received_at
                            <= func.coalesce(
                                PurchaseOrder.expected_delivery_date,
                                func.date(PurchaseOrder.received_at),
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("on_time_orders"),
        )
        .outerjoin(PurchaseOrder, PurchaseOrder.supplier_id == Supplier.id)
        .filter(
            (PurchaseOrder.id.is_(None))
            | (PurchaseOrder.received_at.is_not(None))
        )
        .group_by(Supplier.id, Supplier.name)
        .order_by(Supplier.name)
        .all()
    )

    return {
        "count": len(rows),
        "items": [
            {
                "supplier_id": row.supplier_id,
                "supplier_name": row.supplier_name,
                "received_orders": row.received_orders,
                "on_time_orders": row.on_time_orders,
                "on_time_delivery_percentage": (
                    round(row.on_time_orders / row.received_orders * 100, 2)
                    if row.received_orders
                    else 0
                ),
            }
            for row in rows
        ],
    }


# Existing report: inventory summary
@router.get("/inventory-summary")
def inventory_summary(
    warehouse_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_report_access(current_user)

    query = db.query(
        func.count(func.distinct(Inventory.product_id)).label("total_products"),
        func.coalesce(func.sum(Inventory.quantity_on_hand), 0).label(
            "total_quantity"
        ),
        func.coalesce(func.sum(Inventory.quantity_reserved), 0).label(
            "total_reserved"
        ),
    )

    if warehouse_id is not None:
        query = query.filter(Inventory.warehouse_id == warehouse_id)

    result = query.one()

    return {
        "warehouse_id": warehouse_id,
        "total_products": result.total_products,
        "total_quantity": result.total_quantity,
        "total_reserved": result.total_reserved,
        "available_quantity": result.total_quantity - result.total_reserved,
    }


# Existing report: purchase report
@router.get("/purchases")
def purchase_report(
    warehouse_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_report_access(current_user)

    query = db.query(
        func.count(PurchaseOrder.id).label("total_orders"),
        func.coalesce(func.sum(PurchaseOrder.total_amount), 0).label(
            "total_amount"
        ),
    )

    if warehouse_id is not None:
        query = query.filter(PurchaseOrder.warehouse_id == warehouse_id)

    result = query.one()

    return {
        "warehouse_id": warehouse_id,
        "total_purchase_orders": result.total_orders,
        "total_purchase_amount": float(result.total_amount),
    }


# Existing report: stock movement report
@router.get("/stock-movements")
def stock_movement_report(
    product_id: Optional[int] = Query(None, ge=1),
    warehouse_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    check_report_access(current_user)

    query = db.query(StockMovement)

    if product_id is not None:
        query = query.filter(StockMovement.product_id == product_id)

    if warehouse_id is not None:
        query = query.filter(StockMovement.warehouse_id == warehouse_id)

    movements = query.order_by(
        StockMovement.id.desc()
    ).limit(100).all()

    return {
        "count": len(movements),
        "items": [
            {
                "id": movement.id,
                "product_id": movement.product_id,
                "warehouse_id": movement.warehouse_id,
                "movement_type": movement.movement_type,
                "quantity": movement.quantity,
                "reference_id": movement.reference_id,
                "balance_after": movement.balance_after,
                "performed_by": movement.performed_by,
            }
            for movement in movements
        ],
    }