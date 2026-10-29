terraform {
  required_version = ">= 1.5.0"

  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      # 4.x avoids post-create S3 Object Lock reads blocked by Academy SCP on LabRole.
      version = "~> 4.67"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.tags
  }
}
