# infrastructure-repo — lab discoveries & patterns for Narwal

**Date:** 2026-10-29  
**Context:** AWS Academy Learner Lab (`us-east-1`, account `905418131942`). Compared [`infrastructure-repo`](../../../infrastructure-repo/) (Jupyter pipeline) with [`narwal-backend/infra`](../../infra/) and ran live destroy/apply experiments.

---

## Executive summary

| Stack | Role | CI provision? | Deploy path |
| ----- | ---- | ------------- | ----------- |
| **infrastructure-repo** | Ubuntu EC2 + Jupyter/MLflow + optional client S3 | Yes (`terraform apply` in GHA) | SSH + Ansible, build on host |
| **narwal-backend/infra** | AL2023 EC2 + Nginx + ECR API + external app S3 | No (manual one-time apply) | GHA → ECR + SSM; UI → S3 `ui/` + SSM |

Both can coexist as **separate EC2 instances** in the same lab account. Do not merge into one Terraform root without namespacing (SG names, buckets, state keys).

---

## What we did in the lab (2026-10-29)

### 1. Destroyed `narwal-backend/infra` resources

| Step | Result |
| ---- | ------ |
| `terraform destroy` (narwal-backend) | Removed EIP, key pair, TLS key, SG, most ECR lifecycle policy |
| **Blocked ~6m** on SG delete | EC2 still attached to SG; state listed instance `i-07a45c6e854928587` but **running** instance was `i-0e2a637935592b18d` (state drift after replace) |
| Manual `terminate-instances` | Required to unblock SG deletion |
| ECR delete | Failed until images removed; `aws ecr delete-repository --force` worked |
| Orphan EBS | `vol-0d3f886b8f7e75a56` deleted manually (not in final destroy plan) |

**Still in AWS (not Terraform-managed):**

- S3 **`narwal-bucket-20261025`** (app bucket from `create-app-bucket.sh` / tfvars)
- Lab key pair **`vockey`**

### 2. Applied `infrastructure-repo/terraform/ec2`

| Step | Result |
| ---- | ------ |
| `terraform init` with S3 backend | Used pre-created app bucket + key `terraform/narwhal-jupyter/state.tfstate` — **backend init succeeded** |
| Full `terraform apply` | **Failed** on two issues (below) |
| Targeted apply (EC2 + EBS only) | **Succeeded** — Jupyter host `i-00aab2809a208ffe5`, public IP **`34.228.158.222`** |

**Partial / orphan resources from failed apply:**

- S3 bucket **`narwhal-client-4075252d`** (created; removed from TF state after SCP read failure)
- SG **`ssh-access`** (`sg-07c02091c0ea252d1`)
- Ansible/GHA **deploy job not run** (no SSH key in repo for `vockey`)

---

## Failures observed (actionable)

### A. Academy SCP vs `aws_s3_bucket` (infrastructure-repo)

**Error:** `s3:GetBucketObjectLockConfiguration` → explicit deny on LabRole.

**Same class of problem** documented for Narwal in `infra/README.md` and `s3.tf`.

| Repo | Current approach | Lab result |
| ---- | ---------------- | ---------- |
| **narwal-backend** | Bucket created via `scripts/aws/create-app-bucket.sh`; TF only outputs `app_bucket_name` | Stable |
| **infrastructure-repo** | `aws_s3_bucket` + `aws_s3_bucket_versioning` in TF | Create may succeed; **refresh/plan/apply after create fails** |

**Pattern for Narwal (keep):** do not manage app/client buckets as `aws_s3_bucket` in Learner Lab. Pass bucket name via variable/output; create with CLI script.

**Pattern to borrow for Jupyter repo:** mirror Narwal — external bucket create + optional use of **same app bucket** with prefix `jupyter-client/` or separate CLI-created bucket; drop versioning resource or enable via CLI if needed.

### B. Default Ubuntu AMI is ARM64; instance type is x86

**Error:** `InvalidParameterValue` — AMI `ami-0f8cdf1d816ae220f` (arm64) vs `t3.medium` (x86_64).

**Fix applied in lab:** `ubuntu_ami=ami-033ea4ff4a9c726dc` (Jammy 22.04 **amd64**, Canonical).

**Pattern for both repos:** use `data "aws_ami"` with filters (`ubuntu-jammy-22.04-amd64` or `al2023-ami-*-x86_64`) instead of a static AMI id in `variables.tf` defaults.

### C. ECR destroy with images (narwal-backend)

**Error:** `RepositoryNotEmptyException` on `terraform destroy`.

**Patterns to adopt in `ecr.tf`:**

```hcl
resource "aws_ecr_repository" "api" {
  name         = "${var.project_name}-api"
  force_delete = true
  # ...
}
```

Teardown runbook: `aws ecr delete-repository --repository-name <name> --force` when CI pushed manifest lists.

### D. State drift vs running EC2 (narwal-backend)

Replacing EC2 (e.g. SSH key change) leaves **old instance IDs** in console while state tracks new resources. Destroy then **skips** the running instance but **blocks SG** delete for minutes.

**Patterns:**

- Always `terraform state list` + `aws ec2 describe-instances` before destroy.
- Document: terminate stragglers by Name tag, then re-run destroy.
- Prefer **SSM** over SSH for deploy (Narwal GHA) to reduce key-driven instance replacement.

### E. Provider version skew

