# harden_private_acl.ps1
#
# Protect directories that contain Garmin credentials, health data, or logs.
# The repository itself deliberately keeps its existing ACL; only these roots
# get a private, non-inheriting DACL.  Safe to run repeatedly.

[CmdletBinding()]
param(
    [ValidateSet('All', 'Garmin', 'Backup', 'Logs')]
    [string]$Scope = 'All',
    [string[]]$Targets = @(),
    [switch]$CheckOnly,
    [switch]$Recurse,
    [switch]$CheckTaskPrincipals,
    [switch]$Json
)

$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') {
    $result = [ordered]@{
        ok       = $false
        available = $false
        changed  = @()
        scanned  = 0
        problems = @([ordered]@{ path = ''; code = 'not_windows'; detail = 'Windows ACLs are unavailable' })
    }
    if ($Json) { $result | ConvertTo-Json -Depth 6 -Compress }
    else { Write-Host '[ACL] Windows ACLs are unavailable.' -ForegroundColor Yellow }
    exit 2
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$garminRoot = Join-Path $projectRoot 'garmin'
$defaultGarmin = @(
    (Join-Path $garminRoot 'tokens'),
    (Join-Path $garminRoot 'data')
)
$defaultBackup = @(
    'C:\Backup\Run-Performance',
    'C:\Backup\garmin-db-daily'
)
$defaultLogs = @('C:\Backup\run-performance-logs')

if ($Targets.Count -eq 0) {
    $Targets = switch ($Scope) {
        'Garmin' { $defaultGarmin }
        'Backup' { $defaultBackup }
        'Logs'   { $defaultLogs }
        default  { $defaultGarmin + $defaultBackup + $defaultLogs }
    }
}

$currentIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$currentSid = $currentIdentity.User
$systemSid = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$adminsSid = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$allowedSids = @($currentSid.Value, $systemSid.Value, $adminsSid.Value)
$inheritFlags = [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor `
                [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
$propagationFlags = [System.Security.AccessControl.PropagationFlags]::None
$allowType = [System.Security.AccessControl.AccessControlType]::Allow
$fullControl = [System.Security.AccessControl.FileSystemRights]::FullControl

$aclSections = [System.Security.AccessControl.AccessControlSections]::Access -bor `
               [System.Security.AccessControl.AccessControlSections]::Owner
$allowedSidSet = [System.Collections.Generic.HashSet[string]]::new(
    [string[]]$allowedSids,
    [System.StringComparer]::OrdinalIgnoreCase
)
$problems = [System.Collections.Generic.List[object]]::new()
$changed = [System.Collections.Generic.List[string]]::new()
$script:scanned = 0

function Add-Problem {
    param([string]$Path, [string]$Code, [string]$Detail)
    $script:problems.Add([ordered]@{ path = $Path; code = $Code; detail = $Detail })
}

function Get-PrivateAcl {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ([System.IO.Directory]::Exists($Path)) {
        return [System.IO.Directory]::GetAccessControl($Path, $aclSections)
    }
    return [System.IO.File]::GetAccessControl($Path, $aclSections)
}

function Set-PrivateAclObject {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Acl
    )
    if ([System.IO.Directory]::Exists($Path)) {
        [System.IO.Directory]::SetAccessControl($Path, $Acl)
    }
    else {
        [System.IO.File]::SetAccessControl($Path, $Acl)
    }
}

function Get-PrivateAccessRules {
    param([Parameter(Mandatory = $true)]$Acl)
    return $Acl.GetAccessRules(
        $true, $true, [System.Security.Principal.SecurityIdentifier]
    )
}

