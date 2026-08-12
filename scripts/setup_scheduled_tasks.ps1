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
# ExecutionTimeLimit ต่างกันตามงาน: สายถี่สั้น (fast/wellness), Garmin full ยาวได้ (ยิง API หลายคน)
# MultipleInstances = IgnoreNew ทุกตัว: รอบใหม่มาตอนรอบเก่ายังไม่จบ ให้ข้ามไป ห้ามฆ่าของเก่า

$tasks = @(
    @{
        Name        = 'Run-Performance-Garmin-Fast'
        Desc        = 'ดึง activity summary วันนี้จาก Garmin ทุก 15 นาที (ไม่มีหน้าต่าง)'
        Exe         = 'wscript.exe'
        Script      = Join-Path $garmin 'garmin-fast-sync-hidden.vbs'
        TimeLimit   = 'PT10M'
        OnBattery   = $true
        # เริ่มนาที :05 (→ :05/:20/:35/:50) ไม่ให้ตรงกับ full sync ที่ยิงต้นชั่วโมง —
        # ชนกันทีไรสายนี้ต้องข้ามรอบเพราะ sync.lock เสียเที่ยวเปล่า
        Triggers    = { @(New-ScheduledTaskTrigger -Once -At '00:05' `
                            -RepetitionInterval (New-TimeSpan -Minutes 15) `
                            -RepetitionDuration (New-TimeSpan -Days 36500)) }
        Optional    = $false
    },
    @{
        Name        = 'Run-Performance-Garmin-Wellness'
        Desc        = 'ดึง wellness ที่ขยับระหว่างวัน (body battery/RHR/stress/HRV/นอน/readiness) ทุก 30 นาที'
        Exe         = 'wscript.exe'
        Script      = Join-Path $garmin 'garmin-wellness-sync-hidden.vbs'
        TimeLimit   = 'PT20M'
        OnBattery   = $true
        # เหลื่อมจาก Fast (:05/:20/:35/:50) และจาก full sync (ต้นชั่วโมง) กันแย่ง sync.lock
        Triggers    = { @(New-ScheduledTaskTrigger -Once -At '00:12' `
                            -RepetitionInterval (New-TimeSpan -Minutes 30) `
                            -RepetitionDuration (New-TimeSpan -Days 36500)) }
        Optional    = $false
    },
    @{
        Name        = 'Run-Performance-Garmin'
        Desc        = 'ดึงข้อมูล Garmin (กิจกรรม+wellness) ทุกคนลง garmin.db — ช่อง 08:00 + 21:00 (ยิงทุกชั่วโมงแล้วข้ามเองถ้าช่องนั้นทำแล้ว)'
        Exe         = 'wscript.exe'
        Script      = Join-Path $garmin 'garmin-sync-hidden.vbs'
        TimeLimit   = 'PT2H'
        OnBattery   = $true
        # ยิงทุกต้นชั่วโมง แล้วให้ --catch-up-slots 08:00,21:00 ใน .bat ตัดสินว่ารอบไหนของจริง
        # (รอบส่วนเกิน exit 75 เงียบ ๆ ไม่แตะ API เลย) — ทำแบบนี้เพราะ trigger รายวัน +
        # StartWhenAvailable ของ Windows ยิงตามให้แค่ครั้งเดียว พลาดแล้วหายทั้งวัน
        # (เจอจริง 2 ส.ค. 69: เครื่องหลับตอน 08:00 → รอบตามที่ 09:04 ตายเพราะ log ชนกัน → ไม่มี full sync ทั้งวัน)
        Triggers    = { @(New-ScheduledTaskTrigger -Once -At '00:00' `
                            -RepetitionInterval (New-TimeSpan -Hours 1) `
                            -RepetitionDuration (New-TimeSpan -Days 36500)) }
        Optional    = $false
    },
    @{
        Name        = 'Run-Performance-Backup'
        Desc        = 'สำรองโฟลเดอร์โปรเจกต์ + snapshot garmin.db ไป C:\Backup ทุกวัน 22:00'
        # ต้องไม่มีหน้าต่างเหมือนสายอื่น — งานนี้เป็นงานสุดท้ายที่ยังเปิดจอดำ แล้วก็โดนจริง
        # (3 ส.ค. 69 22:00 ตายกลางทาง exit 0xC000013A เงียบสนิท) ทั้งที่ถือสำเนาเดียว
        # ของ garmin.db อยู่ — .vbs ส่ง argument auto ให้ .bat เองแล้ว
        Exe         = 'wscript.exe'
        Script      = Join-Path $scripts 'backup-hidden.vbs'
        TimeLimit   = 'PT4H'         # เดิม 72 ชม. = งานที่ค้างจะกอดยาวข้ามคืนถัดไป
        # ⚠️ ต้องเป็น $true — เครื่องนี้เป็นโน้ตบุ๊ก (5 ส.ค. 69)
        #   เดิมตั้ง $false ด้วยเหตุผล "backup ใหญ่ ไม่ต้องรันตอนใช้แบต" ผลคือ Windows
        #   ได้สิทธิ์ทั้ง **ไม่เริ่ม** (DisallowStartIfOnBatteries) และ **ฆ่ากลางคัน**
        #   (StopIfGoingOnBatteries) — เงียบสนิททั้งสองแบบ ไม่มี marker ไม่มี toast
        #   เจอจริง 4 ส.ค. 22:00: เครื่องตื่นอยู่ (full sync log 22:00:02) แต่เสียบสายไม่อยู่
        #   → backup ไม่เริ่มเลย และ StartWhenAvailable ตอนตื่นเช้าก็ถูกบล็อกด้วยเหตุผล
        #   เดียวกัน = หายทั้งคืน ทั้งที่งานนี้ถือ**สำเนาเดียว**ของ garmin.db
        #   งานจริงเบามาก (mirror ~41MB + sqlite snapshot) ไม่คุ้มกับการยอมเสียสำเนา
        OnBattery   = $true
        Triggers    = { @(New-ScheduledTaskTrigger -Daily -At '22:00') }
        Optional    = $false
    },
    @{
        Name        = 'Run-Performance-Garmin-Reconcile'
        Desc        = 'เช็คกิจกรรมที่ถูกลบฝั่ง Garmin ย้อน 90 วัน (soft delete) ทุกอาทิตย์ 09:30'
        # ต้องไม่มีหน้าต่างเหมือนสายอื่น — หน้าต่างที่ปิดได้ คือหน้าต่างที่จะโดนปิด
        Exe         = 'wscript.exe'
        Script      = Join-Path $garmin 'garmin-reconcile-hidden.vbs'
        TimeLimit   = 'PT2H'
        OnBattery   = $true
        # ตรึง anchor เป็นวันอาทิตย์เหมือน DeepSync — รายสัปดาห์ (WeeksInterval 1) อาการ
        # ยังไม่ออกเพราะทุกอาทิตย์เป็นรอบอยู่แล้ว แต่ถ้าวันหลังเปลี่ยนเป็นทุก 2/4 สัปดาห์
        # แล้ว anchor ยังเป็นวันที่รันสคริปต์ จะเจอบั๊กเดียวกับที่ DeepSync เพิ่งเจอ
        Triggers    = {
            $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At '09:30'
            $trigger.StartBoundary = '2026-08-09T09:30:00'
            $trigger
        }
        Optional    = $true
    },
    @{
        Name        = 'Run-Performance-Garmin-DeepSync'
        Desc        = 'deep resync wellness ย้อน 45 วัน + ตรวจ schema drift (ทุก 4 สัปดาห์ วันอาทิตย์ เวลา 10:30)'
        # เคยเปิดจอดำแล้วโดนปิดกลางคันจริง (2 ส.ค. 69 exit 0xC000013A ค้างที่ Day 1/46)
        # รอบนี้กินเวลาหลายนาที ยิ่งเปิดค้างยิ่งเสี่ยง → ซ่อนหน้าต่างเหมือนสายอื่น
        Exe         = 'wscript.exe'
        Script      = Join-Path $garmin 'garmin-deepsync-hidden.vbs'
        TimeLimit   = 'PT4H'
        OnBattery   = $true
        # Task Scheduler ไม่มี -Monthly ใน cmdlet → ใช้รายสัปดาห์ทุก 4 สัปดาห์แทน
        #
        # ⚠️ ต้องตรึง StartBoundary เองเป็น "วันอาทิตย์" (แก้ 6 ส.ค. 69)
        #   New-ScheduledTaskTrigger ตั้ง StartBoundary = **วันที่บังเอิญรันสคริปต์นี้**
        #   แล้วเปลี่ยนแค่เวลา → รันวันจันทร์ที่ 3 ส.ค. ได้ anchor เป็นวันจันทร์ ทั้งที่
        #   trigger สั่งวันอาทิตย์ ผลคือ Windows คำนวณรอบถัดไปเป็น 9 ส.ค. (ห่าง 1 สัปดาห์)
        #   ไม่ใช่ 31 ส.ค. ตามเจตนา "ทุก 4 สัปดาห์" — และ cadence จะเลื่อนทุกครั้งที่มีคน
        #   รันสคริปต์นี้ซ้ำ ซึ่งขัดกับที่ตั้งใจให้ไฟล์นี้ idempotent
        #   anchor 2 ส.ค. 69 = วันอาทิตย์จริง และเป็นรอบ deepsync อัตโนมัติรอบล่าสุด
        #   → นับ 4 สัปดาห์ต่อได้พอดีเป็น 30 ส.ค. โดยไม่เลื่อนออกจากจังหวะเดิม
        Triggers    = {
            $trigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 4 -DaysOfWeek Sunday -At '10:30'
            $trigger.StartBoundary = '2026-08-02T10:30:00'
            $trigger
        }
        Optional    = $true
    }
)

