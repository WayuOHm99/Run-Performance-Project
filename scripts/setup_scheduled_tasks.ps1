# setup_scheduled_tasks.ps1 — ตั้ง/ซ่อม Windows Scheduled Task ของโปรเจกต์ทั้งชุด
#
# ทำไมต้องมีไฟล์นี้
#   Scheduled Task อยู่ใน Windows ไม่ได้อยู่ใน git → ลง Windows ใหม่ / ย้ายเครื่อง /
#   เปลี่ยนชื่อโฟลเดอร์โปรเจกต์ แล้วงานอัตโนมัติจะหายหรือชี้ path ผิดเงียบๆ
#   (เจอจริง 26 ก.ค. 69: เปลี่ยนชื่อโฟลเดอร์ → เด้ง "Can not find script file")
#   ไฟล์นี้คือ source of truth ของตารางงานอัตโนมัติ รันซ้ำได้เรื่อยๆ (idempotent)
#
# วิธีใช้
#   คลิกขวาที่ไฟล์ → Run with PowerShell
#   หรือ:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup_scheduled_tasks.ps1
#   เพิ่ม -IncludeOptional เพื่อตั้ง reconcile รายสัปดาห์ + deepsync รายเดือนด้วย
#   เพิ่ม -TaskName <ชื่อ> เพื่อตั้งเฉพาะ task ที่ระบุ
#   เพิ่ม -DryRun เพื่อดูว่าจะตั้งอะไรบ้างโดยไม่แตะของจริง
#
# หมายเหตุ
#   - path ทุกอันคำนวณจากตำแหน่งไฟล์นี้ ไม่ hardcode → ย้ายโฟลเดอร์แล้วรันซ้ำก็จบ
#   - ไม่ต้องรัน as Administrator (task เป็นของ user ตัวเอง logon=Interactive)
#   - ไฟล์นี้ต้องเซฟเป็น UTF-8 **มี BOM** (PS 5.1 อ่านไทยไม่มี BOM แล้ว parser พัง)

