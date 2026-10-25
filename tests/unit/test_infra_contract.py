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
