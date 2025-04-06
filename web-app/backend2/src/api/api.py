from fastapi import APIRouter

from .endpoints import process, status

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(process.router, prefix="/process", tags=["Image Processing"])
# api_router.include_router(status.router, prefix="/status", tags=["Job Status"])
