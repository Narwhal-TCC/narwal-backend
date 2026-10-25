# AWS Academy Deploy Specification

## Problem Statement

Narwal runs locally (Docker + MinIO + SQLite) but the TCC requires a **public demo URL**, **infrastructure as code**, **GitHub Actions CI/CD**, and **architecture + cost documentation**—all within **AWS Academy Learner Lab** limits (~$100 credit, restricted services, `us-east-1` / `us-west-2` only).

## Goals

- [ ] Deliver one stable **HTTP URL** (`app_public_url` on Elastic IP) with **Nginx** serving the React UI and proxying `/api/*` to FastAPI on EC2 (infra + CI; P1 sign-off via [validation-checklist.md](../../../docs/aws/validation-checklist.md)).
- [x] Provision core infrastructure with **Terraform** under `narwal-backend/infra/`, using **LabRole** / **LabInstanceProfile** (no custom IAM users).
- [x] Ship container images via **Amazon ECR**; deploy backend through **GitHub Actions**.
- [x] Keep metadata on **SQLite** (EBS on API instance); images and model weights in **S3**.
- [x] Document **architecture** and **cost scenarios** for the report and sprint demo.

## Out of Scope

| Feature | Reason |
| ------- | ------ |
| Amazon RDS / PostgreSQL migration | SQLite on EBS is the chosen store; RDS deferred to limit scope and app changes. |
| ECS / Fargate / App Runner / API Gateway | Not on Learner Lab foundational allow list or unnecessary for single-API EC2 pattern. |
| GPU instances | Not available in Learner Lab instance tiers. |
| Amazon CloudFront | **Blocked:** Vocareum LabRole denies `cloudfront:*` (403 in console and Terraform). |
| Custom domain (Route 53) | Not confirmed on allow list; HTTP on Elastic IP is sufficient for demo. |
| ECR-less deploy | **Superseded:** ECR is in scope per product decision (2026-10-25). |
| Multi-environment (staging/prod accounts) | Single Learner Lab account; one stack. |
| Model-gateway RAM optimization (unload unused pipelines) | Operational mitigation is instance sizing; code change not required for deploy MVP. |

---

## Assumptions & Open Questions

| Assumption / decision | Chosen default | Rationale | Confirmed? |
| --------------------- | -------------- | --------- | ---------- |
| AWS account type | AWS Academy **Learner Lab** | Stated by user | y |
| Primary region | **us-east-1** | Default in app config; `vockey` key pair available in lab docs | y |
| Edge pattern | **EC2 Nginx (UI + `/api/*` proxy) + S3 app bucket** | CloudFront denied in lab; single origin on EIP | y |
| Public TLS / HTTPS | **Not required** for TCC demo | User confirmed HTTP on EIP is acceptable | y |
| API instance type (initial) | **t3.medium** (4 GiB RAM) | User choice; resize to `t3.large` if OOM during testing | y |
| Elastic IP | **One EIP** on API EC2 | Stable public demo URL; survives stop/start | y |
| Registry | **Amazon ECR** | Immutable deploy artifact for GitHub Actions | y |
| Metadata DB | **SQLite** on EBS at `SQLITE_PATH` | Existing app; no repository rewrite | y |
| Secrets | **Environment variables on EC2** (not committed) | User choice; `JWT_SECRET`, admin creds, `LLM_API_KEY` | y |
| IAM in Terraform | Reference **LabInstanceProfile**; avoid creating IAM users/roles | Learner Lab IAM restrictions | y |
| Frontend repo | **narwal-frontend** separate; deploy workflow + docs linked from backend | Two git repos today | y |
| GitHub → AWS auth | **Access keys** in GitHub Secrets | OIDC provider creation often blocked in Learner Lab | y |
| Presigned image URLs | `S3_PUBLIC_ENDPOINT` unset or set to browser-reachable S3 HTTPS host | Virtual-hosted S3 URLs (no CloudFront) | y |
| UI deploy | **S3 prefix `ui/` + SSM sync** to `/var/www/narwal` | GHA cannot SCP; instance profile pulls from app bucket | y |
| Model switchable in UI | All registered models remain selectable | Product requirement; RAM risk mitigated by instance resize | y |
| Sprint deadline | Working public stack in **~1 week**; polish + docs by defense (~1 month) | User timeline | y |

