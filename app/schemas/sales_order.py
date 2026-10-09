from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class SalesOrderItemCreate(BaseModel):
    product_id: int
    quantity: float = Field(gt=0)


class SalesOrderCreate(BaseModel):
    customer_id: int
    warehouse_id: int
    items: List[SalesOrderItemCreate] = Field(min_length=1)


class SalesOrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: float
    unit_price: float
    line_total: float

    class Config:
        from_attributes = True


class SalesOrderResponse(BaseModel):
    id: int
    so_number: str
    customer_id: int
    warehouse_id: int
    subtotal: float
    tax_amount: float
    grand_total: float
    status: str
    courier_name: Optional[str]
    tracking_number: Optional[str]
    dispatched_at: Optional[datetime]
    delivered_at: Optional[datetime]
    items: List[SalesOrderItemResponse]

    class Config:
        from_attributes = True


class DispatchRequest(BaseModel):
    courier_name: str = Field(min_length=1, max_length=100)
    tracking_number: str = Field(min_length=1, max_length=100)