$knownTaskNames = @($tasks | ForEach-Object { $_.Name })
if ($TaskName -and $TaskName -notin $knownTaskNames) {
    Write-Error "ไม่รู้จัก TaskName '$TaskName' (เลือกได้: $($knownTaskNames -join ', '))"
    exit 2
}

# ---------------- ตรวจ anchor ของ trigger รายสัปดาห์ ----------------
# ทำไมต้องมี: New-ScheduledTaskTrigger ตั้ง StartBoundary เป็น "วันที่รันสคริปต์นี้"
# ถ้าวันนั้นไม่ใช่วันที่ระบุใน -DaysOfWeek การนับ WeeksInterval จะยึดจากวันสุ่ม
# → cadence เพี้ยนเงียบ ๆ (เจอจริง 6 ส.ค. 69: DeepSync ตั้ง "ทุก 4 สัปดาห์ วันอาทิตย์"
# แต่ Windows คำนวณรอบถัดไปห่างแค่ 1 สัปดาห์ เพราะ anchor เป็นวันจันทร์)
# อาการนี้มองจากในสคริปต์ไม่เห็นเลย ต้องไป export XML ถึงจะรู้ → ให้สคริปต์ตรวจเองแทน
function Test-WeeklyTriggerAnchor {
    param($Triggers)

    $problems = @()
    foreach ($tr in $Triggers) {
        # trigger รายสัปดาห์เท่านั้น (รายวัน/-Once ไม่มี DaysOfWeek หรือเป็น 0)
        $dowProp = $tr.PSObject.Properties['DaysOfWeek']
        if (-not $dowProp -or -not $dowProp.Value) { continue }
        if (-not $tr.StartBoundary) { continue }

        $mask   = [int]$dowProp.Value          # bitmask: อาทิตย์=1, จันทร์=2, ... เสาร์=64
        $anchor = [datetime]$tr.StartBoundary
        $bit    = [int][math]::Pow(2, [int]$anchor.DayOfWeek)

        if (($mask -band $bit) -eq 0) {
            $wanted = @('Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday') |
                      Where-Object { $mask -band [int][math]::Pow(2, [array]::IndexOf(
                          @('Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'), $_)) }
            $problems += ("StartBoundary {0} เป็นวัน{1} แต่ trigger สั่งวัน {2} — " -f
                            $anchor.ToString('yyyy-MM-dd HH:mm'), $anchor.DayOfWeek, ($wanted -join '/')) +
                         "การนับ WeeksInterval จะยึดจากวันที่ผิด ทำให้รอบเพี้ยน"
        }
    }
    return $problems
}

