from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models.user import User
from app.models.warehouse import Warehouse
from app.models.inventory import Inventory


router = APIRouter(
    prefix="/warehouses",
    tags=["Warehouses"]
)



# Schemas

class WarehouseCreate(BaseModel):
    warehouse_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=255)
    capacity: float = Field(gt=0)
    manager_id: Optional[int] = None
    is_active: bool = True


class WarehouseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    address: Optional[str] = Field(None, min_length=1, max_length=255)
    capacity: Optional[float] = Field(None, gt=0)
    manager_id: Optional[int] = None


class WarehouseResponse(BaseModel):
    id: int
    warehouse_code: str
    name: str
    city: str
    address: str
    capacity: float
    manager_id: Optional[int]
    is_active: bool

    class Config:
        from_attributes = True





@router.post(
    "",
    response_model=WarehouseResponse,
    status_code=status.HTTP_201_CREATED
)
def create_warehouse(
    data: WarehouseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    existing = db.query(Warehouse).filter(
        Warehouse.warehouse_code == data.warehouse_code
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Warehouse code already exists"
        )

    if data.manager_id:
        manager = db.query(User).filter(
            User.id == data.manager_id
        ).first()

        if not manager:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Warehouse manager not found"
            )

        if manager.role not in ["Admin", "Inventory Manager"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected user cannot manage a warehouse"
            )

    warehouse = Warehouse(
        warehouse_code=data.warehouse_code,
        name=data.name,
        city=data.city,
        address=data.address,
        capacity=data.capacity,
        manager_id=data.manager_id,
        is_active=data.is_active,
        created_by=current_user.id
    )

    db.add(warehouse)
    db.commit()
    db.refresh(warehouse)

    return warehouse



# Get All Warehouses


@router.get(
    "",
    response_model=list[WarehouseResponse]
)
def get_warehouses(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Inventory Manager",
            "Warehouse Staff"
        )
    )
):
    return db.query(Warehouse).all()



# Get Warehouse By ID


@router.get(
    "/{warehouse_id}",
    response_model=WarehouseResponse
)
def get_warehouse(
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Inventory Manager",
            "Warehouse Staff"
        )
    )
):
    warehouse = db.query(Warehouse).filter(
        Warehouse.id == warehouse_id
    ).first()

    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found"
        )

    return warehouse



# Update Warehouse


@router.put(
    "/{warehouse_id}",
    response_model=WarehouseResponse
)
def update_warehouse(
    warehouse_id: int,
    data: WarehouseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    warehouse = db.query(Warehouse).filter(
        Warehouse.id == warehouse_id
    ).first()

    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found"
        )

    
    if data.capacity is not None:
        total_stock = db.query(Inventory).filter(
            Inventory.warehouse_id == warehouse_id
        ).with_entities(
            Inventory.quantity_on_hand
        ).all()

        current_stock = sum(
            item.quantity_on_hand for item in total_stock
        )

        if data.capacity < current_stock:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Capacity cannot be less than current stock"
            )

        warehouse.capacity = data.capacity

    if data.name is not None:
        warehouse.name = data.name

    if data.city is not None:
        warehouse.city = data.city

    if data.address is not None:
        warehouse.address = data.address

    if data.manager_id is not None:
        manager = db.query(User).filter(
            User.id == data.manager_id
        ).first()

        if not manager:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Warehouse manager not found"
            )

        if manager.role not in ["Admin", "Inventory Manager"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected user cannot manage a warehouse"
            )

        warehouse.manager_id = data.manager_id

    db.commit()
    db.refresh(warehouse)

    return warehouse



# Delete / Deactivate Warehouse


@router.delete("/{warehouse_id}")
def delete_warehouse(
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("Admin"))
):
    warehouse = db.query(Warehouse).filter(
        Warehouse.id == warehouse_id
    ).first()

    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found"
        )

    stock = db.query(Inventory).filter(
        Inventory.warehouse_id == warehouse_id,
        Inventory.quantity_on_hand > 0
    ).first()

    if stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Warehouse with stock cannot be deleted or deactivated"
        )

    warehouse.is_active = False

    db.commit()

    return {
        "message": "Warehouse deactivated successfully"
    }



# Get Warehouse Inventory

@router.get("/{warehouse_id}/inventory")
def get_warehouse_inventory(
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Inventory Manager",
            "Warehouse Staff"
        )
    )
):
    warehouse = db.query(Warehouse).filter(
        Warehouse.id == warehouse_id
    ).first()

    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found"
        )

    inventory = db.query(Inventory).filter(
        Inventory.warehouse_id == warehouse_id
    ).all()

    return inventory