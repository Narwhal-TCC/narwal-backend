# Narwal Terraform (AWS Academy Learner Lab)

Infrastructure for CloudFront + S3 UI + EC2 API + ECR in **us-east-1**. Uses the lab-provided **`LabInstanceProfile`** on EC2 — **do not** create `aws_iam_user` or instance IAM roles in this stack.

See also: [Learner Lab operations](../docs/aws/learner-lab-operations.md).

## Prerequisites

1. **Start Lab** in AWS Academy and configure AWS credentials (session keys).
2. Install [Terraform](https://developer.hashicorp.com/terraform/install) `>= 1.5`.
3. Copy `terraform.tfvars.example` → `terraform.tfvars` (gitignored). Set a **globally unique** `app_bucket_name` (this value becomes `S3_BUCKET` on the API container).

## Commands

```bash
cd infra
terraform init
terraform plan
terraform apply
terraform destroy   # when tearing down lab resources
```

After apply, note outputs: `cloudfront_domain_name`, `ui_bucket_name`, `app_bucket_name`, `ecr_repository_url`, `api_instance_id`, `api_elastic_ip`.

## Post-apply

1. Upload model weights to the app bucket (`aws s3 sync` — see ops doc).
2. Copy [`.env.aws.example`](../.env.aws.example) to the instance as `/etc/narwal/env` (gitignored on the server) and fill placeholders.
3. Ensure the data volume is mounted at `/data` and run the API container (user-data runs bootstrap on first boot; see `scripts/aws/ec2-api-bootstrap.sh`).
4. Sync frontend `dist/` to the UI bucket and invalidate CloudFront (CI in later tasks).
5. Run HTTPS smoke checks: `scripts/aws/smoke_cloudfront.sh` (added in deploy phase).

## IAM notes

- EC2 `iam_instance_profile` defaults to **`LabInstanceProfile`** (variable `iam_instance_profile`).
- S3 access from the container relies on the instance profile, not static `AWS_ACCESS_KEY_ID` in the env file.
