data "aws_ami" "ubuntu_jammy" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "aws_instance" "api" {
  ami                    = data.aws_ami.ubuntu_jammy.id
  instance_type          = var.instance_type
  availability_zone      = var.availability_zone
  iam_instance_profile   = var.iam_instance_profile
  key_name               = aws_key_pair.api.key_name
  vpc_security_group_ids = [aws_security_group.api.id]
  user_data              = local.api_user_data

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  depends_on = [
    aws_ecr_repository.api,
  ]

  tags = {
    Name = "${var.project_name}-api"
  }
}

locals {
  api_user_data = templatefile("${path.module}/templates/api-user-data.sh.tpl", {
    aws_region         = var.aws_region
    ecr_repository_url = aws_ecr_repository.api.repository_url
    nginx_conf         = file("${path.module}/../scripts/aws/narwal-nginx.conf")
    mount_data_script  = file("${path.module}/../scripts/aws/mount-data-volume.sh")
  })
}

resource "aws_ebs_volume" "data" {
  availability_zone = var.availability_zone
  size              = 20
  type              = "gp3"

  tags = {
    Name = "${var.project_name}-api-data"
  }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.api.id
}

resource "aws_eip" "api" {
  tags = {
    Name = "${var.project_name}-api"
  }
}

resource "aws_eip_association" "api" {
  instance_id   = aws_instance.api.id
  allocation_id = aws_eip.api.id
}
