resource "aws_key_pair" "api" {
  key_name   = var.ssh_key_name
  public_key = file("${path.module}/${var.ssh_public_key_path}")

  tags = {
    Name = "${var.project_name}-api-ssh"
  }
}
