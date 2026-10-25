# Narwal AWS architecture (Academy Learner Lab)

Production topology for Narwal on AWS Academy Learner Lab, aligned with `.specs/features/aws-academy-deploy/spec.md`.

## Goals

- One **public HTTP URL** on the **Elastic IP** for the TCC demo (`http://<eip>/`).
- **Nginx** on EC2 serves the Vite UI and proxies **`/api/*`** to FastAPI (Docker on `127.0.0.1:8080`).
- **FastAPI** on **EC2** (CPU-only; no GPU in Learner Lab).
- **Reproducible infrastructure** via Terraform in `narwal-backend/infra/`.
- **CI/CD** via GitHub Actions: **ECR** (API), **S3 staging + SSM** (UI).

CloudFront is **not** used: Vocareum LabRole denies `cloudfront:*` in this account.

## High-level diagram

```mermaid
flowchart LR
  User[User browser]
  EC2[EC2 Elastic IP]
  Nginx[Nginx :80]
  Static[/var/www/narwal]
  API[Docker API :8080]
  ECR[ECR narwal-api]
  S3App[S3 app bucket]
  EBS[(EBS gp3 SQLite)]

  User --> EC2
  EC2 --> Nginx
  Nginx -->|"/"| Static
  Nginx -->|"/api/*"| API
  API --> EBS
  API --> S3App
  API --> ECR
```

## Terraform resources (implemented)

| Resource (Terraform address) | AWS purpose |
| ---------------------------- | ----------- |
| S3 app bucket (CLI / `create-app-bucket.sh`, not TF) | Model weights, uploads, UI prefix `ui/` (`S3_BUCKET`) |
| `aws_ecr_repository.api` | Backend container images |
| `aws_security_group.api` | TCP **80** public (Nginx); API not exposed on 8080 |
| `aws_instance.api` | Amazon Linux 2023, Nginx + Docker, **LabInstanceProfile**, **t3.medium** default |
| `aws_ebs_volume.data` + attachment | Persistent `/data` for SQLite |
| `aws_eip.api` + association | Stable public demo URL |

**Outputs** (`infra/outputs.tf`): `app_public_url`, `app_bucket_name`, `ecr_repository_url`, `ecr_repository_name`, `api_instance_id`, `api_public_ip` / `api_elastic_ip`.

## Component responsibilities

| Component | Role |
| --------- | ---- |
| **Nginx** | Serves static UI; reverse-proxies `/api/*` to the API container on localhost. |
| **EC2** | Edge + compute; runs Docker from ECR; **LabInstanceProfile** for S3/ECR. |
| **S3 (app)** | Models, analysis objects, and CI staging for UI under prefix `ui/`. |
| **Elastic IP** | Stable IPv4 for demos after stop/start. |
| **EBS** | `/data` → `SQLITE_PATH` (SQLite metadata). |
| **ECR** | Immutable backend images from GitHub Actions. |
| **GitHub Actions** | Backend: ECR push, SSM restart, health on `APP_PUBLIC_URL`. Frontend: S3 sync to `ui/`, SSM sync to `/var/www/narwal`. |

## Application integration

### Backend environment (AWS)

| Variable | Local (MinIO) | AWS |
| -------- | ------------- | --- |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | unset |
| `S3_FORCE_PATH_STYLE` | `true` | `false` |
| `S3_PUBLIC_ENDPOINT` | `http://localhost:9000` | unset or public S3 virtual-hosted HTTPS URL for presigned images |
| `AWS_ACCESS_KEY_ID` | minioadmin | unset (instance profile) |
| `SQLITE_PATH` | `/app/db/narwal.db` (Compose) | `/data/narwal.db` on EBS |
| `FIX_DB_PERMISSIONS` | `1` in Compose | unset — chown EBS mount once (`scripts/prepare-sqlite-volume.sh`) |

See `.env.aws.example` and `.env.example`.

### Frontend routing

Development uses the Vite proxy (`/api` → `localhost:8080`). In AWS, the **browser origin is the Elastic IP (Nginx on :80)**. Keep **relative** paths such as `/api/auth/login`. Do not rely on the dev proxy in production builds (see `narwal-frontend/docs/DEPLOY-AWS.md`).

## CI/CD wiring (GitHub)

### narwal-backend

| Kind | Name | Maps to |
| ---- | ---- | ------- |
| Secret | `AWS_*` session trio | Learner Lab |
| Variable | `AWS_REGION` | `us-east-1` |
| Variable | `ECR_REPOSITORY`, `ECR_REPOSITORY_URL` | Terraform ECR outputs |
| Variable | `EC2_INSTANCE_ID` | `api_instance_id` |
| Variable | `APP_PUBLIC_URL` | `app_public_url` |

Workflows: `ci.yml`, `deploy-aws.yml`.

### narwal-frontend

| Kind | Name | Maps to |
| ---- | ---- | ------- |
| Secret | Same AWS trio | Learner Lab |
| Variable | `AWS_REGION` | `us-east-1` |
| Variable | `APP_S3_BUCKET` | `app_bucket_name` |
| Variable | `EC2_INSTANCE_ID` | `api_instance_id` |

Workflow: `deploy-aws.yml` (build → `s3://bucket/ui/` → SSM sync on instance).

## Security notes (lab scope)

- Secrets on **EC2** only (`/etc/narwal/env`), not in git or Terraform.
- GitHub Actions uses **Learner Lab access keys** as repository secrets.
- API listens on **127.0.0.1:8080**; only Nginx is on the public security group.

## Model runtime and instance sizing

- Default startup model: **YOLO + ConvNeXt (balanced)**.
- **Initial: `t3.medium` (4 GiB).** OOM → resize to **`t3.large`** in console.
- Model switching in UI may increase RAM use (`GatewayPool`).

## Out of scope

- CloudFront, RDS, ECS/Fargate, API Gateway, GPU, custom DNS (unless later confirmed).

## Traceability

| Doc section | Requirements |
| ----------- | ------------ |
| Nginx + single origin | DEPLOY-01, DEPLOY-02 |
| ECR + GHA | DEPLOY-09, DEPLOY-11 |
| SQLite on EBS | DEPLOY-08 |
| S3 models/images | DEPLOY-04 |
| This doc + outputs | DEPLOY-12, DEPLOY-15 |
