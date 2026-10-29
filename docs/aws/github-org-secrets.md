# GitHub organization secrets (Narwhal-TCC)

Use **organization** secrets so **narwal-backend** and **narwal-frontend** share Learner Lab credentials and Terraform inputs. Workflows use `${{ secrets.NAME }}`; GitHub resolves org secrets when each repo is granted access.

## Required organization secrets

| Secret | Purpose |
| ------ | ------- |
| `AWS_ACCESS_KEY_ID` | Learner Lab (Start Lab → AWS Details) |
| `AWS_SECRET_ACCESS_KEY` | Same |
| `AWS_SESSION_TOKEN` | Same (required for temporary keys) |
| `APP_BUCKET_NAME` | Globally unique app bucket (`terraform apply -var app_bucket_name=…`, models, UI prefix `ui/`) |

## Optional

| Secret | Purpose |
| ------ | ------- |
| `STATE_BUCKET_NAME` | S3 backend for Terraform state; defaults to `APP_BUCKET_NAME` with key `terraform/narwal-app/state.tfstate` |

Deploy workflows read **Terraform outputs** after `apply`; repository variables (`ECR_REPOSITORY`, `APP_PUBLIC_URL`, …) are only needed for manual/local deploys.

## CI behavior (main branch)

| Repo | Workflow | Terraform | Redeploy |
| ---- | -------- | ----------- | -------- |
| **narwal-backend** | `ci.yml` (PR/push) | `validate` only | — |
| **narwal-backend** | `deploy-aws.yml` | `init` + `apply` | ECR + SSM + `/api/health` |
| **narwal-frontend** | `ci.yml` | — | `npm test` only |
| **narwal-frontend** | `deploy-aws.yml` | `apply` (backend `infra/` checkout) | S3 `ui/` + SSM + GET `/` |

Both deploy workflows support **workflow_dispatch** with **deploy_only** to skip Terraform and redeploy the app only.

## Configure (org admin)

```bash
gh auth refresh -h github.com -s admin:org

gh secret set AWS_ACCESS_KEY_ID     -o Narwhal-TCC -b"<from lab>"
gh secret set AWS_SECRET_ACCESS_KEY -o Narwhal-TCC -b"<from lab>"
gh secret set AWS_SESSION_TOKEN       -o Narwhal-TCC -b"<from lab>"
gh secret set APP_BUCKET_NAME         -o Narwhal-TCC -b"your-unique-bucket-name"
# optional:
gh secret set STATE_BUCKET_NAME       -o Narwhal-TCC -b"your-unique-bucket-name"
```

Or run after **Start Lab**:

```powershell
.\scripts\aws\sync-lab-secrets-to-github-org.ps1 -StateBucket "your-unique-bucket-name"
```

Grant secret access to **narwal-backend** and **narwal-frontend** in the org secret settings.

## When each workflow runs

| Workflow | Trigger |
| -------- | ------- |
| **backend `ci.yml`** | Every push or PR to **`master`** (Terraform validate, ruff, pytest — no AWS). |
| **backend `deploy-aws.yml`** | Push to **`master`** when paths change (`app/`, `infra/`, `Dockerfile`, …), or **Run workflow** (optional `deploy_only`). |
| **frontend `ci.yml`** | Every push or PR to **`master`** (`npm test` only). |
| **frontend `deploy-aws.yml`** | Push to **`master`** when frontend paths change, or **Run workflow** (`deploy_only`, `backend_ref` default **`master`**). |

Pushes that only touch docs or unrelated paths do **not** start deploy workflows.

## Automate `/etc/narwal/env`

The API reads **`/etc/narwal/env` on EC2** (not from git). Recommended pattern:

1. Maintain a **local** file from [`.env.aws.example`](../../.env.aws.example) (never commit secrets).
2. Upload to S3 (private prefix):

   ```bash
   export APP_BUCKET_NAME=your-bucket
   bash scripts/aws/upload-env-to-s3.sh .env.aws.local
   ```

   Object: **`s3://<APP_BUCKET_NAME>/config/narwal.env`**

3. Each **backend deploy** SSM step pulls that object to `/etc/narwal/env` (if present), then restarts Docker.

To refresh env after edits, re-upload and run deploy with **`deploy_only: true`**.

Alternative: one-time manual `scp`/Session Manager, or store the file only in S3 and skip GitHub secrets for env content.

## Rotation

Update the three AWS secrets (and session token) whenever the lab session changes.
