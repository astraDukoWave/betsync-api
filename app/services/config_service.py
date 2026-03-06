"""ConfigService (Paso 11): Dynamic configuration management via DB."""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.config import SystemConfig
from app.schemas.config import SystemConfigCreate, SystemConfigUpdate


class ConfigService:
    """CRUD service for dynamic system configuration stored in the DB."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_key(self, key: str) -> Optional[SystemConfig]:
        """Retrieve a config entry by its key."""
        result = await self.db.execute(
            select(SystemConfig).where(SystemConfig.key == key)
        )
        return result.scalar_one_or_none()

    async def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Return the raw string value for a key, or default if not found."""
        entry = await self.get_by_key(key)
        if entry is None or not entry.is_active:
            return default
        return entry.value

    async def set(self, payload: SystemConfigCreate) -> SystemConfig:
        """Create or update a config entry."""
        existing = await self.get_by_key(payload.key)
        if existing:
            existing.value = payload.value
            if payload.description is not None:
                existing.description = payload.description
            existing.is_active = payload.is_active
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        entry = SystemConfig(**payload.model_dump())
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def update(self, key: str, payload: SystemConfigUpdate) -> Optional[SystemConfig]:
        """Partially update an existing config entry."""
        entry = await self.get_by_key(key)
        if entry is None:
            return None
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(entry, field, value)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def delete(self, key: str) -> bool:
        """Delete a config entry by key. Returns True if deleted."""
        entry = await self.get_by_key(key)
        if entry is None:
            return False
        await self.db.delete(entry)
        await self.db.commit()
        return True
