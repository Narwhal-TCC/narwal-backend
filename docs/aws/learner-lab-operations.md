# Learner Lab operations (Narwal)

Quick reference for demos, smoke tests, and GitHub Actions variables. Full checklist: [validation-checklist.md](./validation-checklist.md).

## Demo URL

- **Primary link for slides:** `terraform output -raw app_public_url` → e.g. `http://54.x.x.x/`
- UI and API share that origin; Nginx proxies `/api/*` to the container.

## Smoke test (login + health)

From repo root (Git Bash / WSL):

```bash
export APP_PUBLIC_URL="$(terraform -chdir=infra output -raw app_public_url)"
./scripts/aws/smoke_app.sh
```

The script curls `/api/health` and `/api/auth/login` and exits non-zero on failure. Demo credentials match seeded users (`app/bootstrap/seed.py`).

Manual curls:

```bash
curl -s -X POST "${APP_PUBLIC_URL%/}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo"}'

curl -s "${APP_PUBLIC_URL%/}/api/health"
```

### Upload model weights to S3

```bash
BUCKET="$(terraform -chdir=infra output -raw app_bucket_name)"
aws s3 sync data/models/ "s3://${BUCKET}/models/" --exclude "*/.*"
```

Adjust paths to match `DETECTOR_S3_URI`, `YOLO_G5_S3_URI`, etc. in `.env.example`.

## Start / stop API (save credits)

1. **Start Lab** in AWS Academy (session keys expire — refresh GitHub secrets when keys rotate).
2. **Start EC2** instance (`narwal-api` tag) if stopped.
3. Confirm container: Session Manager → `docker ps` (or SSM run `docker ps`).
4. **Stop EC2** when done demoing for the day.

Stopping EC2 **saves credit**; S3, ECR, and EBS storage still incur charges.

## Troubleshooting

| Symptom | Likely cause | Fix |
| ------- | ------------- | --- |
| Connection refused on demo URL | EC2 stopped | Start instance |
| UI 404 / empty | UI not deployed | Run frontend GHA or manual S3+SSM sync (see checklist §5) |
| `/api/*` 502 / connection reset | Docker down or env missing | Check `/etc/narwal/env`, restart container (`ec2-api-bootstrap.sh`) |
| Login works, images broken | Bad presigned URL host | Fix `S3_PUBLIC_ENDPOINT` / public S3 pattern |
| 503 MODEL_UNAVAILABLE | Models missing in S3 or OOM | Sync models; resize instance |

## GitHub Actions variables

### narwal-backend

| Variable | Source |
| -------- | ------ |
| `AWS_REGION` | `us-east-1` |
| `ECR_REPOSITORY` | `ecr_repository_name` |
| `ECR_REPOSITORY_URL` | `ecr_repository_url` |
| `EC2_INSTANCE_ID` | `api_instance_id` |
| `APP_PUBLIC_URL` | `app_public_url` |

Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`.

### narwal-frontend

| Variable | Source |
| -------- | ------ |
| `AWS_REGION` | `us-east-1` |
| `APP_S3_BUCKET` | `app_bucket_name` |
| `EC2_INSTANCE_ID` | `api_instance_id` |

Same secrets as backend.

## Elastic IP

The instance keeps the same **Elastic IP** after stop/start. Use `app_public_url` output — do not rely on ephemeral private IPs.
