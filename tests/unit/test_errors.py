from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import (
    AnalysisNotFoundError,
    AppError,
    InferenceTimeoutError,
    InvalidCredentialsError,
    InvalidImageError,
    ModelUnavailableError,
    StorageError,
    StoreUnavailableError,
    UnauthorizedError,
    UnknownModelError,
    register_error_handlers,
)


def _client_for(error: AppError) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/raise")
    def raise_error():
        raise error

    return TestClient(app)


def test_invalid_image_returns_400_with_code():
    client = _client_for(InvalidImageError("Unsupported image format"))
    response = client.get("/raise")
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_IMAGE"
    assert body["message"] == "Unsupported image format"


def test_unknown_model_returns_400_with_code_and_default_message():
    client = _client_for(UnknownModelError())
    response = client.get("/raise")
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "UNKNOWN_MODEL"
    assert body["message"] == "Unknown model id"


def test_model_unavailable_returns_503_with_code():
    client = _client_for(ModelUnavailableError("Model not loaded"))
    response = client.get("/raise")
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "MODEL_UNAVAILABLE"
    assert body["message"] == "Model not loaded"


def test_store_unavailable_returns_503_with_code_and_default_message():
    client = _client_for(StoreUnavailableError())
    response = client.get("/raise")
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "STORE_UNAVAILABLE"
    assert body["message"] == "Metadata store is unavailable"


def test_all_error_codes_have_expected_status():
    cases = [
        (InvalidCredentialsError(), 401, "INVALID_CREDENTIALS"),
        (UnauthorizedError(), 401, "UNAUTHORIZED"),
        (InvalidImageError(), 400, "INVALID_IMAGE"),
        (ModelUnavailableError(), 503, "MODEL_UNAVAILABLE"),
        (InferenceTimeoutError(), 504, "INFERENCE_TIMEOUT"),
        (StorageError(), 503, "STORAGE_ERROR"),
        (StoreUnavailableError(), 503, "STORE_UNAVAILABLE"),
        (AnalysisNotFoundError(), 404, "ANALYSIS_NOT_FOUND"),
    ]
    for error, status, code in cases:
        client = _client_for(error)
        response = client.get("/raise")
        assert response.status_code == status
        assert response.json()["code"] == code
