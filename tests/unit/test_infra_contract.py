from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA_DIR = REPO_ROOT / "infra"

REQUIRED_TF_FILES = [
    "main.tf",
    "variables.tf",
    "s3.tf",
    "ecr.tf",
    "security_groups.tf",
    "ec2.tf",
    "nginx.tf",
    "outputs.tf",
]


def _infra_text() -> str:
    parts: list[str] = []
    for path in sorted(INFRA_DIR.glob("*.tf")):
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_infra_required_tf_files_exist():
    for name in REQUIRED_TF_FILES:
        assert (INFRA_DIR / name).is_file(), f"missing infra/{name}"


def test_infra_does_not_create_iam_users():
    text = _infra_text()
    assert "aws_iam_user" not in text


def test_infra_does_not_create_cloudfront():
    text = _infra_text()
    assert "aws_cloudfront" not in text


def test_infra_does_not_manage_s3_bucket_resource():
    """Academy SCP denies GetBucketObjectLockConfiguration on LabRole after TF bucket create."""
    s3_tf = (INFRA_DIR / "s3.tf").read_text(encoding="utf-8")
    assert 'resource "aws_s3_bucket"' not in s3_tf
    assert "var.app_bucket_name" in (INFRA_DIR / "outputs.tf").read_text(encoding="utf-8")


def test_ec2_uses_lab_instance_profile_variable():
    ec2_tf = (INFRA_DIR / "ec2.tf").read_text(encoding="utf-8")
    assert "iam_instance_profile" in ec2_tf
    assert "var.iam_instance_profile" in ec2_tf
    assert 'default     = "LabInstanceProfile"' in (INFRA_DIR / "variables.tf").read_text(
        encoding="utf-8"
    )


def test_nginx_proxies_api_and_serves_spa():
    nginx_conf = (REPO_ROOT / "scripts/aws/narwal-nginx.conf").read_text(encoding="utf-8")
    ec2_tf = (INFRA_DIR / "ec2.tf").read_text(encoding="utf-8")
    assert 'location /api/' in nginx_conf
    assert "proxy_pass http://127.0.0.1:8080/;" in nginx_conf
    assert "try_files" in nginx_conf
    assert "/index.html" in nginx_conf
    user_data_tpl = (INFRA_DIR / "templates/api-user-data.sh.tpl").read_text(encoding="utf-8")
    assert "127.0.0.1:8080:8080" in user_data_tpl
    assert "narwal-nginx.conf" in ec2_tf


def test_security_group_exposes_http_not_public_api_port():
    sg_tf = (INFRA_DIR / "security_groups.tf").read_text(encoding="utf-8")
    assert "from_port   = 80" in sg_tf
    assert "8080" not in sg_tf


REQUIRED_OUTPUTS = [
    "app_public_url",
    "app_bucket_name",
    "ecr_repository_url",
    "ecr_repository_name",
    "api_instance_id",
    "api_public_ip",
    "api_elastic_ip",
]


def test_terraform_outputs_export_deploy_values():
    outputs_tf = (INFRA_DIR / "outputs.tf").read_text(encoding="utf-8")
    for name in REQUIRED_OUTPUTS:
        assert f'output "{name}"' in outputs_tf


def test_api_instance_type_defaults_to_t3_medium():
    variables_tf = (INFRA_DIR / "variables.tf").read_text(encoding="utf-8")
    assert 'default     = "t3.medium"' in variables_tf


def test_ec2_uses_ubuntu_jammy_ami_data_source():
    ec2_tf = (INFRA_DIR / "ec2.tf").read_text(encoding="utf-8")
    assert 'data "aws_ami" "ubuntu_jammy"' in ec2_tf
    assert "ubuntu-jammy-22.04-amd64" in ec2_tf


def test_data_ebs_pinned_to_availability_zone():
    ec2_tf = (INFRA_DIR / "ec2.tf").read_text(encoding="utf-8")
    variables_tf = (INFRA_DIR / "variables.tf").read_text(encoding="utf-8")
    assert "availability_zone      = var.availability_zone" in ec2_tf
    assert "availability_zone = var.availability_zone" in ec2_tf
    assert "variable \"availability_zone\"" in variables_tf


def test_aws_env_example_sqlite_on_data_volume():
    env_aws = (REPO_ROOT / ".env.aws.example").read_text(encoding="utf-8")
    assert "SQLITE_PATH=/data/narwal.db" in env_aws
    assert "S3_FORCE_PATH_STYLE=false" in env_aws
