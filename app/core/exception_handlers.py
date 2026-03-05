from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.core.exceptions import AppError, NotFoundError, ConflictError, BadRequestError


def register_exception_handlers(app: FastAPI):
    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"error": {"code": exc.code, "message": exc.message, "field": exc.field, "meta": exc.meta}})

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"error": {"code": exc.code, "message": exc.message, "field": exc.field, "meta": exc.meta}})

    @app.exception_handler(BadRequestError)
    async def bad_request_handler(request: Request, exc: BadRequestError):
        return JSONResponse(status_code=400, content={"error": {"code": exc.code, "message": exc.message, "field": exc.field, "meta": exc.meta}})

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        first = errors[0] if errors else {}
        return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": str(first.get("msg", "Validation error")), "field": ".".join(str(l) for l in first.get("loc", [])), "meta": {"errors": errors}}})

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred", "field": None, "meta": {}}})