# ---------------- ลงทะเบียน ----------------

$ok = 0; $skipped = 0; $failed = 0

foreach ($t in $tasks) {

    if ($TaskName -and $t.Name -ne $TaskName) {
        $skipped++
        continue
    }

    if ($t.Optional -and -not $IncludeOptional -and -not $TaskName) {
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

    # สร้าง trigger ก่อนแล้วตรวจ anchor — ต้องกันตั้งแต่ก่อนลงทะเบียน เพราะพอลงไปแล้ว
    # อาการจะเงียบสนิท (task ขึ้น Ready ปกติ แค่ยิงผิดจังหวะ) กว่าจะรู้ต้อง export XML ดู
    $triggers = & $t.Triggers
    $anchorProblems = Test-WeeklyTriggerAnchor $triggers
    if ($anchorProblems) {
        foreach ($p in $anchorProblems) {
            Write-Host "         [anchor ผิด] $p" -ForegroundColor Red
        }
        Write-Host "         → ไม่ลงทะเบียน task นี้ (แก้ StartBoundary ในนิยาม task ก่อน)" -ForegroundColor Red
        $failed++
        continue
    }
    foreach ($tr in $triggers) {
        if ($tr.PSObject.Properties['DaysOfWeek'] -and $tr.DaysOfWeek) {
            Write-Host ("         anchor: {0} (ทุก {1} สัปดาห์)" -f `
                        ([datetime]$tr.StartBoundary).ToString('yyyy-MM-dd HH:mm dddd'),
                        $(if ($tr.WeeksInterval) { $tr.WeeksInterval } else { 1 })) -ForegroundColor DarkGray
        }
    }

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
            -Action $action -Trigger $triggers `
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

# ---------------- ตรวจ event log ของ Task Scheduler ----------------
# ทำไมต้องเช็ค: Windows ปิด log นี้มาจากโรงงาน ผลคือเวลา task "ไม่ยิง" เราไม่มีทางรู้
# เหตุผลเลย — ต้องเดาจากหลักฐานแวดล้อม (เจอจริง 5 ส.ค. 69 ตอนไล่ว่าทำไม backup
# รอบ 22:00 หายไปทั้งคืน สุดท้ายเจอว่าเป็นเงื่อนไขแบต แต่กว่าจะเจอต้องไล่ log สายอื่น
# เทียบเวลาเอง). เปิดไว้แล้ว Windows จะบันทึกเหตุผลให้ตรง ๆ เช่น
#   ID 332 = ไม่รันเพราะเงื่อนไข (แบต/idle/เน็ต)  ID 111 = ถูกสั่งจบ  ID 101 = start ไม่สำเร็จ
# เช็คเฉย ๆ ไม่แก้ให้ เพราะการเปิดต้องใช้สิทธิ์ Administrator แต่สคริปต์นี้ตั้งใจให้รัน
# แบบ user ธรรมดาได้ (task เป็นของ user เอง) — ไม่ยอมแลกความง่ายตรงนั้นไปกับ log
$logName = 'Microsoft-Windows-TaskScheduler/Operational'
try {
    $logOn = (Get-WinEvent -ListLog $logName -ErrorAction Stop).IsEnabled
    if ($logOn) {
        Write-Host "event log ของ Task Scheduler: เปิดอยู่ ✔" -ForegroundColor DarkGray
    }
    else {
        Write-Host "event log ของ Task Scheduler: ปิดอยู่ — task ที่ไม่ยิงจะไม่มีเหตุผลให้ไล่" -ForegroundColor Yellow
        Write-Host "  เปิดด้วย (ต้อง Run as Administrator ครั้งเดียว):" -ForegroundColor Yellow
        Write-Host "  wevtutil sl $logName /e:true /rt:false /ms:20971520"
    }
}
catch {
    # อ่าน log ไม่ได้ไม่ควรทำให้สคริปต์ตั้ง task ล้ม — งานหลักจบไปแล้วด้วยซ้ำ
    Write-Host "event log ของ Task Scheduler: ตรวจไม่ได้ ($($_.Exception.Message))" -ForegroundColor DarkGray
}
Write-Host ""

if ($failed -gt 0) { exit 1 }
exit 0
