<#
.SYNOPSIS
    Generates a secure .env file from .env.example with cryptographically strong secrets.

.DESCRIPTION
    Copies .env.example to .env and generates 256-bit base64url random values for:
    - POSTGRES_PASSWORD (and synchronizes DATABASE_URL)
    - JWT_SECRET_KEY
    - GRAFANA_ADMIN_PASSWORD
    - ADMIN_PASSWORD
    Refuses to overwrite an existing .env unless -Force is specified.
    Never prints generated secrets to console or logs.
#>
[CmdletBinding()]
param(
    [switch]$Force,
    [string]$EnvPath = ".env",
    [string]$ExamplePath = ".env.example"
)

$targetPath = [System.IO.Path]::GetFullPath($EnvPath)
$sourcePath = [System.IO.Path]::GetFullPath($ExamplePath)

if ((Test-Path $targetPath) -and -not $Force) {
    Write-Error "File $targetPath already exists. Pass -Force to overwrite."
    exit 1
}

if (-not (Test-Path $sourcePath)) {
    Write-Error "Template file $sourcePath does not exist."
    exit 1
}

function Generate-SecureSecret {
    param([int]$bytes = 32)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $data = New-Object byte[] $bytes
    $rng.GetBytes($data)
    return [Convert]::ToBase64String($data).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$content = [System.IO.File]::ReadAllText($sourcePath)

$secretVars = @(
    "POSTGRES_PASSWORD",
    "JWT_SECRET_KEY",
    "GRAFANA_ADMIN_PASSWORD",
    "ADMIN_PASSWORD",
    "AIRFLOW_DB_PASSWORD",
    "AIRFLOW_ADMIN_PASSWORD"
)

$updatedContent = $content
$setVars = [System.Collections.Generic.List[string]]::new()

foreach ($var in $secretVars) {
    $secret = Generate-SecureSecret -bytes 32
    # Replace either an active placeholder or the intentionally commented
    # template entry.  The generated .env must contain the required variable.
    $pattern = "(?m)^#?\s*$var=.*$"
    if ($updatedContent -match $pattern) {
        $updatedContent = [System.Text.RegularExpressions.Regex]::Replace($updatedContent, $pattern, "$var=$secret")
        $setVars.Add($var)
    }
}

# Fernet keys are URL-safe base64 for exactly 32 random bytes and retain the
# padding required by the Fernet specification.
$fernetRng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$fernetBytes = New-Object byte[] 32
$fernetRng.GetBytes($fernetBytes)
$fernetKey = [Convert]::ToBase64String($fernetBytes)
$fernetPattern = "(?m)^#?\s*AIRFLOW_FERNET_KEY=.*$"
$updatedContent = [System.Text.RegularExpressions.Regex]::Replace(
    $updatedContent, $fernetPattern, "AIRFLOW_FERNET_KEY=$fernetKey"
)
$setVars.Add("AIRFLOW_FERNET_KEY")

# These are non-secret Airflow bootstrap settings.  Uncomment them in the
# generated file so the manual E2E workflow can fail closed and initialize.
$bootstrapDefaults = @{
    "AIRFLOW_ADMIN_USERNAME" = "admin"
    "AIRFLOW_ADMIN_EMAIL" = "admin@example.com"
}
foreach ($entry in $bootstrapDefaults.GetEnumerator()) {
    $pattern = "(?m)^#?\s*$($entry.Key)=.*$"
    $updatedContent = [System.Text.RegularExpressions.Regex]::Replace(
        $updatedContent, $pattern, "$($entry.Key)=$($entry.Value)"
    )
}

# Synchronize DATABASE_URL password
$pgPassMatch = [regex]::Match($updatedContent, "(?m)^POSTGRES_PASSWORD=(.*)$")
if ($pgPassMatch.Success) {
    $pgPass = $pgPassMatch.Groups[1].Value
    $updatedContent = [System.Text.RegularExpressions.Regex]::Replace(
        $updatedContent,
        '(?m)^DATABASE_URL=postgresql\+asyncpg://platform_user:[^@]+@postgres:5432/platform_db',
        "DATABASE_URL=postgresql+asyncpg://platform_user:$pgPass@postgres:5432/platform_db"
    )
    $setVars.Add("DATABASE_URL")
}

[System.IO.File]::WriteAllText($targetPath, $updatedContent, [System.Text.Encoding]::UTF8)

Write-Host "Successfully generated $EnvPath from $ExamplePath."
Write-Host "Configured secure secrets for:"
foreach ($v in $setVars) {
    Write-Host "  - $v"
}
