from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SportBase(BaseModel):
    name: str
    slug: str
    is_active: bool = True


class SportCreate(SportBase):
    pass


class SportRead(SportBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
