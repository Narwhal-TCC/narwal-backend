# AWS Academy Deploy Tasks

## Execution Protocol (MANDATORY -- do not skip)

Implement these tasks with the `tlc-spec-driven` skill: **activate it by name and follow its Execute flow and Critical Rules.** Do not search for skill files by filesystem path. The skill is the source of truth for the full flow (per-task cycle, sub-agent delegation, adequacy review, Verifier, discrimination sensor).

**If the skill cannot be activated, STOP and tell the user - do not proceed without it.**

---

**Design**: `.specs/features/aws-academy-deploy/design.md`  
**Spec**: `.specs/features/aws-academy-deploy/spec.md`  
**Status**: Approved

---

## Test Coverage Matrix

> Generated from codebase, project guidelines, and spec — confirm before Execute. Guidelines found: `README.md` (Tests section), `pyproject.toml` (pytest/ruff), `narwal-frontend/package.json` (vitest) — no separate AGENTS.md.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| ---------- | ------------------ | -------------------- | ---------------- | ----------- |
| FastAPI app (unchanged deploy paths) | unit + integration | Existing suites must stay green; no regression | `tests/unit/**`, `tests/integration/**` | `python -m pytest tests/unit tests/integration -q` |
| Terraform / IaC contract | unit | Required files exist; LabInstanceProfile used; no IAM user resources in TF | `tests/unit/test_infra_contract.py` | `python -m pytest tests/unit/test_infra_contract.py -q` |
| AWS deploy scripts (smoke/bootstrap) | unit | Script presence; required env vars documented; no secrets in repo | `tests/unit/test_aws_deploy_scripts.py` | `python -m pytest tests/unit/test_aws_deploy_scripts.py -q` |
| GitHub Actions workflows | none | YAML valid; secrets referenced by name only | `.github/workflows/*.yml` | build gate (no pytest) |
| React frontend (deploy workflow) | unit | Existing vitest suite green on workflow branch | `narwal-frontend/src/**/*.test.ts(x)` | `npm test` (in frontend repo) |
| Entity / Config (tfvars example, env examples) | none | Documented only | `infra/*.example`, `.env.aws.example` | build gate |

## Gate Check Commands

> Generated from codebase — confirm before Execute.

| Gate Level | When to Use | Command |
| ---------- | ----------- | ------- |
| Quick | After unit-only tasks (infra contract, script tests) | `python -m pytest tests/unit/test_infra_contract.py tests/unit/test_aws_deploy_scripts.py -q` |
| Full | After tasks touching app code or integration | `python -m pytest tests/unit tests/integration -q` |
| Build | After Terraform tasks or phase completion | `terraform -chdir=infra validate` && `python -m ruff check app tests` && `python -m pytest tests/unit tests/integration -q` |

---

## Execution Plan

Phases run sequentially; tasks within a phase run in order.

### Phase 1: Terraform foundation

Tasks T1–T10 (see Phase Execution Map).

### Phase 2: EC2 runtime bootstrap

Tasks T11–T13.

### Phase 3: Smoke tooling

Tasks T14–T15.

### Phase 4: Backend CI/CD

Tasks T16–T18.

### Phase 5: Frontend CI/CD

Tasks T19–T20 (includes **narwal-frontend** repo).

### Phase 6: Documentation closure

Tasks T21–T22.

---

## Task Breakdown

### T1: Terraform backend and provider pins

**What**: Add Terraform version constraint and AWS provider configuration for Learner Lab (`us-east-1`).
**Where**: `infra/main.tf`
**Depends on**: None
**Reuses**: `docs/aws/architecture.md` (region decision)
**Requirement**: DEPLOY-05

**Tools**:

- MCP: NONE
- Skill: `aws-advisor` (Lab constraints)

**Done when**:

- [x] `terraform` block and `provider "aws"` with `region = var.aws_region` are declared
- [x] `required_providers` for `hashicorp/aws` are pinned

**Tests**: none  
**Gate**: build (full `terraform validate` completes by T10)

**Commit**: `feat(infra): add terraform version and provider constraints`

---

### T2: Terraform root variables

**What**: Define input variables (project name, instance type default `t3.medium`, Lab instance profile name, tags) and `terraform.tfvars.example`.
**Where**: `infra/variables.tf`
**Depends on**: T1
**Reuses**: AD-005 (t3.medium)
**Requirement**: DEPLOY-05, DEPLOY-06

