from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.schemas.stock_movement import StockMovementResponse


router = APIRouter(
    prefix="/stock-movements",
    tags=["Stock Movements"]
)


@router.get(
    "",
    response_model=list[StockMovementResponse]
)
def get_stock_movements(
    product_id: int | None = Query(None),
    warehouse_id: int | None = Query(None),
    movement_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(StockMovement)

    if product_id is not None:
        query = query.filter(
            StockMovement.product_id == product_id
        )

    if warehouse_id is not None:
        query = query.filter(
            StockMovement.warehouse_id == warehouse_id
        )

    if movement_type is not None:
        query = query.filter(
            StockMovement.movement_type == movement_type
        )

    # Warehouse Staff can only see movements
    # from their assigned warehouse
    if current_user.role == "Warehouse Staff":
        if current_user.warehouse_id is None:
            raise HTTPException(
                status_code=403,
                detail="Warehouse Staff is not assigned to a warehouse"
            )

        query = query.filter(
            StockMovement.warehouse_id == current_user.warehouse_id
        )

    return (
        query
        .order_by(StockMovement.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get(
    "/{movement_id}",
    response_model=StockMovementResponse
)
def get_stock_movement(
    movement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    movement = (
        db.query(StockMovement)
        .filter(StockMovement.id == movement_id)
        .first()
    )

    if not movement:
        raise HTTPException(
            status_code=404,
            detail="Stock movement not found"
        )

    
    if (
        current_user.role == "Warehouse Staff"
        and current_user.warehouse_id != movement.warehouse_id
    ):
        raise HTTPException(
            status_code=403,
            detail="You are not assigned to this warehouse"
        )

    return movement