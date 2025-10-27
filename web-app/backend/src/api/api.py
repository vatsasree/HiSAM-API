from fastapi import APIRouter

from .endpoints.polylines import process, status

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(process.router, prefix="/detections/process", tags=["Image Processing"])
api_router.include_router(status.router, prefix="/detections/status", tags=["Job Status"])