**Done when**:

- [x] `instance_type` defaults to `t3.medium`
- [x] `iam_instance_profile` defaults to `LabInstanceProfile`
- [x] Example tfvars documents Learner Lab usage without secrets

**Tests**: none  
**Gate**: build

**Commit**: `feat(infra): add terraform input variables`

---

### T3: S3 buckets for UI and application data

**What**: Create UI static bucket and app data bucket (or single bucket with two prefixes — pick one in code and document in outputs).
**Where**: `infra/s3.tf`
**Depends on**: T2
**Reuses**: existing `S3_BUCKET` / model key layout from `.env.example`

_Order: S3 before ECR/SG so later `.tf` files can reference bucket resources._
**Requirement**: DEPLOY-05, DEPLOY-07

**Done when**:

- [x] Buckets block public access by default; UI served via CloudFront OAC only
- [x] App bucket name aligns with `S3_BUCKET` env for API
- [x] `terraform validate` passes

**Tests**: none  
**Gate**: build

**Commit**: `feat(infra): add s3 buckets for ui and app data`

---

### T4: ECR repository for API image

**What**: Add ECR repository with scan-on-push (optional) and lifecycle policy keeping last N images.
**Where**: `infra/ecr.tf`
**Depends on**: T3
**Reuses**: design.md ECR section
**Requirement**: DEPLOY-05, DEPLOY-09

**Done when**:

- [ ] Repository URL available as Terraform output (wired in T8)
- [ ] No IAM user creation in this file

**Tests**: none  
**Gate**: build

**Commit**: `feat(infra): add ecr repository for api`

---

### T5: Security group for API instance

**What**: Security group allowing TCP 8080 from CloudFront (or documented MVP `0.0.0.0/0:8080` with comment for lab) and egress for S3/ECR.
**Where**: `infra/security_groups.tf`
**Depends on**: T4
**Reuses**: design.md network section
**Requirement**: DEPLOY-05

**Done when**:

- [ ] SG resource defined and referenced by EC2 in T6
- [ ] `terraform validate` passes

**Tests**: none  
**Gate**: build

**Commit**: `feat(infra): add api security group`

---

### T6: EC2 API instance, Elastic IP, and SQLite EBS mount

**What**: Launch Amazon Linux 2023 EC2 with `LabInstanceProfile`, `t3.medium`, associated EIP, and EBS volume (or root path) for `/data` SQLite persistence.
**Where**: `infra/ec2.tf`
**Depends on**: T5
**Reuses**: `Dockerfile`, SQLite path from design
**Requirement**: DEPLOY-05, DEPLOY-06, DEPLOY-08

**Done when**:

- [ ] `iam_instance_profile` uses variable default `LabInstanceProfile` (no `aws_iam_role` creation)
- [ ] EIP associated with instance
- [ ] EBS or documented mount point for `SQLITE_PATH`
- [ ] Instance depends on app bucket and ECR (policy via profile, not TF IAM)

**Tests**: none  
**Gate**: build

**Commit**: `feat(infra): add ec2 api instance with eip and data volume`

---

### T7: CloudFront distribution (S3 UI + EC2 `/api/*`)

**What**: CloudFront with OAC to S3 UI origin; custom origin to EC2:8080; ordered behavior `/api/*` → API origin; default → S3.
**Where**: `infra/cloudfront.tf`
**Depends on**: T6
**Reuses**: spec DEPLOY-02, DEPLOY-04
**Requirement**: DEPLOY-01, DEPLOY-02

**Done when**:

- [ ] Viewer protocol HTTPS only
- [ ] `/api/*` behavior forwards cookies/headers needed for JWT (Authorization, multipart)
- [ ] `terraform validate` passes

**Tests**: none  
**Gate**: build

**Commit**: `feat(infra): add cloudfront with s3 and api origins`

---

### T8: Terraform outputs for deploy and CI

**What**: Export CloudFront domain, UI bucket, app bucket, ECR URL/name, instance id, Elastic IP.
**Where**: `infra/outputs.tf`
**Depends on**: T7
**Reuses**: design.md outputs list
**Requirement**: DEPLOY-07

**Done when**:

- [ ] All outputs named in design.md exist
- [ ] `terraform validate` passes

**Tests**: none  
**Gate**: build

**Commit**: `feat(infra): add terraform outputs for deploy`

