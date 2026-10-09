from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class StockMovementResponse(BaseModel):
    id: int
    product_id: int
    warehouse_id: int
    movement_type: str
    quantity: float
    reference_id: Optional[int]
    balance_after: float
    performed_by: int
    created_at: datetime

    class Config:
        from_attributes = True