function Get-DescendantItems {
    param([Parameter(Mandatory = $true)][string]$RootPath)
    $results = [System.Collections.Generic.List[System.IO.FileSystemInfo]]::new()
    $rootDir = [System.IO.DirectoryInfo]::new($RootPath)
    if (-not $rootDir.Exists) { return $results }
    if ($rootDir.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { return $results }

    $stack = [System.Collections.Generic.Stack[System.IO.DirectoryInfo]]::new()
    $stack.Push($rootDir)
    while ($stack.Count -gt 0) {
        $current = $stack.Pop()
        $entries = $current.GetFileSystemInfos()
        for ($i = $entries.Length - 1; $i -ge 0; $i--) {
            $entry = $entries[$i]
            $results.Add($entry)
            if (($entry -is [System.IO.DirectoryInfo]) -and
                    -not ($entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
                $stack.Push([System.IO.DirectoryInfo]$entry)
            }
        }
    }
    return $results
}

function Test-TaskPrincipalsMatchCurrentUser {
    try {
        $schedule = New-Object -ComObject 'Schedule.Service'
        $schedule.Connect()
        $taskFolder = $schedule.GetFolder('\')
    }
    catch {
        Add-Problem '' 'task_scheduler_unavailable' 'Task Scheduler COM API is unavailable'
        return
    }

    $taskNames = @(
        'Run-Performance-Garmin-Fast',
        'Run-Performance-Garmin-Wellness',
        'Run-Performance-Garmin',
        'Run-Performance-Backup',
        'Run-Performance-Garmin-Reconcile',
        'Run-Performance-Garmin-DeepSync',
        'Run-Performance-OffsiteBackup',
        'Run-Performance-RestoreDrill',
        'Run-Performance-SystemHealth'
    )
    $currentLeaf = ($currentIdentity.Name -split '\\')[-1]

    foreach ($taskName in $taskNames) {
        try {
            $task = $taskFolder.GetTask("\$taskName")
        }
        catch {
            Add-Problem $taskName 'task_missing' 'Expected Scheduled Task is missing'
            continue
        }

        $userId = [string]$task.Definition.Principal.UserId
        $matches = [string]::Equals(
            $userId, $currentIdentity.Name,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -or [string]::Equals(
            $userId, $env:USERNAME,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -or [string]::Equals(
            $userId, $currentLeaf,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -or [string]::Equals(
            $userId, $currentSid.Value,
            [System.StringComparison]::OrdinalIgnoreCase
        )

        if (-not $matches) {
            try {
                $taskSid = [System.Security.Principal.NTAccount]::new($userId).Translate(
                    [System.Security.Principal.SecurityIdentifier]
                )
                $matches = $taskSid.Value -eq $currentSid.Value
            }
            catch {
                $matches = $false
            }
        }

        if (-not $matches) {
            Add-Problem $taskName 'task_principal_mismatch' `
                'Task does not run as the current user; private ACL would block it'
        }
    }
}

function Get-AclProblems {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][bool]$IsRoot,
        [System.IO.FileSystemInfo]$Item = $null
    )

    $local = [System.Collections.Generic.List[object]]::new()
    if ($null -eq $Item) {
        if ($IsRoot) {
            if (-not [System.IO.Directory]::Exists($Path)) {
                $local.Add([ordered]@{ path = $Path; code = 'missing'; detail = 'Private directory does not exist' })
                return $local
            }
            $Item = [System.IO.DirectoryInfo]::new($Path)
        }
        else {
            if ([System.IO.Directory]::Exists($Path)) {
                $Item = [System.IO.DirectoryInfo]::new($Path)
            }
            elseif ([System.IO.File]::Exists($Path)) {
                $Item = [System.IO.FileInfo]::new($Path)
            }
            else {
                $local.Add([ordered]@{ path = $Path; code = 'missing'; detail = 'Path does not exist' })
                return $local
            }
        }
    }

    if ($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        $local.Add([ordered]@{ path = $Path; code = 'reparse_point'; detail = 'Reparse points are not allowed in private roots' })
        return $local
    }

    $isContainer = $Item -is [System.IO.DirectoryInfo]
    $acl = if ($isContainer) {
        ([System.IO.DirectoryInfo]$Item).GetAccessControl($aclSections)
    }
    else {
        ([System.IO.FileInfo]$Item).GetAccessControl($aclSections)
    }
    $script:scanned++

    if ($IsRoot -and -not $acl.AreAccessRulesProtected) {
        $local.Add([ordered]@{ path = $Path; code = 'inheritance_enabled'; detail = 'Root still inherits its parent DACL' })
    }
    if (-not $IsRoot -and $acl.AreAccessRulesProtected) {
        $local.Add([ordered]@{ path = $Path; code = 'descendant_protected'; detail = 'Descendant does not inherit the private root DACL' })
    }

    $ownerSid = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
    if ($ownerSid -ne $currentSid.Value) {
        $local.Add([ordered]@{ path = $Path; code = 'wrong_owner'; detail = 'Owner is not the current Scheduled Task user' })
    }

    $rules = $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])
    if ($rules.Count -ne $allowedSids.Count) {
        $local.Add([ordered]@{ path = $Path; code = 'ace_count'; detail = 'DACL must contain exactly three access rules' })
    }

    foreach ($ace in $rules) {
        $sid = $ace.IdentityReference.Value
        if (-not $allowedSidSet.Contains($sid)) {
            $local.Add([ordered]@{ path = $Path; code = 'unexpected_ace'; detail = 'ACL grants or denies an identity outside current user, SYSTEM, and Administrators' })
        }
        if ($ace.AccessControlType -ne $allowType) {
            $local.Add([ordered]@{ path = $Path; code = 'deny_ace'; detail = 'Private paths must use the exact allow-only DACL' })
        }
    }

    $expectedInherited = -not $IsRoot
    $expectedInheritFlags = if ($isContainer) {
        $inheritFlags
    }
    else {
        [System.Security.AccessControl.InheritanceFlags]::None
    }
    foreach ($requiredSid in $allowedSids) {
        $matchCount = 0
        $matchedAce = $null
        foreach ($candidate in $rules) {
            if ($candidate.IdentityReference.Value -eq $requiredSid) {
                $matchCount++
                $matchedAce = $candidate
            }
        }
        if ($matchCount -eq 0) {
            $local.Add([ordered]@{ path = $Path; code = 'required_ace_missing'; detail = 'Current user, SYSTEM, and Administrators must each have FullControl' })
            continue
        }
        if ($matchCount -ne 1) {
            $local.Add([ordered]@{ path = $Path; code = 'duplicate_ace'; detail = 'Each allowed SID must appear exactly once' })
            continue
        }

        if ($matchedAce.AccessControlType -ne $allowType -or $matchedAce.FileSystemRights -ne $fullControl) {
            $local.Add([ordered]@{ path = $Path; code = 'required_ace_not_full_control'; detail = 'Each allowed SID must have exactly Allow FullControl' })
        }
        if ($matchedAce.IsInherited -ne $expectedInherited) {
            $local.Add([ordered]@{ path = $Path; code = 'wrong_inheritance_source'; detail = 'Root rules must be explicit and descendant rules must be inherited' })
        }
        if ($matchedAce.InheritanceFlags -ne $expectedInheritFlags -or
                $matchedAce.PropagationFlags -ne $propagationFlags) {
            $local.Add([ordered]@{ path = $Path; code = 'wrong_inheritance_flags'; detail = 'ACL inheritance flags do not match the exact private DACL' })
        }
    }
    return $local
}

function Set-PrivateRootAcl {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer) { throw "Private ACL target is not a directory: $Path" }
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        throw "Refusing to harden a reparse point: $Path"
    }

    $acl = Get-PrivateAcl -Path $Path
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($ace in @(Get-PrivateAccessRules -Acl $acl)) {
        [void]$acl.RemoveAccessRuleSpecific($ace)
    }
    # Setting Owner (even to the existing owner) requires WRITE_OWNER.  A normal
    # Scheduled Task account owns these roots and therefore has implicit
    # WRITE_DAC, but intentionally does not have WRITE_OWNER.  Avoid asking
    # Windows for a privilege that is unnecessary in the normal case.
    $ownerSid = $acl.GetOwner([System.Security.Principal.SecurityIdentifier])
    if ($ownerSid.Value -ne $currentSid.Value) {
        $acl.SetOwner($currentSid)
    }
    foreach ($sid in @($currentSid, $systemSid, $adminsSid)) {
        $rule = [System.Security.AccessControl.FileSystemAccessRule]::new(
            $sid, $fullControl, $inheritFlags, $propagationFlags, $allowType
        )
        [void]$acl.AddAccessRule($rule)
    }
    Set-PrivateAclObject -Path $Path -Acl $acl
}

function Reset-DescendantAcl {
    param([Parameter(Mandatory = $true)]$Item)

    if ($Item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        throw "Refusing to cross a reparse point: $($Item.FullName)"
    }
    $acl = Get-PrivateAcl -Path $Item.FullName
    $acl.SetAccessRuleProtection($false, $false)
    foreach ($ace in @(Get-PrivateAccessRules -Acl $acl)) {
        if (-not $ace.IsInherited) {
            [void]$acl.RemoveAccessRuleSpecific($ace)
        }
    }
    $ownerSid = $acl.GetOwner([System.Security.Principal.SecurityIdentifier])
    if ($ownerSid.Value -ne $currentSid.Value) {
        $acl.SetOwner($currentSid)
    }
    Set-PrivateAclObject -Path $Item.FullName -Acl $acl
}

if ($CheckTaskPrincipals) {
    Test-TaskPrincipalsMatchCurrentUser
    if ($problems.Count -gt 0 -and -not $CheckOnly) {
        # Fail before changing any ACL when another account still owns a task.
        $result = [ordered]@{
            ok        = $false
            available = $true
            changed   = @()
            scanned   = 0
            problems  = @($problems)
        }
        if ($Json) { $result | ConvertTo-Json -Depth 6 -Compress }
        else { $problems | ForEach-Object { Write-Host "[ACL FAIL] $($_.path): $($_.detail)" -ForegroundColor Red } }
        exit 1
    }
}

foreach ($rawTarget in $Targets) {
    $target = [System.IO.Path]::GetFullPath($rawTarget)
    try {
        $needsVerify = $true
        if (-not $CheckOnly) {
            $targetChanged = $false
            $rootProblems = Get-AclProblems -Path $target -IsRoot $true
            if ($rootProblems.Count -gt 0) {
                Set-PrivateRootAcl -Path $target
                $changed.Add($target)
                $targetChanged = $true
            }

            if ($Recurse) {
                $descendantChanged = $false
                foreach ($item in (Get-DescendantItems -RootPath $target)) {
                    $itemProblems = Get-AclProblems -Path $item.FullName -IsRoot $false -Item $item
                    if ($itemProblems.Count -gt 0) {
                        Reset-DescendantAcl -Item $item
                        $descendantChanged = $true
                    }
                }
                if ($descendantChanged) {
                    $changed.Add("$target\**")
                    $targetChanged = $true
                }
            }
            $needsVerify = $targetChanged
        }

        if ($needsVerify) {
            foreach ($problem in (Get-AclProblems -Path $target -IsRoot $true)) {
                $problems.Add($problem)
            }
            if ($Recurse -and [System.IO.Directory]::Exists($target)) {
                foreach ($item in (Get-DescendantItems -RootPath $target)) {
                    foreach ($problem in (Get-AclProblems -Path $item.FullName -IsRoot $false -Item $item)) {
                        $problems.Add($problem)
                    }
                }
            }
        }
    }
    catch {
        Add-Problem $target 'exception' $_.Exception.Message
    }
}

$result = [ordered]@{
    ok        = ($problems.Count -eq 0)
    available = $true
    changed   = @($changed)
    scanned   = $script:scanned
    problems  = @($problems)
}

if ($Json) {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $result | ConvertTo-Json -Depth 6 -Compress
}
else {
    if ($result.ok) {
        $mode = if ($CheckOnly) { 'check' } else { 'harden' }
        Write-Host "[ACL OK] $mode completed for $($Targets.Count) private roots; scanned $($result.scanned) paths." -ForegroundColor Green
    }
    else {
        foreach ($problem in $problems) {
            Write-Host "[ACL FAIL] $($problem.path): $($problem.detail)" -ForegroundColor Red
        }
    }
}

exit $(if ($result.ok) { 0 } else { 1 })
