from typing import Optional

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: Optional[str] = None
    meta: Optional[dict] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
