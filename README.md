# Narwal Backend

Sonar mine analysis API — FastAPI + S3/MinIO + SQLite metadata.

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
| Metadata | `./db/narwal.db` on the host | Bind-mounted at `/app/db`; `FIX_DB_PERMISSIONS=1` in Compose fixes Windows/Linux dev ownership for uid 1001 |

On AWS the app uses **`/data/narwal.db`** on EBS (not `./db`). Prepare the mount once on the instance: `sudo sh scripts/prepare-sqlite-volume.sh /data`. Do **not** set `FIX_DB_PERMISSIONS` in production.

Startup runs a best-effort bootstrap: ensure the bucket, upload the local RetinaNet and fusion
`.pt` artifacts from `DETECTOR_LOCAL_PATH` / `CLASSIFIER_LOCAL_PATH` when missing in object storage,
seed the platform admin from `PLATFORM_ADMIN_*` and a demo member from `SEED_DEMO_*` when absent in
the database file, and preload both models. Each step logs a warning and the API still serves if a
backing store is not ready yet.

## AWS deployment (Learner Lab)

Spec, design, architecture diagram, cost analysis, and runbook: [`docs/aws/README.md`](docs/aws/README.md).

## Environment variables

All variables and their local defaults live in [`.env.example`](.env.example). On AWS, leave
`S3_ENDPOINT_URL` and `S3_PUBLIC_ENDPOINT` unset, set `S3_FORCE_PATH_STYLE=false`, and prefer an
instance profile over static keys. Never commit a real
`JWT_SECRET` or admin password.

`S3_PUBLIC_ENDPOINT` matters locally: presigned image URLs are signed against the host in the URL,
so browsers need `http://localhost:9000` rather than the Docker-internal `http://minio:9000`.

## Smoke test

```bash
# 1. log in as the seeded demo member (or platform admin: admin / admin)
curl -s -X POST http://localhost:8080/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo","password":"demo"}'

# 2. analyze an image (PNG or JPEG, max 10 MB)
curl -s -X POST http://localhost:8080/analyses \
  -H "Authorization: Bearer $TOKEN" \
  -F 'file=@sonar.png;type=image/png'

# 3. list and reopen analyses for your organization
curl -s http://localhost:8080/analyses -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8080/analyses/$ANALYSIS_ID -H "Authorization: Bearer $TOKEN"
```

Locally, startup uploads `data/models/retinanet_melhor.pt` and
`data/models/fusion_ghostnetv2_mobilenetv2_melhor.pt` to their S3 URIs when missing. Without those
files, upload them to MinIO manually or analyze returns `503 MODEL_UNAVAILABLE`.

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

Tests use moto and a fake model gateway, so neither AWS nor real `.pt` weights are required in CI.

For real two-stage inference, install the project deps (`torch`, `torchvision`, `timm`) and ensure
both artifacts are available via the configured S3 URIs (or local seed paths).
`TwoStageTorchGateway` returns `MODEL_UNAVAILABLE` until both models download and load.
RetinaNet uses `DETECTOR_SCORE_THRESHOLD` (default **0.5**, same as training `score_thresh`) before running the fusion classifier.
