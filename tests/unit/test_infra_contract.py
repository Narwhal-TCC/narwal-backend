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
    "cloudfront.tf",
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


def test_ec2_uses_lab_instance_profile_variable():
    ec2_tf = (INFRA_DIR / "ec2.tf").read_text(encoding="utf-8")
    assert "iam_instance_profile" in ec2_tf
    assert "var.iam_instance_profile" in ec2_tf
    assert 'default     = "LabInstanceProfile"' in (INFRA_DIR / "variables.tf").read_text(
        encoding="utf-8"
    )


def test_cloudfront_routes_api_and_default_ui():
    cf_tf = (INFRA_DIR / "cloudfront.tf").read_text(encoding="utf-8")
    assert 'path_pattern     = "/api/*"' in cf_tf
    assert 'target_origin_id = "ec2-api"' in cf_tf
    assert 'target_origin_id = "s3-ui"' in cf_tf
    assert '"Authorization"' in cf_tf


REQUIRED_OUTPUTS = [
    "cloudfront_domain_name",
    "cloudfront_distribution_id",
    "ui_bucket_name",
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


def test_aws_env_example_sqlite_on_data_volume():
    env_aws = (REPO_ROOT / ".env.aws.example").read_text(encoding="utf-8")
    assert "SQLITE_PATH=/data/narwal.db" in env_aws
    assert "S3_FORCE_PATH_STYLE=false" in env_aws
