# migrate_healthcheck_secret.ps1
# Move the backup Healthchecks bearer URL from readable machine environment
# storage into a DPAPI CurrentUser blob under the already-private Garmin data
# root.  Never prints the URL or its path component.

[CmdletBinding()]
param(
    [switch]$RemoveMachineValue
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security

$name = 'HEALTHCHECK_BACKUP_URL'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dataRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot 'garmin\data'))
$target = [IO.Path]::GetFullPath((Join-Path $dataRoot '.healthcheck-backup-url.dpapi'))
if ([IO.Path]::GetDirectoryName($target) -ne $dataRoot) {
    throw 'Secret target escaped the private Garmin data root'
}

function Test-SafeHealthcheckUri {
    param([Parameter(Mandatory = $true)][string]$Value)
    $uri = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri)) { return $false }
    return $uri.Scheme -eq 'https' -and
           -not [string]::IsNullOrWhiteSpace($uri.Host) -and
           [string]::IsNullOrEmpty($uri.UserInfo) -and
           [string]::IsNullOrEmpty($uri.Query) -and
           [string]::IsNullOrEmpty($uri.Fragment) -and
           ($uri.IsDefaultPort -or $uri.Port -eq 443)
}

$machineValue = [Environment]::GetEnvironmentVariable($name, 'Machine')
$protectedValue = $null
$created = $false

if (Test-Path -LiteralPath $target -PathType Leaf) {
    $ciphertext = [IO.File]::ReadAllBytes($target)
    $plaintext = [Security.Cryptography.ProtectedData]::Unprotect(
        $ciphertext, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    try {
        $protectedValue = [Text.Encoding]::UTF8.GetString($plaintext)
    }
    finally {
        [Array]::Clear($plaintext, 0, $plaintext.Length)
    }
}
else {
    if ([string]::IsNullOrWhiteSpace($machineValue)) {
        throw 'Machine Healthchecks value is missing; nothing can be migrated'
    }
    if (-not (Test-SafeHealthcheckUri -Value $machineValue)) {
        throw 'Machine Healthchecks value failed HTTPS safety validation'
    }
    if (-not (Test-Path -LiteralPath $dataRoot -PathType Container)) {
        throw 'Private Garmin data root is missing'
    }

    $raw = [Text.Encoding]::UTF8.GetBytes($machineValue)
    $temp = $target + '.tmp-' + $PID
    try {
        $ciphertext = [Security.Cryptography.ProtectedData]::Protect(
            $raw, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        [IO.File]::WriteAllBytes($temp, $ciphertext)
        [IO.File]::Move($temp, $target)
        $protectedValue = $machineValue
        $created = $true
    }
    finally {
        [Array]::Clear($raw, 0, $raw.Length)
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
    }
}

if (-not (Test-SafeHealthcheckUri -Value $protectedValue)) {
    throw 'DPAPI-protected Healthchecks value failed HTTPS safety validation'
}
if (-not [string]::IsNullOrWhiteSpace($machineValue) -and
        $machineValue -ne $protectedValue) {
    throw 'Machine and DPAPI Healthchecks values conflict; refusing to delete either'
}

$removed = [string]::IsNullOrWhiteSpace($machineValue)
$requiresAdmin = $false
if ($RemoveMachineValue -and -not $removed) {
    try {
        [Environment]::SetEnvironmentVariable($name, $null, 'Machine')
        $removed = [string]::IsNullOrWhiteSpace(
            [Environment]::GetEnvironmentVariable($name, 'Machine')
        )
        if (-not $removed) { throw 'Machine value still exists after deletion request' }
    }
    catch [System.Security.SecurityException], [System.UnauthorizedAccessException] {
        $requiresAdmin = $true
    }
}

$result = [ordered]@{
    ok                     = (-not $RemoveMachineValue -or $removed)
    protected_file         = (Test-Path -LiteralPath $target -PathType Leaf)
    protected_file_created = $created
    https_validated        = $true
    machine_value_removed  = $removed
    removal_requires_admin = $requiresAdmin
}
$result | ConvertTo-Json -Compress
if ($result.ok) { exit 0 }
exit 3
