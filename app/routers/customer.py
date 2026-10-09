from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.customer import (
    CustomerCreate,
    CustomerResponse,
    CustomerUpdate,
)

router = APIRouter(
    prefix="/customers",
    tags=["Customers"]
)


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED
)
def create_customer(
    data: CustomerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    existing_code = (
        db.query(Customer)
        .filter(Customer.customer_code == data.customer_code)
        .first()
    )

    if existing_code:
        raise HTTPException(
            status_code=409,
            detail="Customer code already exists"
        )

    existing_email = (
        db.query(Customer)
        .filter(Customer.email == data.email)
        .first()
    )

    if existing_email:
        raise HTTPException(
            status_code=409,
            detail="Customer email already exists"
        )

    customer = Customer(
        customer_code=data.customer_code,
        name=data.name,
        email=data.email,
        phone=data.phone,
        address=data.address,
        credit_limit=data.credit_limit,
        is_active=True,
        created_by=current_user.id
    )

    db.add(customer)
    db.commit()
    db.refresh(customer)

    return customer


@router.get(
    "",
    response_model=list[CustomerResponse]
)
def get_customers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return (
        db.query(Customer)
        .filter(Customer.is_active == True)
        .order_by(Customer.id.desc())
        .all()
    )


@router.get(
    "/{customer_id}",
    response_model=CustomerResponse
)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id)
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found"
        )

    return customer


@router.put(
    "/{customer_id}",
    response_model=CustomerResponse
)
def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id)
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found"
        )

    update_data = data.model_dump(exclude_unset=True)

    if "customer_code" in update_data:
        existing_code = (
            db.query(Customer)
            .filter(
                Customer.customer_code == update_data["customer_code"],
                Customer.id != customer_id
            )
            .first()
        )

        if existing_code:
            raise HTTPException(
                status_code=409,
                detail="Customer code already exists"
            )

    if "email" in update_data:
        existing_email = (
            db.query(Customer)
            .filter(
                Customer.email == update_data["email"],
                Customer.id != customer_id
            )
            .first()
        )

        if existing_email:
            raise HTTPException(
                status_code=409,
                detail="Customer email already exists"
            )

    for key, value in update_data.items():
        setattr(customer, key, value)

    db.commit()
    db.refresh(customer)

    return customer


@router.delete("/{customer_id}")
def deactivate_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role != "Admin":
        raise HTTPException(
            status_code=403,
            detail="Only Admin can deactivate customer"
        )

    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id)
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found"
        )

    customer.is_active = False

    db.commit()

    return {
        "message": "Customer deactivated successfully"
    }