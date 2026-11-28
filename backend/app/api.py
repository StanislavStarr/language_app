from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.collections.router import router as collections_router
from app.modules.languages.router import router as languages_router
from app.modules.lexicon.router import router as lexicon_router
from app.modules.users.router import router as users_router
from app.modules.vocabulary.router import router as vocabulary_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(languages_router)
api_router.include_router(lexicon_router)
api_router.include_router(vocabulary_router)
api_router.include_router(collections_router)
