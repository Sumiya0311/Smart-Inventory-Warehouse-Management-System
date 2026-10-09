from typing import Optional

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    sku: str = Field(min_length=1, max_length=50)
    barcode: Optional[str] = Field(None, max_length=100)
    category_id: int
    unit: str
    cost_price: float = Field(gt=0)
    selling_price: float = Field(gt=0)
    reorder_level: int = Field(ge=0)
    reorder_quantity: int = Field(ge=0)
    preferred_supplier_id: Optional[int] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=150)
    barcode: Optional[str] = Field(None, max_length=100)
    category_id: Optional[int] = None
    unit: Optional[str] = None
    cost_price: Optional[float] = Field(None, gt=0)
    selling_price: Optional[float] = Field(None, gt=0)
    reorder_level: Optional[int] = Field(None, ge=0)
    reorder_quantity: Optional[int] = Field(None, ge=0)
    preferred_supplier_id: Optional[int] = None


class ProductResponse(BaseModel):
    id: int
    name: str
    sku: str
    barcode: Optional[str]
    category_id: int
    unit: str
    cost_price: float
    selling_price: float
    reorder_level: int
    reorder_quantity: int
    preferred_supplier_id: Optional[int]
    is_active: bool

    class Config:
        from_attributes = True