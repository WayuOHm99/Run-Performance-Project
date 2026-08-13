[CmdletBinding()]
param(
    [switch]$Plan,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$garmin = Join-Path $root 'garmin'
$data = Join-Path $garmin 'data'
$secretPath = Join-Path $data 'restic_repository_password.dpapi'
$repository = 'C:\Backup\run-performance-restic'
$githubSecretName = 'RESTIC_REPOSITORY_PASSWORD'
$scheduledTasks = @(
    'Run-Performance-OffsiteBackup',
    'Run-Performance-RestoreDrill',
    'Run-Performance-SystemHealth'
)

$planPayload = [ordered]@{
    repository = $repository
    sources = @('C:\Backup\garmin-db-daily', 'C:\Backup\Run-Performance')
    local_secret_storage = 'DPAPI CurrentUser'
    recovery_secret_storage = 'GitHub Actions secret'
    recovery_secret_name = $githubSecretName
    plaintext_secret_file = $false
    initial_proof = 'backup + restore-drill when no successful proof exists'
    scheduled_tasks = $scheduledTasks
}
if ($Plan) {
    if ($Json) { $planPayload | ConvertTo-Json -Compress } else { $planPayload | Format-List }
    exit 0
}

function Resolve-ResticExecutable {
    $command = Get-Command restic -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $packageRoot = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    $candidate = Get-ChildItem $packageRoot -Recurse -File -Filter 'restic*_windows_amd64.exe' -ErrorAction SilentlyContinue |
        Sort-Object FullName | Select-Object -Last 1
    if ($candidate) { return $candidate.FullName }
    throw 'ไม่พบ restic.exe — ติดตั้งด้วย winget install --id restic.restic -e'
}

function Resolve-GitHubRepository([string]$Gh, [string]$Root) {
    Push-Location $Root
    try {
        $name = & $Gh repo view --json nameWithOwner --jq '.nameWithOwner'
        $code = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    if ($code -ne 0 -or $name -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') {
        throw 'ระบุ GitHub repository จาก git remote ไม่สำเร็จ'
    }
    return $name.Trim()
}

function Set-GitHubSecretFromMemory(
    [string]$Gh,
    [string]$Repository,
    [string]$Name,
    [string]$Value,
    [string]$WorkingDirectory
) {
    # ส่งผ่าน stdin แบบไม่มี newline และไม่วาง secret ใน command line/process list
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $Gh
    $start.Arguments = "secret set $Name --repo $Repository"
    $start.WorkingDirectory = $WorkingDirectory
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw 'เปิด GitHub CLI ไม่สำเร็จ' }
        $process.StandardInput.Write($Value)
        $process.StandardInput.Close()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            $detail = if ($stderr) { $stderr.Trim() } else { $stdout.Trim() }
            throw "บันทึก recovery secret ใน GitHub Actions ไม่สำเร็จ: $detail"
        }
    }
    finally {
        $process.Dispose()
    }
}

function Test-SuccessfulProof([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    try {
        $document = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        return ($document.ok -eq $true)
    }
    catch {
        return $false
    }
}

function Invoke-OffsiteWorker([string]$Python, [string]$Worker, [string]$Command) {
    $output = & $Python $Worker $Command --json
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        throw "พิสูจน์ $Command ไม่สำเร็จ: $($output | Select-Object -Last 1)"
    }
    try {
        $payload = $output | Select-Object -Last 1 | ConvertFrom-Json
    }
    catch {
        throw "พิสูจน์ $Command คืนผลที่อ่านไม่ได้"
    }
    if ($payload.ok -ne $true) {
        throw "พิสูจน์ $Command รายงานล้มเหลว"
    }
}