---

### T9: Terraform operator README

**What**: Document `init/plan/apply/destroy`, Learner Lab Start Lab, required variables, and post-apply steps (model upload, EC2 env file).
**Where**: `infra/README.md`
**Depends on**: T8
**Reuses**: `docs/aws/learner-lab-operations.md`
**Requirement**: DEPLOY-05

**Done when**:

- [ ] Apply instructions mention `LabInstanceProfile` and no IAM user creation
- [ ] Points to smoke script (T14) and ops doc

**Tests**: none  
**Gate**: build

**Commit**: `docs(infra): add terraform apply runbook`

---

### T10: Infra contract unit tests

**What**: Add pytest asserting Terraform layout, banned resources (IAM users), and presence of `LabInstanceProfile` on EC2.
**Where**: `tests/unit/test_infra_contract.py`
**Depends on**: T9
**Reuses**: `tests/unit/test_local_stack.py` patterns
**Requirement**: DEPLOY-06

**Done when**:

- [ ] Tests fail if `aws_iam_user` appears in `infra/`
- [ ] Tests assert required `.tf` files exist
- [ ] Quick gate passes

**Tests**: unit  
**Gate**: quick

**Commit**: `test(infra): add terraform layout contract tests`

---

### T11: EC2 API bootstrap shell script

**What**: Script to install Docker, login to ECR, pull image tag, run container with env-file and SQLite volume mount on host port 8080.
**Where**: `scripts/aws/ec2-api-bootstrap.sh`
**Depends on**: T10
**Reuses**: `Dockerfile` CMD
**Requirement**: DEPLOY-08, DEPLOY-09

**Done when**:

- [ ] Script is idempotent-safe (stop/remove old container name)
- [ ] Documents required env vars (no secret values)
- [ ] Uses instance metadata/profile for ECR login (no hardcoded keys)

**Tests**: none  
**Gate**: quick

**Commit**: `feat(deploy): add ec2 docker bootstrap script`

---

### T12: Wire EC2 user-data to bootstrap script

**What**: Template user-data in Terraform to install prerequisites and invoke bootstrap (or embed minimal first-boot pull of `:latest`).
**Where**: `infra/ec2.tf`
**Depends on**: T11
**Reuses**: T6 instance resource
**Requirement**: DEPLOY-08

**Done when**:

- [ ] User-data references ECR repo from T4
- [ ] `terraform validate` passes
- [ ] Infra contract tests still pass

**Tests**: none  
**Gate**: quick (`pytest tests/unit/test_infra_contract.py -q` after ec2 change)

**Commit**: `feat(infra): wire ec2 user-data for api container`

---

### T13: AWS production env example file

**What**: Add `.env.aws.example` listing AWS-safe settings (`S3_FORCE_PATH_STYLE=false`, unset MinIO endpoints, `SQLITE_PATH=/data/narwal.db`, model URIs).
**Where**: `.env.aws.example`
**Depends on**: T12
**Reuses**: `.env.example`
**Requirement**: DEPLOY-08

**Done when**:

- [ ] File contains no real secrets (placeholders only)
- [ ] README or `infra/README.md` references copying to EC2 as `/etc/narwal/env` (gitignored on server)

**Tests**: none  
**Gate**: build

**Commit**: `docs(config): add aws env example for ec2`

---

### T14: CloudFront HTTPS smoke script

**What**: Shell script curling `/api/health` and `/api/auth/login` via CloudFront base URL; exit non-zero on failure.
**Where**: `scripts/aws/smoke_cloudfront.sh`
**Depends on**: T13
**Reuses**: README smoke test curls
**Requirement**: DEPLOY-03, DEPLOY-11

**Done when**:

- [ ] Accepts `CLOUDFRONT_URL` env var
- [ ] Documents demo credentials source (seed users)

**Tests**: none  
**Gate**: quick

**Commit**: `feat(deploy): add cloudfront smoke script`

---

### T15: Unit tests for deploy scripts

**What**: Pytest that bootstrap and smoke scripts exist, are executable text, and document required env vars (grep-based contract).
**Where**: `tests/unit/test_aws_deploy_scripts.py`
**Depends on**: T14
**Reuses**: T10 patterns
**Requirement**: DEPLOY-03, DEPLOY-11

**Done when**:

- [ ] Quick gate passes
- [ ] Tests cover both script paths under `scripts/aws/`

