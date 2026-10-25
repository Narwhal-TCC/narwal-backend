# AWS Academy deploy — complete checklist

End-to-end guide for **first-time setup**, **CI wiring**, and **P1 demo sign-off** in Learner Lab (`us-east-1`). Use this document as the single checklist; [learner-lab-operations.md](./learner-lab-operations.md) covers day-to-day ops and troubleshooting.

---

## Part 0 — Prerequisites

Complete before `terraform apply` or any deploy.

| # | Requirement | How to verify |
| - | ----------- | ------------- |
| P0.1 | **AWS Academy Learner Lab** access with **Start Lab** available | Lab status green in console |
| P0.2 | **Repos** cloned locally: `narwal-backend`, `narwal-frontend` | On branch with `infra/` and workflows |
| P0.3 | **Terraform** ≥ 1.5 | `terraform version` |
| P0.4 | **AWS CLI** v2 | `aws --version` |
| P0.5 | **Docker** (for local image build / push fallback) | `docker version` |
| P0.6 | **Node.js** 20+ (frontend manual build) | `node --version` |
| P0.7 | **Model weights** on disk under `narwal-backend/data/models/` (or paths matching `.env.example` S3 URIs) | Files exist before `aws s3 sync` |
| P0.8 | **Git Bash or WSL** on Windows (for `scripts/aws/*.sh`) | `./scripts/aws/smoke_app.sh` runs |

**Lab credentials (each session):** After **Start Lab**, set CLI credentials (include session token when the lab provides one):

```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."   # required for Learner Lab keys
export AWS_DEFAULT_REGION=us-east-1
```

Or: `aws configure` and paste keys; for session token use `aws configure set aws_session_token "..."`.

**Local pre-flight (no AWS needed):**

```bash
cd narwal-backend
terraform -chdir=infra validate
python -m ruff check app tests
python -m pytest tests/unit tests/integration -q
python -m pytest tests/unit/test_infra_contract.py tests/unit/test_aws_deploy_scripts.py -q
```

| Pass? | Step |
| ----- | ---- |
| ☐ | Terraform validates |
| ☐ | Ruff clean |
| ☐ | Full pytest green |
| ☐ | Infra + deploy script contract tests green |

---

## Part 1 — One-time infrastructure (Terraform)

| # | Action | Pass? |
| - | ------ | ----- |
| 1.1 | **Start Lab** in AWS Academy | ☐ |
| 1.2 | Copy `infra/terraform.tfvars.example` → `infra/terraform.tfvars` | ☐ |
| 1.3 | Set **globally unique** `app_bucket_name` in `terraform.tfvars` (same value will become `S3_BUCKET` on the API) | ☐ |
| 1.3b | **Create S3 bucket outside Terraform** (SCP blocks TF `aws_s3_bucket` reads): `APP_BUCKET_NAME=<name> bash scripts/aws/create-app-bucket.sh` | ☐ |
| 1.4 | Run init / plan / apply | ☐ |
| 1.5 | Save all Terraform outputs (see commands below) | ☐ |

**Commands** (from repo root):

```bash
cd narwal-backend/infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — unique app_bucket_name

terraform init
terraform plan
terraform apply
```

**Capture outputs** (repeat anytime):

```bash
cd narwal-backend
terraform -chdir=infra output
terraform -chdir=infra output -raw app_public_url
terraform -chdir=infra output -raw app_bucket_name
terraform -chdir=infra output -raw ecr_repository_url
terraform -chdir=infra output -raw ecr_repository_name
terraform -chdir=infra output -raw api_instance_id
terraform -chdir=infra output -raw api_elastic_ip
```

**PowerShell:** Commands assume cwd is the **monorepo parent** (`narwal-tcc`) or you first `cd` to `narwal-backend`. If you are already in `narwal-backend\infra` after `apply`, skip `cd narwal-backend` and run `terraform output` (no `-chdir=infra`). From `narwal-backend` root, use `terraform -chdir=infra output …` as above.

| Output | Used for |
| ------ | -------- |
| `app_public_url` | Public demo URL, `APP_PUBLIC_URL`, smoke script |
| `app_bucket_name` | `S3_BUCKET`, models, UI staging prefix `ui/` |
| `ecr_repository_url` / `ecr_repository_name` | Docker push, bootstrap, GHA |
| `api_instance_id` | SSM deploy (API + UI sync), EC2 console |
| `api_elastic_ip` | Same host as `app_public_url` |

| Pass? | Step |
| ----- | ---- |
| ☐ | `terraform apply` succeeded |
| ☐ | Outputs recorded in a secure note (not committed) |

