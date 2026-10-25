#!/usr/bin/env bash
# Create the Narwal app S3 bucket outside Terraform (Academy SCP blocks TF bucket reads).
#
# Usage:
#   export APP_BUCKET_NAME="your-globally-unique-name"
#   export AWS_REGION="${AWS_REGION:-us-east-1}"
#   ./scripts/aws/create-app-bucket.sh
#
# Requires: AWS CLI with Learner Lab credentials (session token if applicable).

set -euo pipefail

APP_BUCKET_NAME="${APP_BUCKET_NAME:-${1:-}}"
AWS_REGION="${AWS_REGION:-us-east-1}"

if [[ -z "${APP_BUCKET_NAME}" ]]; then
  echo "APP_BUCKET_NAME is required (same value as infra/terraform.tfvars app_bucket_name)." >&2
  exit 1
fi

echo "Creating s3://${APP_BUCKET_NAME} in ${AWS_REGION} ..."
if aws s3api head-bucket --bucket "${APP_BUCKET_NAME}" 2>/dev/null; then
  echo "Bucket already exists."
else
  if [[ "${AWS_REGION}" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "${APP_BUCKET_NAME}"
  else
    aws s3api create-bucket --bucket "${APP_BUCKET_NAME}" \
      --create-bucket-configuration "LocationConstraint=${AWS_REGION}"
  fi
  echo "Bucket created."
fi

echo "Applying default encryption (AES256) ..."
aws s3api put-bucket-encryption --bucket "${APP_BUCKET_NAME}" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

echo "Blocking public access ..."
aws s3api put-public-access-block --bucket "${APP_BUCKET_NAME}" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "Done. Use app_bucket_name = \"${APP_BUCKET_NAME}\" in terraform.tfvars."
