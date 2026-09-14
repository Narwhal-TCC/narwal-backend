# Narwal Backend

Sonar mine analysis API — FastAPI + S3/MinIO + DynamoDB.

Authenticated org members upload a sonar image, get detection boxes with confidence back
synchronously, and can list or reopen their organization's past analyses.

## Local stack

```bash
cp .env.example .env      # local-only defaults; .env is gitignored
docker compose up --build
```

| Service | URL | Notes |
| ------- | --- | ----- |
| API | http://localhost:8080 | OpenAPI at `/docs`, liveness at `/health` |
| MinIO API | http://localhost:9000 | bucket `narwal`, created by `minio-init` and on startup |
| MinIO console | http://localhost:9001 | `minioadmin` / `minioadmin` |
| DynamoDB Local | http://localhost:8000 | `-inMemory`, so data resets when the container is recreated |

Startup runs a best-effort bootstrap: ensure the bucket, seed the platform admin from
`PLATFORM_ADMIN_*`, and preload the model. Each step logs a warning and the API still serves if a
backing store is not ready yet. DynamoDB Local runs in memory, so re-seeding happens on every
`docker compose up`.

## Environment variables

All variables and their local defaults live in [`.env.example`](.env.example). On AWS, leave
`S3_ENDPOINT_URL`, `S3_PUBLIC_ENDPOINT`, and `DYNAMODB_ENDPOINT_URL` unset, set
`S3_FORCE_PATH_STYLE=false`, and prefer an instance profile over static keys. Never commit a real
`JWT_SECRET` or admin password.

`S3_PUBLIC_ENDPOINT` matters locally: presigned image URLs are signed against the host in the URL,
so browsers need `http://localhost:9000` rather than the Docker-internal `http://minio:9000`.

## Smoke test

```bash
# 1. log in as the seeded platform admin
curl -s -X POST http://localhost:8080/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}'

# 2. analyze an image (PNG or JPEG, max 10 MB)
curl -s -X POST http://localhost:8080/analyses \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file=@sonar.png;type=image/png'

# 3. list and reopen analyses for your organization
curl -s http://localhost:8080/analyses -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8080/analyses/$ANALYSIS_ID -H "Authorization: Bearer $TOKEN"
```

Analyze needs the `.keras` artifact at `MODEL_S3_URI`; upload it to MinIO (console or
`mc cp model.keras local/narwal/models/v1/model.keras`) or the call returns
`503 MODEL_UNAVAILABLE`.

| Failure | Status | Code |
| ------- | ------ | ---- |
| Bad credentials | 401 | `INVALID_CREDENTIALS` |
| Missing or invalid token | 401 | `UNAUTHORIZED` |
| Non-PNG/JPEG, corrupt, or >10 MB upload | 400 | `INVALID_IMAGE` |
| Model missing or unloadable | 503 | `MODEL_UNAVAILABLE` |
| Inference over the timeout | 504 | `INFERENCE_TIMEOUT` |
| Unknown id, or an id from another org | 404 | `ANALYSIS_NOT_FOUND` |

## Tests

```bash
python -m pytest tests/unit tests/integration -q
python -m ruff check app tests
```

Tests use moto and a fake model gateway, so neither AWS nor TensorFlow is required.

For real `.keras` inference on a host that will load the artifact, install the optional extra:

```bash
pip install -e ".[inference]"
```

The API still runs without it; `KerasModelGateway` returns `MODEL_UNAVAILABLE` until TensorFlow/Keras is present and the object is loadable.
