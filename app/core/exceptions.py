class AppError(Exception):
    def __init__(self, code: str, message: str, field: str = None, meta: dict = None):
        self.code = code
        self.message = message
        self.field = field
        self.meta = meta or {}
        super().__init__(message)


class NotFoundError(AppError):
    pass


class ConflictError(AppError):
    pass


class BadRequestError(AppError):
    pass


class UnprocessableError(AppError):
    pass
