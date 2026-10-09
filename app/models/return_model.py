from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String
)
from sqlalchemy.orm import relationship

from app.database import Base


class SalesReturn(Base):
    __tablename__ = "sales_returns"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    so_id = Column(
        Integer,
        ForeignKey("sales_orders.id"),
        nullable=False
    )

    reason = Column(
        String(255),
        nullable=False
    )

    status = Column(
        String(30),
        nullable=False,
        default="Requested"
    )

    refund_amount = Column(
        Float,
        nullable=False,
        default=0
    )

    rejection_reason = Column(
        String(255),
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    created_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    # Sales Order relationship
    sales_order = relationship(
        "SalesOrder",
        back_populates="returns"
    )

    # Return items relationship
    items = relationship(
        "SalesReturnItem",
        back_populates="sales_return",
        cascade="all, delete-orphan"
    )


class SalesReturnItem(Base):
    __tablename__ = "sales_return_items"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    return_id = Column(
        Integer,
        ForeignKey("sales_returns.id"),
        nullable=False
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False
    )

    quantity = Column(
        Float,
        nullable=False
    )

    condition = Column(
        String(20),
        nullable=True
    )

    # Sales return relationship
    sales_return = relationship(
        "SalesReturn",
        back_populates="items"
    )

    # Product relationship
    product = relationship(
        "Product"
    )