function Protect-CurrentUserSecret([string]$Value, [string]$Path) {
    Add-Type -AssemblyName System.Security
    $raw = [Text.Encoding]::UTF8.GetBytes($Value)
    try {
        $blob = [Security.Cryptography.ProtectedData]::Protect(
            $raw, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        $directory = Split-Path -Parent $Path
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
        $temporary = "$Path.tmp"
        [IO.File]::WriteAllBytes($temporary, $blob)
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    }
    finally {
        [Array]::Clear($raw, 0, $raw.Length)
    }
}

function Unprotect-CurrentUserSecret([string]$Path) {
    Add-Type -AssemblyName System.Security
    $blob = [IO.File]::ReadAllBytes($Path)
    $raw = [Security.Cryptography.ProtectedData]::Unprotect(
        $blob, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    try { return [Text.Encoding]::UTF8.GetString($raw) }
    finally { [Array]::Clear($raw, 0, $raw.Length) }
}

$restic = Resolve-ResticExecutable
$repositoryConfig = Join-Path $repository 'config'
$password = $null
try {
    if (Test-Path -LiteralPath $secretPath) {
        $password = Unprotect-CurrentUserSecret $secretPath
    }
    elseif (Test-Path -LiteralPath $repositoryConfig) {
        throw 'พบ Restic repository เดิมแต่ไม่พบ DPAPI secret — หยุดเพื่อไม่ทำ repository เดิมใช้การไม่ได้'
    }
    else {
        $random = New-Object byte[] 48
        $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($random) }
        finally { $rng.Dispose() }
        try { $password = [Convert]::ToBase64String($random) }
        finally { [Array]::Clear($random, 0, $random.Length) }
        Protect-CurrentUserSecret $password $secretPath
    }

    New-Item -ItemType Directory -Path $repository -Force | Out-Null
    & (Join-Path $PSScriptRoot 'harden_private_acl.ps1') -Targets @($data, $repository) -Recurse | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'ปรับ ACL ของ Restic/DPAPI ไม่สำเร็จ' }

    $env:RESTIC_REPOSITORY = $repository
    $env:RESTIC_PASSWORD = $password
    if (-not (Test-Path -LiteralPath $repositoryConfig)) {
        & $restic init
    }
    else {
        & $restic snapshots --compact | Out-Null
    }
    if ($LASTEXITCODE -ne 0) { throw 'Restic repository initialize/verify ไม่สำเร็จ' }

    $gh = (Get-Command gh -ErrorAction Stop).Source
    & $gh auth status | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'GitHub CLI ยังไม่ได้ sign in' }
    $githubRepository = Resolve-GitHubRepository $gh $root
    Set-GitHubSecretFromMemory `
        -Gh $gh -Repository $githubRepository -Name $githubSecretName `
        -Value $password -WorkingDirectory $root

    $python = Join-Path $garmin '.venv\Scripts\python.exe'
    $worker = Join-Path $garmin 'scripts\offsite_backup.py'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'ไม่พบ Python venv ของ Garmin'
    }
    $offsiteStatus = Join-Path $data 'sync_lane\offsite_backup.json'
    $restoreStatus = Join-Path $data 'sync_lane\restore_drill.json'
    $initialProofRun = $false
    if (-not ((Test-SuccessfulProof $offsiteStatus) -and (Test-SuccessfulProof $restoreStatus))) {
        Invoke-OffsiteWorker $python $worker 'backup'
        Invoke-OffsiteWorker $python $worker 'restore-drill'
        $initialProofRun = $true
    }

    $taskSetup = Join-Path $PSScriptRoot 'setup_scheduled_tasks.ps1'
    foreach ($taskName in $scheduledTasks) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $taskSetup -TaskName $taskName
        if ($LASTEXITCODE -ne 0) { throw "ตั้ง Scheduled Task $taskName ไม่สำเร็จ" }
    }

    [ordered]@{
        ok = $true
        repository_initialized = (Test-Path -LiteralPath $repositoryConfig)
        dpapi_secret = (Test-Path -LiteralPath $secretPath)
        github_recovery_secret = $githubSecretName
        initial_proof_run = $initialProofRun
        scheduled_tasks = $scheduledTasks
    } | ConvertTo-Json -Compress
}
finally {
    Remove-Item Env:RESTIC_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:RESTIC_REPOSITORY -ErrorAction SilentlyContinue
    $password = $null
}
