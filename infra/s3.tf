# App data bucket is NOT managed by Terraform: Vocareum SCP denies
# s3:GetBucketObjectLockConfiguration (and related reads) on LabRole, which breaks
# aws_s3_bucket refresh after create. Create the bucket once with:
#   scripts/aws/create-app-bucket.sh
# or: aws s3 mb s3://YOUR_UNIQUE_NAME --region us-east-1
# Set the same name in terraform.tfvars as app_bucket_name.

data "aws_caller_identity" "current" {}
