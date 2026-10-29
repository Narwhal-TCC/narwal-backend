output "app_public_url" {
  description = "Public demo URL (HTTP on Elastic IP — Nginx serves UI and proxies /api/*)."
  value       = "http://${aws_eip.api.public_ip}"
}

output "app_bucket_name" {
  description = "S3 bucket for models, analysis objects, and UI deploy prefix ui/ (set S3_BUCKET on API)."
  value       = var.app_bucket_name
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
  description = "EC2 instance ID (console / debugging)."
  value       = aws_instance.api.id
}

output "api_public_ip" {
  description = "Elastic IP associated with the API instance."
  value       = aws_eip.api.public_ip
}

output "api_elastic_ip" {
  description = "Same as api_public_ip (stable public address)."
  value       = aws_eip.api.public_ip
}

output "api_ssh_key_name" {
  description = "EC2 key pair name attached to the API instance."
  value       = aws_key_pair.api.key_name
}

output "api_ssh_command" {
  description = "Example SSH command for Amazon Linux (ec2-user). Use your local private PEM matching ssh_public_key_path."
  value       = "ssh -i \"<path-to-${var.ssh_key_name}.pem>\" ec2-user@${aws_eip.api.public_ip}"
}
