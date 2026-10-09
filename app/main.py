from fastapi import FastAPI

from app.routers.auth import router as auth_router
from app.routers.warehouse import router as warehouse_router
from app.routers.category import router as category_router
from app.routers.product import router as product_router
from app.routers.supplier import router as supplier_router
from app.routers.purchase_order import router as purchase_order_router
from app.routers.customer import router as customer_router
from app.routers.sales_order import router as sales_order_router
from app.routers.stock_movement import router as stock_movement_router
from app.routers.returns import router as returns_router
from app.routers.audit_logs import router as audit_logs_router
from app.routers.inventory import router as inventory_router
from app.routers.reports import router as reports_router
app = FastAPI(
    title="Smart Inventory & Warehouse Management System",
    version="1.0.0"
)

app.include_router(auth_router)
app.include_router(warehouse_router)
app.include_router(category_router)
app.include_router(product_router)
app.include_router(supplier_router)
app.include_router(purchase_order_router)
app.include_router(customer_router)
app.include_router(sales_order_router)
app.include_router(stock_movement_router)
app.include_router(returns_router)
app.include_router(audit_logs_router)
app.include_router(inventory_router)
app.include_router(reports_router)

@app.get("/")
def root():
    return {
        "message": "Smart Inventory & Warehouse Management API is running"
    }