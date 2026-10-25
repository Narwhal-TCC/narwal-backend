data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_instance" "api" {
  ami                    = data.aws_ami.amazon_linux_2023.id
  instance_type          = var.instance_type
  iam_instance_profile   = var.iam_instance_profile
  vpc_security_group_ids = [aws_security_group.api.id]

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  depends_on = [
    aws_s3_bucket.app,
    aws_ecr_repository.api,
  ]

  tags = {
    Name = "${var.project_name}-api"
  }
}

resource "aws_ebs_volume" "data" {
  availability_zone = aws_instance.api.availability_zone
  size              = 20
  type              = "gp3"

  tags = {
    Name = "${var.project_name}-api-data"
  }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/xvdf"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.api.id
}

resource "aws_eip" "api" {
  domain = "vpc"

  tags = {
    Name = "${var.project_name}-api"
  }
}

resource "aws_eip_association" "api" {
  instance_id   = aws_instance.api.id
  allocation_id = aws_eip.api.id
}