[CmdletBinding()]
param(
    [switch]$IncludeOptional,
    [string]$TaskName,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$root    = Split-Path -Parent $PSScriptRoot
$scripts = Join-Path $root 'scripts'
$garmin  = Join-Path $root 'garmin'

Write-Host ""
Write-Host "โฟลเดอร์โปรเจกต์: $root" -ForegroundColor Cyan
Write-Host ""

# ---------------- นิยามงานทั้งหมด ----------------
# ExecutionTimeLimit ต่างกันตามงาน: LineSync สั้น (~9 วิ ปกติ), Garmin ยาวได้ (ยิง API หลายคน)
# MultipleInstances = IgnoreNew ทุกตัว: รอบใหม่มาตอนรอบเก่ายังไม่จบ ให้ข้ามไป ห้ามฆ่าของเก่า

$tasks = @(
    @{
        Name        = 'Run-Performance-LineSync'
        Desc        = 'ดึงรูป/ข้อความจากกลุ่มไลน์ลงเครื่อง ทุก 15 นาที (ไม่มีหน้าต่าง)'
        Exe         = 'wscript.exe'
        Script      = Join-Path $scripts 'sync-hidden.vbs'
        TimeLimit   = 'PT10M'
        OnBattery   = $true          # ให้รันแม้ใช้แบตเตอรี่
        Triggers    = { @(New-ScheduledTaskTrigger -Once -At '00:00' `
                            -RepetitionInterval (New-TimeSpan -Minutes 15) `
                            -RepetitionDuration (New-TimeSpan -Days 3650)) }
        Optional    = $false
    },
    @{
        Name        = 'Run-Performance-Garmin-Fast'
        Desc        = 'ดึง activity summary วันนี้จาก Garmin ทุก 15 นาที (ไม่มีหน้าต่าง)'
        Exe         = 'wscript.exe'
        Script      = Join-Path $garmin 'garmin-fast-sync-hidden.vbs'
        TimeLimit   = 'PT10M'
        OnBattery   = $true
        Triggers    = { @(New-ScheduledTaskTrigger -Once -At '00:00' `
                            -RepetitionInterval (New-TimeSpan -Minutes 15) `
                            -RepetitionDuration (New-TimeSpan -Days 3650)) }
        Optional    = $false
    },
    @{
        Name        = 'Run-Performance-Garmin'
        Desc        = 'ดึงข้อมูล Garmin (กิจกรรม+wellness) ทุกคนลง garmin.db วันละ 2 รอบ 08:00 + 21:00'
        Exe         = 'wscript.exe'
        Script      = Join-Path $garmin 'garmin-sync-hidden.vbs'
        TimeLimit   = 'PT2H'
        OnBattery   = $true
        Triggers    = { @(
                          (New-ScheduledTaskTrigger -Daily -At '08:00'),
                          (New-ScheduledTaskTrigger -Daily -At '21:00')
                       ) }
        Optional    = $false
    },
    @{
        Name        = 'Run-Performance-Backup'
        Desc        = 'สำรองโฟลเดอร์โปรเจกต์ไป C:\Backup ทุกวัน 22:00'
        Exe         = 'cmd.exe'
        Script      = Join-Path $scripts 'สำรองข้อมูล.bat'
        ExtraArgs   = 'auto'         # โหมด auto = ไม่ pause รอกด Enter
        TimeLimit   = 'PT72H'
        OnBattery   = $false         # backup ใหญ่ ไม่ต้องรันตอนใช้แบต
        Triggers    = { @(New-ScheduledTaskTrigger -Daily -At '22:00') }
        Optional    = $false
    },
    @{
        Name        = 'Run-Performance-Garmin-Reconcile'
        Desc        = 'เช็คกิจกรรมที่ถูกลบฝั่ง Garmin ย้อน 90 วัน (soft delete) ทุกอาทิตย์ 09:30'
        Exe         = 'cmd.exe'
        Script      = Join-Path $garmin 'garmin-reconcile-auto.bat'
        TimeLimit   = 'PT2H'
        OnBattery   = $true
        Triggers    = { @(New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At '09:30') }
        Optional    = $true
    },
    @{
        Name        = 'Run-Performance-Garmin-DeepSync'
        Desc        = 'deep resync wellness ย้อน 45 วัน + ตรวจ schema drift (เดือนละครั้ง วันที่ 1)'
        Exe         = 'cmd.exe'
        Script      = Join-Path $garmin 'garmin-deepsync-auto.bat'
        TimeLimit   = 'PT4H'
        OnBattery   = $true
        # Task Scheduler ไม่มี -Monthly ใน cmdlet → ใช้รายสัปดาห์ทุก 4 สัปดาห์แทน
        Triggers    = { @(New-ScheduledTaskTrigger -Weekly -WeeksInterval 4 -DaysOfWeek Sunday -At '10:30') }
        Optional    = $true
    }
)

# ---------------- ลงทะเบียน ----------------

$ok = 0; $skipped = 0; $failed = 0

foreach ($t in $tasks) {

    if ($TaskName -and $t.Name -ne $TaskName) {
        $skipped++
        continue
    }

    if ($t.Optional -and -not $IncludeOptional) {
        Write-Host "[ข้าม]  $($t.Name)  (ใส่ -IncludeOptional ถ้าต้องการ)" -ForegroundColor DarkGray
        $skipped++
        continue
    }

    if (-not (Test-Path -LiteralPath $t.Script)) {
        Write-Host "[พัง]   $($t.Name)  → ไม่พบไฟล์ $($t.Script)" -ForegroundColor Red
        $failed++
        continue
    }

    # ครอบ quote เสมอ: path อาจมีเว้นวรรคหรืออักษรไทย
    $argument = '"{0}"' -f $t.Script
    if ($t.Exe -eq 'cmd.exe') { $argument = '/c ' + $argument }
    if ($t.ExtraArgs)         { $argument = $argument + ' ' + $t.ExtraArgs }

    Write-Host "[ตั้ง]   $($t.Name)" -ForegroundColor Green
    Write-Host "         $($t.Exe) $argument"
    Write-Host "         $($t.Desc)" -ForegroundColor DarkGray

    if ($DryRun) { $ok++; continue }

    try {
        $action = New-ScheduledTaskAction -Execute $t.Exe -Argument $argument `
                    -WorkingDirectory (Split-Path -Parent $t.Script)

        # UserId ต้องเป็นชื่อแบบเต็ม DOMAIN\user (ใส่แค่ชื่อ user เปล่าๆ Windows ตอบ
        # "The parameter is incorrect" — เจอจริงตอนเขียนสคริปต์นี้)
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
                        -LogonType Interactive -RunLevel Limited

        $settings = New-ScheduledTaskSettingsSet `
                        -MultipleInstances IgnoreNew `
                        -StartWhenAvailable `
                        -ExecutionTimeLimit ([System.Xml.XmlConvert]::ToTimeSpan($t.TimeLimit)) `
                        -AllowStartIfOnBatteries:$t.OnBattery `
                        -DontStopIfGoingOnBatteries:$t.OnBattery

        Register-ScheduledTask -TaskName $t.Name -Description $t.Desc `
            -Action $action -Trigger (& $t.Triggers) `
            -Principal $principal -Settings $settings -Force | Out-Null

        $ok++
    }
    catch {
        Write-Host "         ล้มเหลว: $($_.Exception.Message)" -ForegroundColor Red
        $failed++
    }
}

Write-Host ""
Write-Host ("สรุป: ตั้งสำเร็จ {0} | ข้าม {1} | ล้มเหลว {2}" -f $ok, $skipped, $failed) -ForegroundColor Cyan
if ($DryRun) { Write-Host "(โหมด -DryRun ไม่ได้แตะของจริง)" -ForegroundColor Yellow }
Write-Host ""
Write-Host "ดูผล:  Get-ScheduledTask -TaskName 'Run-Performance-*' | Format-Table TaskName,State"
Write-Host ""
