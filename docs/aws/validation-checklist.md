# P1 validation checklist (Learner Lab)

Manual sign-off for **public HTTPS demo** (spec P1). Execute with the API EC2 instance **running**, models synced to the app S3 bucket, and `/etc/narwal/env` configured on the instance.

**Prerequisites:** [learner-lab-operations.md](./learner-lab-operations.md) — Start Lab, start EC2, note `cloudfront_domain_name`.

| Step | Action | Pass? | Notes |
| ---- | ------ | ----- | ----- |
| 1 | `export CLOUDFRONT_URL=https://<cloudfront_domain>` and run `./scripts/aws/smoke_cloudfront.sh` | ☐ | Health + login JSON |
| 2 | Open `CLOUDFRONT_URL` in a browser — UI loads over **HTTPS**, no mixed-content console errors | ☐ | |
| 3 | Log in as seeded **demo** user (or configured admin) | ☐ | JWT stored; redirect to app shell |
| 4 | Start **new analysis**, upload a valid PNG/JPEG (≤ 10 MB) | ☐ | HTTP 200 or documented 4xx/503, not CloudFront 502 |
| 5 | On **result** page, confirm detection overlay / metrics render | ☐ | |
| 6 | **Presigned image:** open DevTools → Network; confirm the result image request returns **200** and displays (not broken icon / CORS / wrong host) | ☐ | If fail, fix `S3_PUBLIC_ENDPOINT` per ops doc |
| 7 | Optional: stop EC2, reload UI — static shell still HTTPS; `/api/health` non-2xx until instance started | ☐ | DEPLOY-01 edge case |

**Recorded by:** _______________ **Date:** _______________ **CloudFront domain:** _______________

**Evidence for spec:** When all required rows (1–6) pass, mark DEPLOY-01–DEPLOY-04 **Verified** in `.specs/features/aws-academy-deploy/spec.md` with this date and domain in the evidence note.

## Related automated checks

| Check | Location |
| ----- | -------- |
| Terraform layout / no IAM users | `tests/unit/test_infra_contract.py` |
| Deploy scripts contract | `tests/unit/test_aws_deploy_scripts.py` |
| Backend CI | `.github/workflows/ci.yml` |
| Backend deploy + `/api/health` | `.github/workflows/deploy-aws.yml` |
| Frontend test + S3 sync | `narwal-frontend/.github/workflows/deploy-aws.yml` |
