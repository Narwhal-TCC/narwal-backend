# Narwal AWS architecture (Academy Learner Lab)

This document describes the **deployed production topology** for Narwal on AWS Academy Learner Lab. It aligns with `.specs/features/aws-academy-deploy/spec.md` and `design.md`.

## Goals

- One **public HTTPS URL** for the TCC demo (CloudFront default domain, e.g. `https://dxxxxxxxx.cloudfront.net`).
- **FastAPI** inference on **EC2** (CPU-only; no GPU in Learner Lab).
- **React** static hosting on **S3** behind the same CloudFront distribution.
- **Reproducible infrastructure** via Terraform in `narwal-backend/infra/`.
- **CI/CD** via GitHub Actions pushing to **ECR** (API) and **S3** (UI).

## High-level diagram

```mermaid
flowchart LR
  User[User browser]
  CF[CloudFront HTTPS]
  S3UI[S3 static UI]
  EC2[EC2 Docker API t3.medium]
  ECR[ECR narwal-api]
  S3Data[S3 app bucket]
  EBS[(EBS gp3 SQLite)]
  EIP[Elastic IP]

  User --> CF
  CF -->|default| S3UI
  CF -->|/api/*| EC2
  EIP --- EC2
  EC2 --> EBS
  EC2 --> S3Data
  EC2 --> ECR
```

## Terraform resources (implemented)

| Resource (Terraform address) | AWS purpose |
| ---------------------------- | ----------- |
| `aws_s3_bucket.ui` | Vite static assets (OAC + CloudFront only) |
| `aws_s3_bucket.app` | Model weights, uploads, optional DB backups (`S3_BUCKET`) |
| `aws_ecr_repository.api` | Backend container images |
| `aws_security_group.api` | TCP 8080 to API (lab MVP ingress documented in TF) |
| `aws_instance.api` | Amazon Linux 2023, `LabInstanceProfile`, **t3.medium** default |
| `aws_ebs_volume.data` + `aws_volume_attachment.data` | Persistent `/data` for SQLite |
| `aws_eip.api` + `aws_eip_association.api` | Stable API origin for CloudFront |
| `aws_cloudfront_distribution.main` | Dual origin: S3 UI + EC2:8080, behavior `/api/*` → API |

**Outputs** (see `infra/outputs.tf`): `cloudfront_domain_name`, `cloudfront_distribution_id`, `ui_bucket_name`, `app_bucket_name`, `ecr_repository_url`, `ecr_repository_name`, `api_instance_id`, `api_public_ip` / `api_elastic_ip`.

## Component responsibilities

| Component | Role |
| --------- | ---- |
| **CloudFront** | TLS termination; routes `/` to UI bucket; routes `/api/*` to API origin (EC2:8080). |
| **S3 (UI)** | Hosts Vite production build (`index.html`, `/assets/*`). |
| **S3 (app)** | Application data bucket (`app_bucket_name` / `S3_BUCKET`): model `.pt` files, analysis uploads. |
| **EC2** | Runs Docker image from ECR; `uvicorn` on port 8080; **LabInstanceProfile** for S3/ECR API access. |
| **Elastic IP** | Stable IPv4 for API origin when instance is stopped/started within the lab. |
| **EBS** | Data volume at `/data` holding `SQLITE_PATH` (SQLite metadata). |
| **ECR** | Stores immutable backend images produced by GitHub Actions. |
| **GitHub Actions** | Backend: test, ECR push, SSM restart, `/api/health` check. Frontend: test, build, S3 sync, invalidation. |

## Application integration

### Backend environment (AWS)

| Variable | Local (MinIO) | AWS |
| -------- | ------------- | --- |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | unset |
| `S3_FORCE_PATH_STYLE` | `true` | `false` |
| `S3_PUBLIC_ENDPOINT` | `http://localhost:9000` | unset or public HTTPS host for presigned URLs |
| `AWS_ACCESS_KEY_ID` | minioadmin | unset (instance profile) |
| `SQLITE_PATH` | `/app/db/narwal.db` (Compose) | `/data/narwal.db` on persistent EBS |
| `FIX_DB_PERMISSIONS` | `1` in `docker-compose.yml` only | **unset** — chown the EBS mount on the host once (`scripts/prepare-sqlite-volume.sh`) |

See `.env.aws.example` and `.env.example` in the backend repo for the full list.

### Frontend routing

Development uses Vite proxy (`/api` → `localhost:8080`). In AWS, the **browser origin is CloudFront**, so relative requests like `/api/auth/login` must hit CloudFront and be forwarded to EC2. Production builds must **not** depend on the dev proxy (see `narwal-frontend/docs/DEPLOY-AWS.md`).

## CI/CD wiring (GitHub)

### narwal-backend (`.github/workflows/`)

| Kind | Name | Maps to |
| ---- | ---- | ------- |
| Secret | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Learner Lab session |
| Variable | `AWS_REGION` | `us-east-1` |
| Variable | `ECR_REPOSITORY` | `ecr_repository_name` |
| Variable | `ECR_REPOSITORY_URL` | `ecr_repository_url` |
| Variable | `EC2_INSTANCE_ID` | `api_instance_id` |
| Variable | `CLOUDFRONT_URL` | `https://${cloudfront_domain_name}` |

Workflows: `ci.yml` (test + `terraform validate`); `deploy-aws.yml` (ECR push, SSM restart, post-deploy health).

### narwal-frontend

| Kind | Name | Maps to |
| ---- | ---- | ------- |
| Secret | Same AWS trio as backend | Learner Lab session |
| Variable | `AWS_REGION` | `us-east-1` |
| Variable | `UI_S3_BUCKET` | `ui_bucket_name` |
| Variable | `CLOUDFRONT_DISTRIBUTION_ID` | `cloudfront_distribution_id` |

Workflow: `deploy-aws.yml` (vitest, Vite build, S3 sync, invalidation).

## Security notes (lab scope)

- Secrets (`JWT_SECRET`, admin password, `LLM_API_KEY`) live in **EC2 environment** only—not in git or Terraform plaintext.
- GitHub Actions uses **Learner Lab access keys** stored as repository secrets; rotate if leaked.
- Security groups should limit API port exposure where practical; CloudFront is the intended public entry.

## Model runtime and instance sizing

- Default model at startup: **YOLO + ConvNeXt (balanced)** — loads **two YOLO weights and three ConvNeXt classifiers** into memory.
- **Initial instance: `t3.medium` (4 GiB RAM).** If the container OOMs during preload or analyze, resize to **`t3.large` (8 GiB)** in the EC2 console (allowed up to `large` in Learner Lab).
- Switching models in the UI may load **additional** pipelines (cached in `GatewayPool`); full registry testing needs more RAM.

## Out of scope for this architecture

- RDS, ECS/Fargate, API Gateway, App Runner, GPU instances, custom DNS (unless later confirmed in your lab allow list).

## Traceability

| Doc section | Requirements |
| ----------- | ------------ |
| CloudFront + dual origin | DEPLOY-01, DEPLOY-02 |
| ECR + GHA | DEPLOY-09, DEPLOY-11 |
| SQLite on EBS | DEPLOY-08 |
| S3 models/images | DEPLOY-04 (existing app behavior) |
| This doc + outputs | DEPLOY-12, DEPLOY-15 |
