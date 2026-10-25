output "cloudfront_domain_name" {
  description = "CloudFront distribution domain (HTTPS entry point)."
  value       = aws_cloudfront_distribution.main.domain_name
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (invalidations)."
  value       = aws_cloudfront_distribution.main.id
}

output "ui_bucket_name" {
  description = "S3 bucket for Vite static assets."
  value       = aws_s3_bucket.ui.id
}

output "app_bucket_name" {
  description = "S3 bucket for models and analysis objects (set S3_BUCKET to this value)."
  value       = aws_s3_bucket.app.id
}

output "ecr_repository_url" {
  description = "ECR repository URL for docker push/pull."
  value       = aws_ecr_repository.api.repository_url
}

output "ecr_repository_name" {
  description = "ECR repository name."
  value       = aws_ecr_repository.api.name
}

output "api_instance_id" {
  description = "EC2 instance ID for SSM deploy commands."
  value       = aws_instance.api.id
}

output "api_public_ip" {
  description = "Elastic IP associated with the API instance."
  value       = aws_eip.api.public_ip
}

output "api_elastic_ip" {
  description = "Same as api_public_ip (stable origin for CloudFront)."
  value       = aws_eip.api.public_ip
}
