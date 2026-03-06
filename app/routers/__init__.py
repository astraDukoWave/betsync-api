from fastapi import APIRouter
from app.routers import picks, parlays

router = APIRouter()
router.include_router(picks.router, prefix="/picks", tags=["picks"])
router.include_router(parlays.router, prefix="/parlays", tags=["parlays"])