**Tests**: unit  
**Gate**: quick

**Commit**: `test(deploy): add script contract tests`

---

### T16: Backend CI workflow (test + validate)

**What**: GitHub Actions workflow on push/PR: pytest, ruff, `terraform validate` (no apply).
**Where**: `.github/workflows/ci.yml`
**Depends on**: T15
**Reuses**: README test commands
**Requirement**: DEPLOY-09

**Done when**:

- [ ] Workflow runs on `pull_request` and `push` to default branch
- [ ] Fails if pytest or validate fails

**Tests**: none  
**Gate**: build

**Commit**: `ci: add backend test and terraform validate workflow`

---

### T17: Backend deploy workflow (build and push ECR)

**What**: Workflow job: configure AWS creds from secrets, `docker build`, push to ECR with `github.sha` and `latest` tags.
**Where**: `.github/workflows/deploy-aws.yml`
**Depends on**: T16
**Reuses**: `Dockerfile`
**Requirement**: DEPLOY-09

**Done when**:

- [ ] Uses repository secrets for AWS keys (no plaintext keys in YAML)
- [ ] ECR repository from repo variable matching Terraform output
- [ ] Does not print secrets in logs

**Tests**: none  
**Gate**: build

**Commit**: `ci: add backend ecr push workflow`

---

### T18: Backend deploy SSM restart and health check

**What**: Add deploy job steps: SSM Run Command on EC2 to pull new image and restart container; curl CloudFront `/api/health` expecting 200.
**Where**: `.github/workflows/deploy-aws.yml`
**Depends on**: T17
**Reuses**: T11 bootstrap commands
**Requirement**: DEPLOY-09, DEPLOY-11

**Done when**:

- [ ] Workflow fails if health check fails (covers EC2 stopped case with clear log message)
- [ ] Instance id from repo variable

**Tests**: none  
**Gate**: build

**Commit**: `ci: add ssm deploy and post-deploy health check`

---

### T19: Frontend deploy workflow (S3 sync + invalidation)

**What**: In **narwal-frontend** repo: workflow running `npm test`, `npm run build`, `aws s3 sync`, CloudFront invalidation for `/index.html` and `/assets/*`.
**Where**: `narwal-frontend/.github/workflows/deploy-aws.yml` (sibling repo)
**Depends on**: T18
**Reuses**: Vite `dist/` output; backend docs for bucket/distribution variables
**Requirement**: DEPLOY-10

**Done when**:

- [ ] Secrets/vars documented in frontend deploy doc (T20)
- [ ] Workflow does not echo AWS secrets

**Tests**: unit (vitest in workflow)  
**Gate**: full (`npm test` in CI)

**Commit**: `ci: add frontend s3 and cloudfront deploy workflow` (in narwal-frontend)

---

### T20: Frontend AWS deploy doc

**What**: Short doc linking to backend `docs/aws/` and listing required GitHub variables for UI bucket and distribution id.
**Where**: `narwal-frontend/docs/DEPLOY-AWS.md`
**Depends on**: T19
**Reuses**: `narwal-backend/docs/aws/README.md`
**Requirement**: DEPLOY-10

**Done when**:

- [ ] Cross-repo links are valid relative paths or full GitHub paths
- [ ] States CloudFront same-origin `/api` requirement (no Vite proxy in prod)

**Tests**: none  
**Gate**: build

**Commit**: `docs: add aws deploy guide for frontend` (in narwal-frontend)

---

### T21: Sync backend AWS docs with implemented stack

**What**: Update `docs/aws/architecture.md`, `cost-analysis.md`, and `learner-lab-operations.md` with actual Terraform resource names, output keys, and GHA secret/variable tables.
**Where**: `docs/aws/architecture.md`
**Depends on**: T20
**Reuses**: existing docs from spec P4
**Requirement**: DEPLOY-12, DEPLOY-13, DEPLOY-14, DEPLOY-15

**Done when**:

- [ ] Diagram matches Terraform (ECR, EIP, t3.medium)
- [ ] Cost doc unchanged in assumptions unless instance/storage sizes changed
- [ ] Ops doc lists GHA secrets and `scripts/aws/smoke_cloudfront.sh`

**Tests**: none  
**Gate**: build

**Commit**: `docs(aws): align architecture and ops with infra and ci`

---

### T22: P1 validation checklist and spec traceability update

