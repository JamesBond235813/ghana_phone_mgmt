from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.inventory import router as inventory_router
from app.api.shipment import router as shipment_router
from app.api.transfer import router as transfer_router
from app.api.sales import router as sales_router
from app.api.repair import router as repair_router
from app.api.stocktake import router as stocktake_router
from app.api.documents import router as documents_router
from app.api.admin import router as admin_router
from app.core.config import settings


app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(inventory_router, prefix="/api/v1")
app.include_router(shipment_router, prefix="/api/v1")
app.include_router(transfer_router, prefix="/api/v1")
app.include_router(sales_router, prefix="/api/v1")
app.include_router(repair_router, prefix="/api/v1")
app.include_router(stocktake_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
