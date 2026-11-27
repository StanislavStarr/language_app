from fastapi import APIRouter

from app.modules.languages.router import router as languages_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(languages_router)
