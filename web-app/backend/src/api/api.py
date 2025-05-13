from fastapi import APIRouter

from .endpoints.polylines import process, status

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(process.router, prefix="/polylines/process", tags=["Image Processing"])
api_router.include_router(status.router, prefix="/polylines/status", tags=["Job Status"])