**Open questions:** none — all resolved or logged above.

---

## User Stories

### P1: Public web application ⭐ MVP

**User Story**: As a jury member, I want to open one public link and use login, upload, and analysis so that the TCC demo does not depend on localhost.

**Why P1**: Sprint presentation requires a public URL.

**Acceptance Criteria**:

1. WHEN a user opens `app_public_url` (HTTP on Elastic IP) THEN the system SHALL serve the production-built React application from Nginx without browser console errors attributable to wrong API origin.
2. WHEN a user submits `POST /api/auth/login` through the same public hostname THEN the system SHALL return HTTP 200 with a JWT for valid seeded credentials.
3. WHEN a user uploads a valid PNG/JPEG (≤ 10 MB) via `POST /api/analyses` with a Bearer token THEN the system SHALL return HTTP 200 with detection payload or a documented API error code (4xx/503/504), not an edge **502** due to misconfigured `/api/*` proxy routing.
4. The EC2 edge SHALL configure Nginx so path prefix `/api/*` is reverse-proxied to the API container on `127.0.0.1:8080` and all other paths serve the static SPA from `/var/www/narwal`.
5. IF the API EC2 instance is stopped THEN the demo URL SHALL be unreachable until the instance is started (UI and API share one host).

**Independent Test**: Open `app_public_url` → login as demo user → run one analysis → view result page.

---

### P2: Infrastructure as code (Learner Lab–compatible)

**User Story**: As a developer, I want reproducible infrastructure in the backend repo so that the stack can be recreated for the report and after lab resets.

**Why P2**: TCC architecture evidence; reduces clickops drift.

**Acceptance Criteria**:

1. The repository SHALL contain Terraform under `narwal-backend/infra/` that creates at minimum: S3 **app** bucket, ECR repository, EC2 instance with **LabInstanceProfile** (Nginx + Docker), security group, and Elastic IP association — **without** CloudFront resources.
2. WHEN `terraform apply` runs in `us-east-1` with Learner Lab credentials THEN the system SHALL complete without creating IAM users or custom IAM roles outside lab-permitted patterns.
3. The Terraform outputs SHALL expose at minimum: `app_public_url`, app bucket name, ECR repository URL, EC2 instance id, and API Elastic IP.
4. The system SHALL use **SQLite** on an EBS volume (or root volume path documented in runbook) with `SQLITE_PATH` configured on the API container.

**Independent Test**: Fresh apply in lab → outputs match running resources → smoke test P1 passes.

---

### P3: CI/CD via GitHub Actions

**User Story**: As a developer, I want pushes to main to deploy backend and frontend so that the demo stays current without manual docker commands on every change.

**Why P2**: Explicit TCC deliverable (CI/CD on GitHub Actions).

**Acceptance Criteria**:

1. WHEN a push to the default branch updates `narwal-backend` THEN GitHub Actions SHALL run unit/integration tests, build the Docker image, push to the configured **ECR** repository, and restart the API container on EC2 (SSM Run Command or equivalent documented mechanism).
2. WHEN a push to the default branch updates `narwal-frontend` THEN GitHub Actions SHALL run tests, build static assets, sync to `s3://<app_bucket>/ui/`, and run SSM on EC2 to sync files into `/var/www/narwal` and reload Nginx.
3. IF a workflow step lacks AWS credentials THEN the workflow SHALL fail explicitly and SHALL NOT echo secret values in logs.
4. The backend workflow SHALL verify `/api/health` returns HTTP 200 after deploy against `APP_PUBLIC_URL`.

**Independent Test**: Commit a visible UI string change → pipeline green → change visible after invalidation; backend image tag updates on ECR after backend change.

---

### P4: Operations, architecture, and cost documentation

**User Story**: As a TCC author, I want architecture and cost write-ups so that constraints and trade-offs are defensible in the report.

**Why P2**: Required deliverables from user.

**Acceptance Criteria**:

1. The repository SHALL include `docs/aws/architecture.md` with a diagram matching the deployed topology (Nginx/EC2, S3 app bucket, ECR, EIP, SQLite on EBS).
2. The repository SHALL include `docs/aws/cost-analysis.md` with at least two monthly scenarios: **demo hours** (EC2 stopped when idle) and **always-on EC2** (labeled as over budget).
3. The repository SHALL include `docs/aws/learner-lab-operations.md` describing Start Lab, start/stop EC2, model upload to S3, and EIP behavior.
4. WHEN documenting instance sizing THEN the docs SHALL state initial **t3.medium** and the OOM mitigation path (**resize to t3.large**).

