# Narwal Terraform (AWS Academy Learner Lab)

Infrastructure for **Nginx + EC2 (UI + API) + S3 app bucket + ECR** in **us-east-1**. Uses **`LabInstanceProfile`** on EC2 — **do not** create `aws_iam_user` or custom IAM roles.

CloudFront is intentionally omitted (LabRole denies `cloudfront:*` in Vocareum).

See [Learner Lab operations](../docs/aws/learner-lab-operations.md).

## Prerequisites

1. **Start Lab** in AWS Academy and configure session credentials.
2. Terraform `>= 1.5`.
3. Copy `terraform.tfvars.example` → `terraform.tfvars`. Set a **globally unique** `app_bucket_name` (becomes `S3_BUCKET` on the API).
4. **Create the S3 bucket before `terraform apply`** (Terraform does not manage the bucket — Vocareum SCP blocks post-create S3 reads):

```bash
export APP_BUCKET_NAME="same-as-terraform.tfvars"
export AWS_REGION=us-east-1
bash scripts/aws/create-app-bucket.sh
```

## Commands

```bash
cd infra
terraform init
terraform plan
terraform apply
terraform destroy
```

After apply, note outputs: `app_public_url`, `app_bucket_name`, `ecr_repository_url`, `api_instance_id`, `api_elastic_ip`.

**SSH (optional):** `terraform apply` generates `infra/keys/<project_name>-api.pem` and registers the matching EC2 key pair. Connect with `terraform output -raw api_ssh_command`. Adding a key to an existing instance **replaces** the EC2 resource; the separate EBS `/data` volume is reattached. Prefer Session Manager if you already configured `/etc/narwal/env` and want zero downtime.

## S3 bucket (outside Terraform)

Learner Lab SCP **explicitly denies** `s3:GetBucketObjectLockConfiguration` on student roles, so `aws_s3_bucket` in Terraform fails after create. The bucket is created with **`scripts/aws/create-app-bucket.sh`** (or `aws s3 mb`); Terraform only passes `app_bucket_name` through outputs and docs.

## Post-apply

1. Upload model weights to the app bucket (`aws s3 sync` — ops doc).
2. Copy [`.env.aws.example`](../.env.aws.example) to the instance as `/etc/narwal/env` and fill secrets.
3. Bootstrap API: user-data on first boot; or `scripts/aws/ec2-api-bootstrap.sh` on the instance.
4. Deploy UI: frontend GitHub Actions or manual `s3 sync` to `s3://<app_bucket>/ui/` + SSM sync to `/var/www/narwal` (checklist §5).
5. Smoke: `APP_PUBLIC_URL=$(terraform output -raw app_public_url) ./scripts/aws/smoke_app.sh`.

## IAM notes

- EC2 `iam_instance_profile` defaults to **`LabInstanceProfile`**.
- S3/ECR from the container use the instance profile, not static keys in the env file.
