from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Any |None = None
    error: str | None = None


def success_response(
    data: Any = None,
    message: str = "Request successful",
) -> ApiResponse:
    return ApiResponse(
        success=True,
        message=message,
        data=data,
    )


def error_response(
    message: str = "Something went wrong",
    error: str | None = None,
) -> ApiResponse:
    return ApiResponse(
        success=False,
        message=message,
        data=None,
        error=error,
    )