**Independent Test**: Reader can follow operations doc to start lab, start API, and run P1 smoke test without chat history.

---

## Edge Cases

- IF EC2 RAM is exhausted during model preload or inference THEN the API container SHALL exit or return `503 MODEL_UNAVAILABLE` AND operators SHALL resize instance type per runbook (not silently fail with generic 502).
- IF Learner Lab session ends THEN stopped EC2 and preserved EBS/S3 resources SHALL remain per lab policy AND operators SHALL Start Lab before demos.
- IF presigned URLs use wrong `S3_PUBLIC_ENDPOINT` THEN browsers SHALL fail to load analysis images AND configuration SHALL be corrected to a public S3 hostname.
- IF GitHub Actions deploy runs while EC2 is stopped THEN the deploy workflow SHALL fail the health check OR document manual instance start before deploy.
- WHEN users switch among multiple model ids in one session THEN the API SHALL allow selection AND operators SHALL monitor RAM (GatewayPool caches pipelines).

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status | Evidence |
| -------------- | ----- | ----- | ------ | -------- |
| DEPLOY-01 | P1: HTTPS app | Execute | Pending lab | `docs/aws/validation-checklist.md` §2–3 (browser HTTPS UI) |
| DEPLOY-02 | P1: `/api` routing | Execute | Verified | `infra/ec2.tf` Nginx proxy; `tests/unit/test_infra_contract.py` |
| DEPLOY-03 | P1: Auth smoke | Execute | Verified | `scripts/aws/smoke_app.sh`; backend `deploy-aws.yml` health/login paths |
| DEPLOY-04 | P1: Analyze smoke | Execute | Pending lab | `docs/aws/validation-checklist.md` §4–6 (upload + presigned image) |
| DEPLOY-05 | P2: Terraform layout | Execute | Verified | `infra/*.tf`; `terraform validate` in CI |
| DEPLOY-06 | P2: Lab IAM constraints | Execute | Verified | `tests/unit/test_infra_contract.py` (no `aws_iam_user`; `LabInstanceProfile`) |
| DEPLOY-07 | P2: Terraform outputs | Execute | Verified | `infra/outputs.tf` |
| DEPLOY-08 | P2: SQLite on EBS | Execute | Verified | `infra/ec2.tf`, `.env.aws.example`, `scripts/prepare-sqlite-volume.sh` |
| DEPLOY-09 | P3: Backend GHA + ECR | Execute | Verified | `.github/workflows/deploy-aws.yml` |
| DEPLOY-10 | P3: Frontend GHA + S3 | Execute | Verified | `narwal-frontend/.github/workflows/deploy-aws.yml`, `docs/DEPLOY-AWS.md` |
| DEPLOY-11 | P3: Post-deploy health | Execute | Verified | `.github/workflows/deploy-aws.yml` `APP_PUBLIC_URL` `/api/health` step |
| DEPLOY-12 | P4: Architecture doc | Execute | Verified | `docs/aws/architecture.md` |
| DEPLOY-13 | P4: Cost doc | Execute | Verified | `docs/aws/cost-analysis.md` |
| DEPLOY-14 | P4: Operations doc | Execute | Verified | `docs/aws/learner-lab-operations.md` |
| DEPLOY-15 | P4: Instance sizing notes | Execute | Verified | `docs/aws/architecture.md`, `cost-analysis.md`, ops doc |

**Coverage:** 15 total, 15 mapped in `tasks.md` (22 tasks T1–T22)

---

## Success Criteria

- [ ] `app_public_url` completes P1 smoke test (login + one analysis) with EC2 running — use [validation-checklist.md](../../../docs/aws/validation-checklist.md) in lab.
- [x] `terraform apply` / `destroy` documented; no disallowed services in plan (`infra/README.md`, contract tests).
- [x] Both GitHub Actions workflows defined for ECR push and S3 sync (green runs require lab credentials on `main`).
- [x] Architecture and cost documents included in repo and consistent with Terraform + CI wiring.
