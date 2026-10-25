resource "tls_private_key" "api_ssh" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "api" {
  key_name   = "${var.project_name}-api"
  public_key = tls_private_key.api_ssh.public_key_openssh

  tags = {
    Name = "${var.project_name}-api-ssh"
  }
}

resource "local_sensitive_file" "api_ssh_private_key" {
  content         = tls_private_key.api_ssh.private_key_pem
  filename        = "${path.module}/keys/${var.project_name}-api.pem"
  file_permission = "0400"
}
