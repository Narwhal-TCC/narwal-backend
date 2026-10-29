# Push current Learner Lab AWS credentials to Narwhal-TCC organization secrets.
# Requires: gh CLI (admin:org), AWS credentials in environment or aws configure profile.
# Usage: .\scripts\aws\sync-lab-secrets-to-github-org.ps1 [-Org Narwhal-TCC] [-StateBucket narwal-bucket-20261025]

param(
    [string]$Org = "Narwhal-TCC",
    [string]$StateBucket = "narwal-bucket-20261025"
)

$ErrorActionPreference = "Stop"

function Get-AwsCredentialValue {
    param([string]$Name)
    $envVal = (Get-Item -Path "Env:$Name" -ErrorAction SilentlyContinue).Value
    if ($envVal) { return $envVal }
    $ini = Join-Path $env:USERPROFILE ".aws\credentials"
    if (-not (Test-Path $ini)) {
        throw "Set Env:$Name or configure AWS CLI ($ini)."
    }
    $content = Get-Content $ini -Raw
    $profile = if ($env:AWS_PROFILE) { $env:AWS_PROFILE } else { "default" }
    if ($content -match "(?ms)\[$([regex]::Escape($profile))\].*?${Name}\s*=\s*(\S+)") {
        return $Matches[1]
    }
    if ($content -match "${Name}\s*=\s*(\S+)") {
        return $Matches[1]
    }
    throw "Could not read $Name from environment or credentials file."
}

$accessKey = Get-AwsCredentialValue -Name "AWS_ACCESS_KEY_ID"
$secretKey = Get-AwsCredentialValue -Name "AWS_SECRET_ACCESS_KEY"
$sessionToken = Get-AwsCredentialValue -Name "AWS_SESSION_TOKEN"

Write-Host "Setting organization secrets on $Org (repos must allow org secret access)..."
gh secret set AWS_ACCESS_KEY_ID     -o $Org -b $accessKey
gh secret set AWS_SECRET_ACCESS_KEY -o $Org -b $secretKey
gh secret set AWS_SESSION_TOKEN     -o $Org -b $sessionToken
gh secret set APP_BUCKET_NAME       -o $Org -b $StateBucket
gh secret set STATE_BUCKET_NAME     -o $Org -b $StateBucket
Write-Host "Done. Remove duplicate repo-level AWS secrets if present to avoid confusion."
