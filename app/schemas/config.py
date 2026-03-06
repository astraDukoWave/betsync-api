from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SystemConfigBase(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    is_active: bool = True


class SystemConfigCreate(SystemConfigBase):
    pass


class SystemConfigUpdate(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SystemConfigRead(SystemConfigBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AppConfigResponse(BaseModel):
    """Non-sensitive runtime config returned by the /config endpoint."""
    app_name: str
    version: str
    debug: bool
    odds_api_base_url: str
