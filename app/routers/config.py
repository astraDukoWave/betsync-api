from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.schemas.config import ConfigResponse, ConfigUpdate
from app.services import config_service

router = APIRouter(prefix="/config")


@router.get("/", response_model=list[ConfigResponse])
async def list_configs(db: AsyncSession = Depends(get_db)):
    return await config_service.list_configs(db)


@router.patch("/{key}", response_model=ConfigResponse)
async def update_config(
    key: str,
    body: ConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await config_service.update_config(db, key, body.value)