| Project | Provider pin | Init pulled |
| ------- | ------------ | ----------- |
| **narwal-backend/infra** | `aws ~> 4.67` | 4.x (SCP-aware comments) |
| **infrastructure-repo** | none | **aws 6.71.0** |

AWS provider 5+/6+ performs extra S3 API reads (object lock, etc.), which **amplifies** SCP denials in Academy.

**Pattern:** pin `hashicorp/aws` to `~> 4.67` in infrastructure-repo for lab parity, or accept external S3 only.

---

## Patterns worth adopting (by target)

### narwal-backend `infra/`

| Pattern | Source | Recommendation |
| ------- | ------ | -------------- |
| S3 remote state backend | infrastructure-repo GHA + lab test | **Optional:** store state at `s3://<app_bucket>/terraform/narwal-app/state.tfstate` (lab verified init). Keep local state if team prefers simplicity. |
| Dynamic `backend.hcl` in CI | `pipeline.yml` | If adding infra workflow: generate backend config from secret `STATE_BUCKET_NAME` (same as app bucket). |
| Pin `TF_VERSION` (e.g. 1.9.8) | `pipeline.yml` | Add to `.github/workflows/ci.yml` for reproducible validate. |
| `terraform/.gitignore` template | infrastructure-repo | Add `infra/.gitignore` (state, `.terraform/`, `*.tfvars`, `keys/*.pem`). |
| `random_id` bucket suffix | infrastructure-repo | Not needed — bucket name is explicit in tfvars. |
| ECR `force_delete` | destroy lesson | Add to `ecr.tf`. |
| `data.aws_ami` only | both | Already on AL2023; keep no static AMI defaults. |

### narwal-backend / frontend **CI** (no change to topology)

| Pattern | Source | Recommendation |
| ------- | ------ | -------------- |
| Session token in GHA | both pipelines | Already used; rotate on every Start Lab. |
| Two-stage pipeline | infrastructure-repo | Narwal already splits **manual infra** vs **app deploy**; do not run `terraform apply` on every app push unless you add a dedicated workflow. |
| SSH wait (`nc -z :22`) | infrastructure-repo | Not needed — Narwal uses **SSM** (`deploy-aws.yml`). |
| Ansible on host | infrastructure-repo | Replace with ECR pull + SSM (current design). |

### infrastructure-repo (fixes for lab + CI green)

| Issue | Fix |
| ----- | --- |
| S3 in TF | Remove `aws_s3_bucket*`; document CLI create; pass `client_bucket_name` var |
| AMI default | `data "aws_ami"` amd64 Ubuntu 22.04 |
| Missing `LabInstanceProfile` | Add `iam_instance_profile = "LabInstanceProfile"` on `aws_instance.jupyter` for S3 access without static keys |
| Provider | Pin `aws ~> 4.67` |
| `required_providers` | Declare `random` explicitly (already pulled implicitly) |
| Windows local apply | Use `cmd /c` for multiple `-target=` flags (PowerShell splits args) |
| Full pipeline | CI still needs `EC2_SSH_KEY`, `EC2_KEY_NAME`, `UBUNTU_AMI`, `STATE_BUCKET_NAME` secrets |

---

## S3 backend discovery (important)

Narwal app docs say TF cannot **manage** buckets due to SCP. In this session, **using an existing bucket as Terraform state backend worked**:

```hcl
bucket = "narwal-bucket-20261025"
key    = "terraform/narwhal-jupyter/state.tfstate"
region = "us-east-1"
```

State storage uses different API paths than managing bucket resources in the same root module. **Remote state is viable** for team/CI if the bucket already exists and lab session credentials are valid.

---

## Current lab inventory (after experiments)

| Resource | ID / name | Managed by |
| -------- | --------- | ---------- |
| Jupyter EC2 | `i-00aab2809a208ffe5`, IP `34.228.158.222` | infrastructure-repo TF (partial) |
| Jupyter EBS | `vol-05310c7dac16ee410` | infrastructure-repo TF |
| Jupyter SG | `sg-07c02091c0ea252d1` (`ssh-access`) | infrastructure-repo TF |
| Orphan client bucket | `narwhal-client-4075252d` | Manual cleanup (`aws s3 rb --force`) |
| Narwal app bucket | `narwal-bucket-20261025` | CLI / retained for re-apply Narwal |

**To tear down Jupyter stack:**

```bash
cd infrastructure-repo/terraform/ec2
terraform destroy   # after fixing or removing S3 resources from config
```

**To restore Narwal demo stack:**

```bash
cd narwal-backend/infra
terraform apply
# Re-wire GitHub vars from terraform output; redeploy backend + frontend GHA
```

---

## Related docs

| Doc | Role |
| --- | ---- |
| [validation-checklist.md](./validation-checklist.md) | Narwal deploy + GHA secrets |
| [infra/README.md](../../infra/README.md) | Narwal Terraform reference |
| [architecture.md](./architecture.md) | Narwal topology (Nginx + ECR + SSM) |
| `infrastructure-repo/.github/workflows/pipeline.yml` | Jupyter provision + Ansible deploy |

---

## Open decisions

1. **One account, two stacks:** keep Jupyter and Narwal on separate EC2 instances, or time-share one instance (not recommended — different OS/user-data).
2. **State backend:** local vs S3 in app bucket for Narwal `infra/`.
3. **infrastructure-repo CI:** fix S3 + AMI before relying on push-to-main provision in production demos.
