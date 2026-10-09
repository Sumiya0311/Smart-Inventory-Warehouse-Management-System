from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class PurchaseOrderItemCreate(BaseModel):
    product_id: int
    quantity_ordered: float = Field(gt=0)
    unit_cost: float = Field(gt=0)


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    warehouse_id: int
    expected_delivery_date: Optional[date] = None
    items: List[PurchaseOrderItemCreate] = Field(min_length=1)


class PurchaseOrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity_ordered: float
    quantity_received: float
    unit_cost: float

    class Config:
        from_attributes = True


class PurchaseOrderResponse(BaseModel):
    id: int
    po_number: str
    supplier_id: int
    warehouse_id: int
    expected_delivery_date: Optional[date]
    received_at: Optional[datetime]
    total_amount: float
    status: str
    items: List[PurchaseOrderItemResponse]

    class Config:
        from_attributes = True


class PurchaseOrderReceiveItem(BaseModel):
    item_id: int
    quantity_received: float = Field(gt=0)


class PurchaseOrderReceiveRequest(BaseModel):
    items: List[PurchaseOrderReceiveItem] = Field(min_length=1)