---

## Part 2 — EC2 data volume and environment file

The API container runs as **uid 1001** and expects SQLite at **`/data/narwal.db`** with host mount **`/data`**.

| # | Action | Pass? |
| - | ------ | ----- |
| 2.1 | **Start** the API EC2 instance (`api_instance_id`) if stopped | ☐ |
| 2.2 | Connect via **Session Manager** (SSM) or SSH (if lab allows) | ☐ |
| 2.3 | Run **`prepare-sqlite-volume.sh`** on the instance (as root) | ☐ |
| 2.4 | Create **`/etc/narwal/env`** from `.env.aws.example` | ☐ |
| 2.5 | Set **`S3_BUCKET`** = `app_bucket_name`; fix all `s3://...` model URIs to that bucket | ☐ |
| 2.6 | Set strong **`JWT_SECRET`**, admin passwords (not defaults for public demo) | ☐ |
| 2.7 | Do **not** set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` on EC2 (use **LabInstanceProfile**) | ☐ |
| 2.8 | Do **not** set `FIX_DB_PERMISSIONS` on EC2 | ☐ |

**On the EC2 instance (root):**

```bash
# Copy prepare script to instance (from your laptop), or paste contents:
sudo mkdir -p /data
sudo sh /path/to/narwal-backend/scripts/prepare-sqlite-volume.sh /data
ls -la /data   # expect owner uid 1001
```

**Create env file on instance:**

```bash
sudo mkdir -p /etc/narwal
sudo nano /etc/narwal/env   # or scp from laptop after editing locally
sudo chmod 600 /etc/narwal/env
```

Template: [`narwal-backend/.env.aws.example`](../../.env.aws.example). Replace `YOUR_APP_BUCKET_FROM_TERRAFORM_OUTPUT` with `terraform output -raw app_bucket_name`.

| Pass? | Step |
| ----- | ---- |
| ☐ | `/data` owned by 1001 |
| ☐ | `/etc/narwal/env` exists, mode 600, bucket + URIs correct |

---

## Part 3 — Upload model weights to S3

From a machine with lab credentials and local model files:

```bash
cd narwal-backend
APP_BUCKET="$(terraform -chdir=infra output -raw app_bucket_name)"

# Example: sync all .pt under data/models preserving layout
aws s3 sync "data/models/" "s3://${APP_BUCKET}/models/" \
  --exclude "*" --include "*.pt"