**What**: Add `docs/aws/validation-checklist.md` with manual P1 steps (browser login + analyze); update spec requirement statuses to Verified when checklist executed in lab.
**Where**: `docs/aws/validation-checklist.md`
**Depends on**: T21
**Reuses**: spec P1 independent test
**Requirement**: DEPLOY-01, DEPLOY-04

**Done when**:

- [ ] Checklist includes presigned image verification on result page
- [ ] Spec traceability table updated for DEPLOY-01–DEPLOY-15 (status Verified or N/A with evidence note)

**Tests**: none  
**Gate**: build

**Commit**: `docs(aws): add p1 validation checklist and traceability`

---

## Phase Execution Map

```
T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9 → T10 → T11 → T12 → T13 → T14 → T15 → T16 → T17 → T18 → T19 → T20 → T21 → T22
```

Execution is strictly sequential within each phase. Phases run in order. **~22 tasks → ~3 batch workers** at Execute time if sub-agents are used.

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1: versions.tf | 1 file | ✅ Granular |
| T2: variables.tf | 1 file + example | ✅ Granular |
| T3: s3.tf | 1 file | ✅ Granular |
| T4: ecr.tf | 1 file | ✅ Granular |
| T5: security_groups.tf | 1 file | ✅ Granular |
| T6: ec2.tf | 1 file | ✅ Granular |
| T7: cloudfront.tf | 1 file | ✅ Granular |
| T8: outputs.tf | 1 file | ✅ Granular |
| T9: infra README | 1 doc | ✅ Granular |
| T10: infra contract tests | 1 test file | ✅ Granular |
| T11–T22 | single deliverable each | ✅ Granular |

---

## Diagram-Definition Cross-Check

Linear chain: each task **Depends on** exactly its predecessor (T1: None). Matches Phase Execution Map arrow chain T1→…→T22.

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | --------------------------- | --------------- | --------- | ------ |
| T1–T9 | Terraform config | none | none | ✅ OK |
| T10 | IaC contract | unit | unit | ✅ OK |
| T11 | Shell script | none (script contract in T15) | none | ✅ OK |
| T12 | ec2.tf | none | unit | ⚠️ T12 modifies TF only; unit gate verifies contract — OK |
| T13 | env example | none | none | ✅ OK |
| T14 | smoke script | none | none | ✅ OK |
| T15 | script contract tests | unit | unit | ✅ OK |
| T16–T18 | GHA YAML | none | none | ✅ OK |
| T19 | frontend workflow | unit in CI | unit | ✅ OK |
| T20–T22 | docs | none | none | ✅ OK |

Note: T12 **Gate: quick** re-runs infra contract tests after ec2.tf change; no separate app layer.

---

## Requirement Traceability (tasks → DEPLOY IDs)

| Task | Requirements |
| ---- | -------------- |
| T1–T2 | DEPLOY-05, DEPLOY-06 |
| T3 | DEPLOY-05, DEPLOY-07 |
| T4 | DEPLOY-05, DEPLOY-09 |
| T5–T6 | DEPLOY-05, DEPLOY-06, DEPLOY-08 |
| T7 | DEPLOY-01, DEPLOY-02 |
| T8 | DEPLOY-07 |
| T9 | DEPLOY-05 |
| T10 | DEPLOY-06 |
| T11–T13 | DEPLOY-08, DEPLOY-09 |
| T14–T15 | DEPLOY-03, DEPLOY-11 |
| T16–T18 | DEPLOY-09, DEPLOY-11 |
| T19–T20 | DEPLOY-10 |
| T21 | DEPLOY-12, DEPLOY-13, DEPLOY-14, DEPLOY-15 |
| T22 | DEPLOY-01, DEPLOY-04 (+ traceability closure) |

**Coverage:** 15 requirements mapped across 22 tasks.

---

## MCPs and Skills (Execute prep)

| Task range | Suggested tools |
| ---------- | --------------- |
| T1–T10 | Skill: `aws-advisor`; Shell for `terraform validate` |
| T11–T15 | Shell; optional `aws-advisor` for presigned URL notes |
| T16–T18 | GitHub Actions; `aws-advisor` for ECR/SSM IAM notes |
| T19–T20 | Frontend repo; same AWS secrets pattern |
| T21–T22 | Docs only; manual Learner Lab apply for P1 checklist |

Confirm tool choices when starting Execute.
