from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerBase(BaseModel):
    customer_code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=150)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=15)
    address: str = Field(..., min_length=1, max_length=255)
    credit_limit: float = Field(default=100000, ge=0)


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    customer_code: Optional[str] = Field(
        default=None, min_length=1, max_length=50
    )
    name: Optional[str] = Field(
        default=None, min_length=1, max_length=150
    )
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(
        default=None, min_length=10, max_length=15
    )
    address: Optional[str] = Field(
        default=None, min_length=1, max_length=255
    )
    credit_limit: Optional[float] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class CustomerResponse(CustomerBase):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)