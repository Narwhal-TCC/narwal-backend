resource "aws_security_group" "api" {
  name        = "${var.project_name}-api"
  description = "Narwal API instance (Docker on 8080)"

  # MVP Learner Lab: open 8080 for CloudFront custom origin (restrict to CloudFront prefix list when lab allows).
  ingress {
    description = "HTTP API from CloudFront custom origin (MVP: 0.0.0.0/0 in lab account)"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "HTTPS for ECR, S3, and package mirrors"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "HTTP fallback for package mirrors"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
