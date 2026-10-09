from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------
# CREATE RETURN
# ---------------------------------------------------------

class ReturnItemCreate(BaseModel):
    product_id: int
    quantity: float = Field(..., gt=0)


class ReturnCreate(BaseModel):
    reason: str = Field(..., min_length=1)
    items: List[ReturnItemCreate]



class InspectItem(BaseModel):
    product_id: int
    condition: str


class ReturnInspect(BaseModel):
    items: List[InspectItem]




class ReturnReject(BaseModel):
    rejection_reason: str = Field(..., min_length=1)




class ReturnItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: float
    condition: Optional[str] = None

    class Config:
        from_attributes = True


class ReturnResponse(BaseModel):
    id: int
    so_id: int
    reason: str
    status: str
    refund_amount: float
    rejection_reason: Optional[str] = None
    items: List[ReturnItemResponse]

    class Config:
        from_attributes = True