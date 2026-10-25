# AWS Academy Learner Lab — Narwal operations

Runbook for developers operating Narwal in **Learner Lab** (`us-east-1` recommended). Complements Terraform (once added under `infra/`) and GitHub Actions deploys.

## Before each work session

1. Open **AWS Academy** → **Learner Lab** → **Start Lab** (wait for green status).
2. Copy **AWS Access Key ID**, **Secret Access Key**, and **Session Token** if using CLI locally.
3. In EC2 console, **start** the API instance if it is stopped.
4. Confirm **Elastic IP** is still associated (same IP after stop/start when EIP is attached).

## Public URL

- **Primary link for slides:** CloudFront domain from Terraform output (`cloudfront_domain_name`).
- Do **not** use raw EC2 IP for HTTPS demos unless CloudFront is misconfigured.

## Smoke test (after API is running)

Replace `https://<cloudfront-domain>` with your distribution.

```bash
# Login
curl -s -X POST "https://<cloudfront-domain>/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo"}'

# Health (via CloudFront)
curl -s "https://<cloudfront-domain>/api/health"
```

Then use the browser: login → new analysis → upload image.

## One-time / rare tasks

### Upload model weights to S3

From a machine with AWS creds and local `data/models/`:

```bash
aws s3 sync "data/models/" "s3://<app-bucket>/models/" --exclude "*" --include "*.pt"
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

Example run after ECR pull (adjust image URL and env file):

```bash
docker run -d --name narwal-api --restart unless-stopped \
  -p 8080:8080 \
  -v /data:/data \
  -e SQLITE_PATH=/data/narwal.db \
  --env-file /etc/narwal/api.env \
  <account>.dkr.ecr.us-east-1.amazonaws.com/narwal-api:latest
```

If you see **`503 Metadata store is unavailable`** or SQLite **readonly database** in logs, check ownership: `ls -la /data` should show uid **1001** (or re-run the prepare script).

### ECR first deploy (manual fallback)

If GitHub Actions is not wired yet:

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com
docker build -t narwal-api .
docker tag narwal-api:latest <ecr-repo-url>:latest
docker push <ecr-repo-url>:latest
# On EC2: pull and run with env file + volume for SQLITE_PATH
```

## EC2 instance sizing

- **Initial:** `t3.medium` (4 GiB RAM).
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

## GitHub Actions secrets (reference)

Store in **narwal-backend** and **narwal-frontend** repository settings:

| Secret / variable | Purpose |
| ----------------- | ------- |
| `AWS_ACCESS_KEY_ID` | Learner Lab session |
| `AWS_SECRET_ACCESS_KEY` | Learner Lab session |
| `AWS_SESSION_TOKEN` | If lab provides temporary session token |
| `AWS_REGION` | `us-east-1` |
| Variables from Terraform | `ECR_REPOSITORY`, `EC2_INSTANCE_ID`, `UI_BUCKET`, `CLOUDFRONT_DISTRIBUTION_ID` |

Never commit keys or `.env` with production secrets.

## Related docs

- [architecture.md](./architecture.md)
- [cost-analysis.md](./cost-analysis.md)
- Spec: `.specs/features/aws-academy-deploy/spec.md`
