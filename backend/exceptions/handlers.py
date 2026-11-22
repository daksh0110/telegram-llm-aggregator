from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from schemas.response import error_response


class AppError(Exception):
    def __init__(
        self,
        message: str = "Something went wrong",
        status_code: int = 500,
        error: str | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error = error
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message=message, status_code=404, error="NOT_FOUND")


class BadRequestError(AppError):
    def __init__(self, message: str = "Invalid request"):
        super().__init__(message=message, status_code=400, error="BAD_REQUEST")


async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            message=exc.message,
            error=exc.error,
        ).model_dump(),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=error_response(
            message="Validation failed",
            error="VALIDATION_ERROR",
        ).model_dump(),
    )
