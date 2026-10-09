from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models.category import Category
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.inventory import Inventory
from app.models.user import User
from app.schemas.product import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)


router = APIRouter(
    prefix="/products",
    tags=["Products"]
)


# Create Product
@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED
)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "Inventory Manager")
    )
):
    if data.selling_price < data.cost_price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selling price cannot be less than cost price"
        )

    existing_sku = db.query(Product).filter(
        Product.sku == data.sku
    ).first()

    if existing_sku:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SKU already exists"
        )

    if data.barcode:
        existing_barcode = db.query(Product).filter(
            Product.barcode == data.barcode
        ).first()

        if existing_barcode:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Barcode already exists"
            )

    category = db.query(Category).filter(
        Category.id == data.category_id,
        Category.is_active == True
    ).first()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active category not found"
        )

    if data.preferred_supplier_id:
        supplier = db.query(Supplier).filter(
            Supplier.id == data.preferred_supplier_id,
            Supplier.is_active == True
        ).first()

        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active supplier not found"
            )

    product = Product(
        name=data.name,
        sku=data.sku,
        barcode=data.barcode,
        category_id=data.category_id,
        unit=data.unit,
        cost_price=data.cost_price,
        selling_price=data.selling_price,
        reorder_level=data.reorder_level,
        reorder_quantity=data.reorder_quantity,
        preferred_supplier_id=data.preferred_supplier_id,
        is_active=True,
        created_by=current_user.id
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    return product


# Get All Products
@router.get(
    "",
    response_model=list[ProductResponse]
)
def get_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Inventory Manager",
            "Warehouse Staff"
        )
    )
):
    return db.query(Product).filter(
        Product.is_active == True
    ).all()


# Get Product By ID
@router.get(
    "/{product_id}",
    response_model=ProductResponse
)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(
            "Admin",
            "Inventory Manager",
            "Warehouse Staff"
        )
    )
):
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    return product


# Update Product
@router.put(
    "/{product_id}",
    response_model=ProductResponse
)
def update_product(
    product_id: int,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "Inventory Manager")
    )
):
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    new_cost = (
        data.cost_price
        if data.cost_price is not None
        else product.cost_price
    )

    new_selling = (
        data.selling_price
        if data.selling_price is not None
        else product.selling_price
    )

    if new_selling < new_cost:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selling price cannot be less than cost price"
        )

    if data.barcode:
        existing_barcode = db.query(Product).filter(
            Product.barcode == data.barcode,
            Product.id != product_id
        ).first()

        if existing_barcode:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Barcode already exists"
            )

    if data.category_id is not None:
        category = db.query(Category).filter(
            Category.id == data.category_id,
            Category.is_active == True
        ).first()

        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active category not found"
            )

    for field, value in data.model_dump(
        exclude_unset=True
    ).items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    return product


# Soft Delete Product
@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles("Admin", "Inventory Manager")
    )
):
    product = db.query(Product).filter(
        Product.id == product_id
    ).first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    stock = db.query(Inventory).filter(
        Inventory.product_id == product_id,
        Inventory.quantity_on_hand > 0
    ).first()

    if stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate product with available stock"
        )

    product.is_active = False

    db.commit()

    return {
        "message": "Product deactivated successfully"
    }