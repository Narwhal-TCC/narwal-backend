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

**Implementation status:** Spec and docs are in place; Terraform (`infra/`), GitHub Actions, and frontend production routing are **not implemented yet** (next execution phase).

**Locked decisions (2026-10-25):** CloudFront + S3 + EC2, **ECR**, **SQLite on EBS**, initial **t3.medium**, **Elastic IP**, Terraform under `narwal-backend/infra/`.
