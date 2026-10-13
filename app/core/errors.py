from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    code: str = "INTERNAL_ERROR"
    status_code: int = 500
    default_message: str = "An unexpected error occurred"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class InvalidCredentialsError(AppError):
    code = "INVALID_CREDENTIALS"
    status_code = 401
    default_message = "Invalid username or password"


class UnauthorizedError(AppError):
    code = "UNAUTHORIZED"
    status_code = 401
    default_message = "Missing or invalid authentication token"


class InvalidImageError(AppError):
    code = "INVALID_IMAGE"
    status_code = 400
    default_message = "Invalid or unsupported image upload"


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    status_code = 400
    default_message = "Request validation failed"


class UnknownModelError(AppError):
    code = "UNKNOWN_MODEL"
    status_code = 400
    default_message = "Unknown model id"


class ModelUnavailableError(AppError):
    code = "MODEL_UNAVAILABLE"
    status_code = 503
    default_message = "Detection model is unavailable"


class InferenceTimeoutError(AppError):
    code = "INFERENCE_TIMEOUT"
    status_code = 504
    default_message = "Inference exceeded the configured timeout"


class StorageError(AppError):
    code = "STORAGE_ERROR"
    status_code = 503
    default_message = "Object storage operation failed"


class StoreUnavailableError(AppError):
    code = "STORE_UNAVAILABLE"
    status_code = 503
    default_message = "Metadata store is unavailable"


class AnalysisNotFoundError(AppError):
    code = "ANALYSIS_NOT_FOUND"
    status_code = 404
    default_message = "Analysis not found"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )
