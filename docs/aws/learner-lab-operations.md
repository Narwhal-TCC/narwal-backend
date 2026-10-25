# AWS Academy Learner Lab — Narwal operations

Runbook for developers operating Narwal in **Learner Lab** (`us-east-1` recommended). Complements Terraform under [`infra/`](../../infra/) and GitHub Actions deploys.

## Before each work session

1. Open **AWS Academy** → **Learner Lab** → **Start Lab** (wait for green status).
2. Copy **AWS Access Key ID**, **Secret Access Key**, and **Session Token** if using CLI locally or refreshing GitHub secrets.
3. In EC2 console, **start** the API instance (`api_instance_id` from `terraform output`) if it is stopped.
4. Confirm **Elastic IP** (`api_elastic_ip`) is still associated (same IP after stop/start when EIP is attached).

## Public URL

- **Primary link for slides:** `terraform output -raw cloudfront_domain_name` → `https://<value>/`
- Do **not** use raw EC2 IP for HTTPS demos unless CloudFront is misconfigured.

## Smoke test (after API is running)

### Script (recommended)

```bash
export CLOUDFRONT_URL="https://$(terraform -chdir=infra output -raw cloudfront_domain_name)"
./scripts/aws/smoke_cloudfront.sh
```

The script curls `/api/health` and `/api/auth/login` via CloudFront and exits non-zero on failure. Demo credentials are the seeded users (see `app/bootstrap/seed.py`).

### Manual curls

```bash
# Login
curl -s -X POST "${CLOUDFRONT_URL%/}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo"}'

# Health (via CloudFront)
curl -s "${CLOUDFRONT_URL%/}/api/health"
```

Then use the browser: login → new analysis → upload image (full P1 steps in [validation-checklist.md](./validation-checklist.md)).

## One-time / rare tasks

### Upload model weights to S3

From a machine with AWS creds and local `data/models/`:

```bash
APP_BUCKET="$(terraform -chdir=infra output -raw app_bucket_name)"
aws s3 sync "data/models/" "s3://${APP_BUCKET}/models/" --exclude "*" --include "*.pt"
```

Adjust paths to match `DETECTOR_S3_URI`, `YOLO_G5_S3_URI`, etc. in `.env.example`.

### Seed SQLite users

On first boot the API **seeds** admin/demo users if missing (see `app/bootstrap/seed.py`). Set non-default `JWT_SECRET` and admin passwords via EC2 env before exposing publicly.

### SQLite volume on EC2 (required once per data path)

The image runs **uvicorn as uid 1001**. Mount persistent storage at **`/data`**, set **`SQLITE_PATH=/data/narwal.db`**, and **do not** set `FIX_DB_PERMISSIONS` (that flag is for local Compose bind mounts only).

On the instance (as root), before the first container start:

```bash
sudo sh /path/to/narwal-backend/scripts/prepare-sqlite-volume.sh /data
```

Production env template: [`.env.aws.example`](../../.env.aws.example) → copy to `/etc/narwal/env` on the instance (gitignored on the server). Bootstrap: [`scripts/aws/ec2-api-bootstrap.sh`](../../scripts/aws/ec2-api-bootstrap.sh).

If you see **`503 Metadata store is unavailable`** or SQLite **readonly database** in logs, check ownership: `ls -la /data` should show uid **1001** (or re-run the prepare script).

### ECR first deploy (manual fallback)

If GitHub Actions is not wired yet:

```bash
ECR_URL="$(terraform -chdir=infra output -raw ecr_repository_url)"
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "${ECR_URL%%/*}"
docker build -t narwal-api .
docker tag narwal-api:latest "${ECR_URL}:latest"
docker push "${ECR_URL}:latest"
# On EC2: pull and run via ec2-api-bootstrap.sh or deploy-aws.yml SSM commands
```

## EC2 instance sizing

- **Initial:** `t3.medium` (4 GiB RAM) — Terraform variable `instance_type` default.
- **Symptom of insufficient RAM:** container restart, `503 MODEL_UNAVAILABLE`, OOM in `dmesg` / Docker logs during startup or first analyze.
- **Action:** Stop instance → change type to **`t3.large`** → start → retest.
- Default preload loads **YOLO G5, YOLO A, and three ConvNeXt** weights; switching models may load more.

## End of session

1. **Stop** EC2 (do not terminate if you want to keep the same disk and EIP association pattern).
2. **End Lab** when finished (lab policy may stop instances automatically).

Stopping EC2 **saves credit**; S3, CloudFront, ECR, and EBS continue to incur storage charges.

## When `/api` fails but the UI loads

| Symptom | Likely cause | Fix |
| ------- | ------------ | --- |
| CloudFront 502/504 on `/api/*` | EC2 stopped or Docker down | Start instance; check container |
| 502 | Security group or wrong origin port | Origin must reach `:8080` |
| Login works, images broken | Bad presigned URL host | Fix `S3_PUBLIC_ENDPOINT` / public S3 access pattern |
| 503 MODEL_UNAVAILABLE | Models missing in S3 or OOM | Sync models; resize instance |
| 503 Metadata store is unavailable | SQLite path not writable by uid 1001 | Run `prepare-sqlite-volume.sh`; confirm `SQLITE_PATH` matches the mount |

## GitHub Actions secrets and variables

Configure **both** repositories with Learner Lab session credentials (rotate when the lab session ends).

### Shared secrets

| Secret | Purpose |
| ------ | ------- |
| `AWS_ACCESS_KEY_ID` | Learner Lab access key |
| `AWS_SECRET_ACCESS_KEY` | Learner Lab secret key |
| `AWS_SESSION_TOKEN` | Session token (required for lab keys) |

### narwal-backend variables

| Variable | Terraform output |
| -------- | ---------------- |
| `AWS_REGION` | `us-east-1` (default) |
| `ECR_REPOSITORY` | `ecr_repository_name` |
| `ECR_REPOSITORY_URL` | `ecr_repository_url` |
| `EC2_INSTANCE_ID` | `api_instance_id` |
| `CLOUDFRONT_URL` | `https://` + `cloudfront_domain_name` |

Workflows: `.github/workflows/ci.yml`, `.github/workflows/deploy-aws.yml`.

### narwal-frontend variables

| Variable | Terraform output |
| -------- | ---------------- |
| `AWS_REGION` | `us-east-1` |
| `UI_S3_BUCKET` | `ui_bucket_name` |
| `CLOUDFRONT_DISTRIBUTION_ID` | `cloudfront_distribution_id` |

See [narwal-frontend/docs/DEPLOY-AWS.md](https://github.com/narwal-tcc/narwal-frontend/blob/master/docs/DEPLOY-AWS.md) (or sibling clone).

Never commit keys or `.env` with production secrets.

## Related docs

- [architecture.md](./architecture.md)
- [cost-analysis.md](./cost-analysis.md)
- [validation-checklist.md](./validation-checklist.md)
- Spec: `.specs/features/aws-academy-deploy/spec.md`
