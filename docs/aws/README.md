# AWS deployment documentation (Narwal)

Documentation for deploying Narwal to **AWS Academy Learner Lab**, aligned with the feature spec:

**Spec:** [`.specs/features/aws-academy-deploy/spec.md`](../../.specs/features/aws-academy-deploy/spec.md)  
**Design:** [`.specs/features/aws-academy-deploy/design.md`](../../.specs/features/aws-academy-deploy/design.md)  
**Tasks:** [`.specs/features/aws-academy-deploy/tasks.md`](../../.specs/features/aws-academy-deploy/tasks.md) (22 tasks, T1–T22)

| Document | Audience | Contents |
| -------- | -------- | -------- |
| [architecture.md](./architecture.md) | TCC report, reviewers | Topology, components, security notes |
| [cost-analysis.md](./cost-analysis.md) | TCC report, budget | Monthly scenarios, EC2 hours vs 24/7 |
| [learner-lab-operations.md](./learner-lab-operations.md) | Developers | Start Lab, smoke tests, ECR, sizing |
| [validation-checklist.md](./validation-checklist.md) | **Start here** | Full deploy checklist: prerequisites, Terraform, EC2, S3 models, CI, smoke commands, P1 browser sign-off |

**Implementation status:** Terraform (`infra/`), backend and frontend GitHub Actions deploy workflows, and AWS docs are **implemented** on `master`. Complete P1 sign-off in Learner Lab using [validation-checklist.md](./validation-checklist.md).

**Locked decisions (2026-10-25, updated):** **EC2 Nginx single origin** (HTTP on Elastic IP — CloudFront blocked by LabRole), S3 app bucket, **ECR**, **SQLite on EBS**, **t3.medium**, **Elastic IP**, Terraform under `narwal-backend/infra/`.
