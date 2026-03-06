from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.config import SystemConfig


async def list_configs(db: AsyncSession) -> list[SystemConfig]:
    result = await db.execute(select(SystemConfig).order_by(SystemConfig.key))
    return list(result.scalars().all())


async def get_config_by_key(db: AsyncSession, key: str) -> SystemConfig:
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.key == key)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError("CONFIG_NOT_FOUND", f"Config key '{key}' not found")
    return entry


async def get_config_value(
    db: AsyncSession, key: str, default: Optional[str] = None
) -> Optional[str]:
    result = await db.execute(
        select(SystemConfig).where(SystemConfig.key == key)
    )
    entry = result.scalar_one_or_none()
    return entry.value if entry else default


async def update_config(db: AsyncSession, key: str, value: str) -> SystemConfig:
    entry = await get_config_by_key(db, key)
    entry.value = value
    await db.flush()
    return entry
