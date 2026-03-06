from pydantic import BaseModel
from typing import Optional, Any, List


class ErrorDetail(BaseModel):
    """Single error detail, mirrors RFC 7807 Problem Details."""
    field: Optional[str] = None
    message: str
    code: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response envelope used across all endpoints."""
    error: str
    message: str
    details: Optional[List[ErrorDetail]] = None
    status_code: int


class ValidationErrorResponse(BaseModel):
    """422 Unprocessable Entity response shape."""
    error: str = "ValidationError"
    message: str = "Input validation failed"
    details: List[ErrorDetail]
    status_code: int = 422


class NotFoundResponse(ErrorResponse):
    error: str = "NotFound"
    status_code: int = 404


class ConflictResponse(ErrorResponse):
    error: str = "Conflict"
    status_code: int = 409
