resource "aws_security_group" "api" {
  name        = "${var.project_name}-api"
  description = "Narwal edge (Nginx :80; API bound to localhost only)"

  ingress {
    description = "HTTP for Nginx (UI + /api proxy)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH admin access"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.ssh_allowed_cidr_blocks
  }

  egress {
    description = "All outbound (DNS, NTP, ECR, S3, apt)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
