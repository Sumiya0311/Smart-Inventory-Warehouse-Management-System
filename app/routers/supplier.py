from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.supplier import Supplier
from app.schemas.supplier import SupplierCreate, SupplierResponse, SupplierUpdate
from app.auth.dependencies import get_current_user

router = APIRouter(
    prefix="/suppliers",
    tags=["Suppliers"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/", response_model=SupplierResponse, status_code=201)
def create_supplier(
    supplier: SupplierCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in ["Admin", "Inventory Manager"]:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to create supplier"
        )

    existing_code = db.query(Supplier).filter(
        Supplier.supplier_code == supplier.supplier_code
    ).first()

    if existing_code:
        raise HTTPException(
            status_code=409,
            detail="Supplier code already exists"
        )

    existing_email = db.query(Supplier).filter(
        Supplier.email == supplier.email
    ).first()

    if existing_email:
        raise HTTPException(
            status_code=409,
            detail="Supplier email already exists"
        )

    new_supplier = Supplier(
        supplier_code=supplier.supplier_code,
        name=supplier.name,
        email=supplier.email,
        phone=supplier.phone,
        gst_number=supplier.gst_number,
        address=supplier.address,
        lead_time_days=supplier.lead_time_days,
        is_active=True,
        created_by=current_user.id
    )

    db.add(new_supplier)
    db.commit()
    db.refresh(new_supplier)

    return new_supplier


@router.get("/", response_model=list[SupplierResponse])
def get_suppliers(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return db.query(Supplier).offset(skip).limit(limit).all()


@router.get("/{supplier_id}", response_model=SupplierResponse)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    supplier = db.query(Supplier).filter(
        Supplier.id == supplier_id
    ).first()

    if not supplier:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found"
        )

    return supplier


@router.put("/{supplier_id}", response_model=SupplierResponse)
def update_supplier(
    supplier_id: int,
    supplier_data: SupplierUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in ["Admin", "Inventory Manager"]:
        raise HTTPException(
            status_code=403,
            detail="Not authorized to update supplier"
        )

    supplier = db.query(Supplier).filter(
        Supplier.id == supplier_id
    ).first()

    if not supplier:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found"
        )

    update_data = supplier_data.model_dump(exclude_unset=True)

    if "email" in update_data:
        existing_email = db.query(Supplier).filter(
            Supplier.email == update_data["email"],
            Supplier.id != supplier_id
        ).first()

        if existing_email:
            raise HTTPException(
                status_code=409,
                detail="Supplier email already exists"
            )

    for key, value in update_data.items():
        setattr(supplier, key, value)

    db.commit()
    db.refresh(supplier)

    return supplier


@router.delete("/{supplier_id}")
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role != "Admin":
        raise HTTPException(
            status_code=403,
            detail="Only Admin can deactivate supplier"
        )

    supplier = db.query(Supplier).filter(
        Supplier.id == supplier_id
    ).first()

    if not supplier:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found"
        )

    supplier.is_active = False

    db.commit()

    return {
        "message": "Supplier deactivated successfully"
    }