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
  api_user_data = <<-EOF
    #!/bin/bash
    set -euo pipefail
    exec > /var/log/narwal-user-data.log 2>&1

    dnf install -y docker nginx aws-cli
    systemctl enable --now docker

    mkdir -p /var/www/narwal
    chown -R nginx:nginx /var/www/narwal

    cat > /etc/nginx/conf.d/narwal.conf <<'NGINX'
    server {
        listen 80 default_server;
        listen [::]:80 default_server;
        server_name _;
        root /var/www/narwal;
        index index.html;

        location /api/ {
            proxy_pass http://127.0.0.1:8080;
            proxy_http_version 1.1;
            proxy_set_header Host $$host;
            proxy_set_header X-Real-IP $$remote_addr;
            proxy_set_header X-Forwarded-For $$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $$scheme;
        }

        location / {
            try_files $$uri $$uri/ /index.html;
        }
    }
    NGINX

    systemctl enable --now nginx

    if ! mountpoint -q /data; then
      if ! blkid /dev/xvdf; then
        mkfs -t xfs /dev/xvdf
      fi
      mkdir -p /data
      echo '/dev/xvdf /data xfs defaults,nofail 0 2' >> /etc/fstab
      mount -a
      chown 1001:1001 /data
    fi

    export AWS_REGION="${var.aws_region}"
    export ECR_REPOSITORY_URL="${aws_ecr_repository.api.repository_url}"
    export IMAGE_TAG="latest"
    export NARWAL_ENV_FILE="/etc/narwal/env"

    ECR_REGISTRY="$${ECR_REPOSITORY_URL%%/*}"
    aws ecr get-login-password --region "$${AWS_REGION}" | docker login --username AWS --password-stdin "$${ECR_REGISTRY}"

    IMAGE="$${ECR_REPOSITORY_URL}:$${IMAGE_TAG}"
    docker pull "$${IMAGE}" || true

    if docker ps -a --format '{{.Names}}' | grep -qx narwal-api; then
      docker stop narwal-api || true
      docker rm narwal-api || true
    fi

    ENV_ARGS=()
    if [[ -f "$${NARWAL_ENV_FILE}" ]]; then
      ENV_ARGS=(--env-file "$${NARWAL_ENV_FILE}")
    fi

    docker run -d --name narwal-api --restart unless-stopped \
      -p 127.0.0.1:8080:8080 \
      -v /data:/data \
      "$${ENV_ARGS[@]}" \
      "$${IMAGE}" || echo "Container start deferred until $${NARWAL_ENV_FILE} exists"
  EOF
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
  tags = {
    Name = "${var.project_name}-api"
  }
}

resource "aws_eip_association" "api" {
  instance_id   = aws_instance.api.id
  allocation_id = aws_eip.api.id
}