```

Verify keys match URIs in `/etc/narwal/env` (v1/v2/v3 paths per `.env.aws.example`).

```bash
aws s3 ls "s3://${APP_BUCKET}/models/" --recursive | head
```

| Pass? | Step |
| ----- | ---- |
| ☐ | Required `.pt` objects exist at URIs in env file |
| ☐ | No accidental upload of secrets |

---

## Part 4 — Backend container (ECR image + bootstrap)

### Option A — GitHub Actions (recommended after secrets are set)

See **Part 6** first, then trigger:

- Push to `master`/`main` touching `app/**`, `Dockerfile`, or workflow; or
- **Actions → Deploy backend (AWS) → Run workflow**

Workflow: [`.github/workflows/deploy-aws.yml`](../../.github/workflows/deploy-aws.yml) — build, push to ECR, SSM restart, curl `APP_PUBLIC_URL/api/health`.

### Option B — Manual build and push (first boot or CI not wired)

**On your laptop:**

```bash
cd narwal-backend
ECR_URL="$(terraform -chdir=infra output -raw ecr_repository_url)"
AWS_REGION=us-east-1

aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_URL%%/*}"

docker build -t narwal-api .
docker tag narwal-api:latest "${ECR_URL}:latest"
docker push "${ECR_URL}:latest"
```

**On EC2 instance:**

```bash
export AWS_REGION=us-east-1
export ECR_REPOSITORY_URL="<ecr_repository_url from terraform>"
sudo -E bash /path/to/narwal-backend/scripts/aws/ec2-api-bootstrap.sh
```

Or set vars in `/etc/profile.d/narwal.sh` and re-run bootstrap after each new image.

**Validate on instance (direct to API container):**

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/health
# Expect 200 after models load (first start may take several minutes)
docker logs narwal-api --tail 50
```

| Pass? | Step |
| ----- | ---- |
| ☐ | Image in ECR (`aws ecr describe-images --repository-name ...`) |
| ☐ | Container running (`docker ps`) |
| ☐ | Local health **200** on instance |
| ☐ | No OOM / repeated restarts (if yes → resize to `t3.large`, see ops doc) |

---

## Part 5 — Frontend static assets (S3 staging + EC2 Nginx)

Production uses **relative `/api/*`** on the **Elastic IP** (Nginx proxies to the API) — no Vite proxy. See [narwal-frontend/docs/DEPLOY-AWS.md](../../../narwal-frontend/docs/DEPLOY-AWS.md).

### Option A — GitHub Actions

After frontend secrets/vars (Part 6): push to `master`/`main` or **workflow_dispatch** (uploads to `s3://<app_bucket>/ui/`, then SSM sync to `/var/www/narwal`).

### Option B — Manual

```bash
cd narwal-frontend
npm ci
npm test
npm run build

APP_BUCKET="$(terraform -chdir=../narwal-backend/infra output -raw app_bucket_name)"
INSTANCE_ID="$(terraform -chdir=../narwal-backend/infra output -raw api_instance_id)"

aws s3 sync dist/ "s3://${APP_BUCKET}/ui/" --delete

aws ssm send-command \
  --instance-ids "${INSTANCE_ID}" \
  --document-name "AWS-RunShellScript" \
  --parameters commands="aws s3 sync s3://${APP_BUCKET}/ui/ /var/www/narwal/ --delete && chown -R nginx:nginx /var/www/narwal && systemctl reload nginx" \
  --query "Command.CommandId" --output text
# Wait for command success in SSM console or: aws ssm wait command-executed ...
```

| Pass? | Step |
| ----- | ---- |
| ☐ | `npm test` passed |
| ☐ | `dist/` synced to `s3://<app_bucket>/ui/` |
| ☐ | SSM sync to `/var/www/narwal` succeeded |
| ☐ | `curl -sI "$(terraform -chdir=../narwal-backend/infra output -raw app_public_url)/" | head` → HTTP 200 |

---

## Part 6 — GitHub Actions secrets and variables (one-time per lab rotation)

Configure **both** repositories when lab session keys change.

### Shared secrets (backend + frontend)

| Secret | Value |
| ------ | ----- |
| `AWS_ACCESS_KEY_ID` | From Start Lab |
| `AWS_SECRET_ACCESS_KEY` | From Start Lab |
| `AWS_SESSION_TOKEN` | From Start Lab (required) |

### narwal-backend — repository variables

| Variable | Source |
| -------- | ------ |
| `AWS_REGION` | `us-east-1` |
| `ECR_REPOSITORY` | `terraform output -raw ecr_repository_name` |
| `ECR_REPOSITORY_URL` | `terraform output -raw ecr_repository_url` |
| `EC2_INSTANCE_ID` | `terraform output -raw api_instance_id` |
| `APP_PUBLIC_URL` | `terraform output -raw app_public_url` |

Workflows: [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml), [`.github/workflows/deploy-aws.yml`](../../.github/workflows/deploy-aws.yml).

### narwal-frontend — repository variables

| Variable | Source |
| -------- | ------ |
| `AWS_REGION` | `us-east-1` |
| `APP_S3_BUCKET` | `terraform output -raw app_bucket_name` |
| `EC2_INSTANCE_ID` | `terraform output -raw api_instance_id` |

| Pass? | Step |
| ----- | ---- |
| ☐ | All secrets set on both repos |
| ☐ | All variables set from Terraform outputs |
| ☐ | Backend **CI** workflow green on latest push |
| ☐ | Backend **deploy** workflow green (or manual Part 4B done) |
| ☐ | Frontend **deploy** workflow green (or manual Part 5B done) |

---

## Part 7 — Automated validation (command-line)

Run with **EC2 running** and **container healthy**.

```bash
cd narwal-backend
export APP_PUBLIC_URL="$(terraform -chdir=infra output -raw app_public_url)"

# HTTP smoke: /api/health + /api/auth/login (demo/demo by default)
./scripts/aws/smoke_app.sh

# Optional: override seeded user
# export SMOKE_USERNAME=demo SMOKE_PASSWORD=demo
```

**Manual curls (same checks):**

```bash
BASE="${APP_PUBLIC_URL%/}"

curl -sS "${BASE}/api/health"
curl -sS -X POST "${BASE}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo"}'
```

**Login with token (optional deeper API check):**

```bash
TOKEN="$(curl -sS -X POST "${BASE}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo"}' | jq -r .access_token)"

curl -sS -H "Authorization: Bearer ${TOKEN}" "${BASE}/api/models"
```

| Pass? | Check | Expected |
| ----- | ----- | -------- |
| ☐ | `smoke_app.sh` | Exit 0 |
| ☐ | `/api/health` | HTTP 200 |
| ☐ | `/api/auth/login` | HTTP 200, JSON with `access_token` |
| ☐ | UI over HTTP | `curl -sI "${APP_PUBLIC_URL%/}/" \| head` → 200, not 502 |

---

## Part 8 — P1 browser sign-off (demo / spec DEPLOY-01–04)

Execute with API **running**, models in S3, env on EC2, UI deployed.

| Step | Action | Pass? | Notes |
| ---- | ------ | ----- | ----- |
| 8.1 | Part 7 smoke script green | ☐ | |
| 8.2 | Open `app_public_url` — UI loads (HTTP), no console errors | ☐ | |
| 8.3 | Log in as **demo** / **demo** (or values from `SEED_DEMO_*` on EC2) | ☐ | JWT stored; app shell loads |
| 8.4 | **New analysis** → upload valid PNG/JPEG (≤ 10 MB) | ☐ | 200 or documented 4xx/503 — **not** Nginx **502** |
| 8.5 | **Result** page: overlay / metrics visible | ☐ | |
| 8.6 | **Presigned image:** DevTools → Network → result image request **200**, image renders (not broken icon) | ☐ | If fail: adjust `S3_PUBLIC_ENDPOINT` / ops doc |
| 8.7 | *(Optional)* Stop EC2 → demo URL unreachable until instance started | ☐ | Cost-saving behavior |

**Recorded by:** _______________ **Date:** _______________ **App URL:** _______________

When steps **8.1–8.6** pass, update `.specs/features/aws-academy-deploy/spec.md` traceability: mark **DEPLOY-01–04** **Verified** with date and domain in the evidence note.

---

## Part 9 — Every work session (quick checklist)

| # | Action | Pass? |
| - | ------ | ----- |
| 9.1 | **Start Lab** | ☐ |
| 9.2 | Refresh local CLI creds (and GitHub secrets if keys rotated) | ☐ |
| 9.3 | **Start** EC2 API instance | ☐ |
| 9.4 | Wait for container / model preload; run Part 7 smoke | ☐ |
| 9.5 | Demo or develop | ☐ |
| 9.6 | **Stop** EC2 when done (save credits) | ☐ |
| 9.7 | **End Lab** when finished for the day | ☐ |

Public URL for slides:

```bash
terraform -chdir=narwal-backend/infra output -raw app_public_url
```

---

## Part 10 — Teardown (optional)

```bash
cd narwal-backend/infra
terraform destroy
```

Confirm empty ECR images and S3 buckets if lab policy requires manual cleanup.

| Pass? | Step |
| ----- | ---- |
| ☐ | Resources destroyed or documented as retained |

---

## Troubleshooting (quick)

| Symptom | Likely cause | What to run / fix |
| ------- | ------------ | ----------------- |
| Smoke health ≠ 200 | EC2 stopped or container down | Start instance; `docker ps` / `ec2-api-bootstrap.sh` |
| Nginx 502 on `/api/*` | API container down | `docker ps`; SG allows :80; API on 127.0.0.1:8080 |
| Login 200 but analyze 503 | Models missing or OOM | `aws s3 ls`; resize to `t3.large` |
| 503 metadata / readonly DB | Bad `/data` permissions | `prepare-sqlite-volume.sh` |
| Broken result images | Presigned URL host | See [learner-lab-operations.md](./learner-lab-operations.md) |
| GHA deploy fails health | Wrong `APP_PUBLIC_URL` or stopped EC2 | Fix vars; start instance |
| Terraform S3 Object Lock AccessDenied | Academy SCP | Do **not** use `aws_s3_bucket` in TF; run `scripts/aws/create-app-bucket.sh` first, then `terraform apply` |

---

## Related automated checks (CI / repo)

| Check | Command / location |
| ----- | ------------------ |
| Terraform layout, no IAM users, Nginx `/api/*` proxy | `python -m pytest tests/unit/test_infra_contract.py -q` |
| Bootstrap + smoke script contract | `python -m pytest tests/unit/test_aws_deploy_scripts.py -q` |
| Backend CI | `.github/workflows/ci.yml` |
| Backend deploy + health | `.github/workflows/deploy-aws.yml` |
| Frontend test + S3 sync | `narwal-frontend/.github/workflows/deploy-aws.yml` |

---

## Document map

| Doc | Role |
| --- | ---- |
| **This file** | Full checklist + commands |
| [learner-lab-operations.md](./learner-lab-operations.md) | Day-to-day ops, sizing, presigned URLs |
| [infra/README.md](../../infra/README.md) | Terraform-only reference |
| [architecture.md](./architecture.md) | TCC topology narrative |
