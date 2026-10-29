variable "aws_region" {
  description = "AWS region for Learner Lab (default us-east-1)."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short project prefix for resource names (lowercase, no spaces)."
  type        = string
  default     = "narwal"
}

variable "instance_type" {
  description = "EC2 instance type for the API host."
  type        = string
  default     = "t3.medium"
}

variable "iam_instance_profile" {
  description = "Existing Learner Lab instance profile name (do not create IAM roles in TF)."
  type        = string
  default     = "LabInstanceProfile"
}

variable "app_bucket_name" {
  description = "Globally unique S3 bucket for app data/models (set S3_BUCKET env to this value on EC2)."
  type        = string
}

variable "ssh_allowed_cidr_blocks" {
  description = "CIDR blocks allowed to SSH to the API instance (port 22). Restrict to your public IP when possible."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "ssh_key_name" {
  description = "Existing EC2 key pair name in AWS (public key registered via ssh_public_key_path)."
  type        = string
  default     = "narwhal-dev-keypair"
}

variable "ssh_public_key_path" {
  description = "Path to OpenSSH public key file relative to infra/ (committed .pub; private PEM stays local)."
  type        = string
  default     = "keys/narwhal-dev-keypair.pub"
}

variable "tags" {
  description = "Default tags applied to supported resources."
  type        = map(string)
  default = {
    Project = "narwal"
    Managed = "terraform"
  }
}
