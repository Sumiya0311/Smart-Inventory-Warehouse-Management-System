from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class SupplierCreate(BaseModel):
    supplier_code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=10)
    gst_number: Optional[str] = Field(None, min_length=15, max_length=15)
    address: str = Field(..., min_length=1, max_length=255)
    lead_time_days: int = Field(..., ge=0)


class SupplierUpdate(BaseModel):
    supplier_code: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, min_length=10, max_length=10)
    gst_number: Optional[str] = Field(None, min_length=15, max_length=15)
    address: Optional[str] = Field(None, min_length=1, max_length=255)
    lead_time_days: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class SupplierResponse(BaseModel):
    id: int
    supplier_code: str
    name: str
    email: EmailStr
    phone: str
    gst_number: Optional[str]
    address: str
    lead_time_days: int
    is_active: bool

    class Config:
        from_attributes = True