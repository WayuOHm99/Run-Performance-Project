# notify_sync.ps1 — เด้ง Windows toast เมื่อรอบ sync Garmin มีปัญหา
#
# garmin-sync-auto.bat เรียกไฟล์นี้หลัง fetch_all.py จบทุกรอบ (ส่ง exit code มาทาง -SyncExit)
# อ่าน data\sync_status.json แล้วตัดสิน:
#   - มีคนล้มเหลว (token/เน็ต/timeout)        -> toast แดง บอกรายคน + วิธีแก้
#   - sync ผ่านแต่ sanity check เจอข้อมูลเพี้ยน -> toast เตือน บอกจำนวนจุด
#   - ทุกอย่างปกติ                              -> เงียบ (ไม่มี toast)
# toast ค้างอยู่ใน Action Center ของ Windows — ไม่อยู่หน้าจอตอนเด้งก็ย้อนดูได้
#
# "รอบนี้เขียนสถานะจริงไหม" ตัดสินจาก start-marker (data\sync_run_start.txt ที่ bat เขียน
# ก่อนรัน fetch_all) — ไม่ใช่เดาจากอายุไฟล์ (heuristic เดิม >1 ชม. false-fire ตอนกดมือ).
# ถ้า sync_status.run_at เก่ากว่าเวลาเริ่มรอบ = fetch_all ไม่ได้เขียน (ไม่ได้รัน/ตายก่อน).
#
# กติกา: สคริปต์แจ้งเตือนต้องไม่ทำให้ Task ล้มเอง — ทุก error ในนี้กลืนเงียบ (exit 0 เสมอ)

param(
    [int]$SyncExit = 0,
    [string]$StartMarker = "sync_run_start.txt"
)

$ErrorActionPreference = "Stop"

function Show-Toast([string]$Title, [string]$Body) {
    try {
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        # escape อักขระพิเศษ XML (ข้อความมีชื่อไฟล์/ข้อความ error ปนได้)
        $t = [System.Security.SecurityElement]::Escape($Title)
        $b = [System.Security.SecurityElement]::Escape($Body)
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml("<toast><visual><binding template=`"ToastGeneric`"><text>$t</text><text>$b</text></binding></visual></toast>")
        # AppId ของ PowerShell — toast จากสคริปต์ unpackaged ต้องอิง AppUserModelID ที่ลงทะเบียนแล้ว
        $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
        $toast = New-Object Windows.UI.Notifications.ToastNotification($xml)
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
        $flat = $Body -replace "`n", " / "
        Write-Output "toast: $Title | $flat"
    } catch {
        Write-Output "toast ล้มเหลว (ไม่กระทบ sync): $_"
    }
}

try {
    $dataDir = Join-Path (Split-Path $PSScriptRoot -Parent) "data"
    $statusPath = Join-Path $dataDir "sync_status.json"
    $startPath = Join-Path $dataDir $StartMarker

    # เวลาเริ่มรอบนี้ (bat เขียนก่อนรัน fetch_all) — ใช้ตัดสินว่าสถานะถูกเขียน "รอบนี้" จริงไหม
    $runStart = $null
    if (Test-Path $startPath) {
        try { $runStart = [datetime]::Parse((Get-Content $startPath -Raw).Trim()) } catch {}
    }

    if (-not (Test-Path $statusPath)) {
        # ไม่มีไฟล์สถานะเลย — แจ้งถ้ารอบนี้ exit ผิดปกติ
        if ($SyncExit -ne 0) {
            Show-Toast "Garmin sync ล้มเหลว" "ไม่มีไฟล์สถานะ — เปิด log C:\Backup\garmin-sync-log.txt"
        }
        exit 0
    }

    $s = Get-Content $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $statusTime = [datetime]$s.run_at

    # สถานะรอบนี้จริงไหม: run_at ต้อง >= เวลาเริ่มรอบ (เผื่อ jitter 5 วิ). ถ้าไม่มี start-marker
    # (เช่นรัน fetch_all มือตรง ๆ ไม่ผ่าน bat) ถือว่า fresh เพื่อไม่เตือนพร่ำเพรื่อ
    $isFresh = ($runStart -eq $null) -or ($statusTime -ge $runStart.AddSeconds(-5))
    if (-not $isFresh) {
        Show-Toast "Garmin sync ล้มเหลว" "fetch_all ไม่ได้เขียนสถานะรอบนี้ (ไม่ได้รัน/ตายก่อน) — เปิด log C:\Backup\garmin-sync-log.txt"
        exit 0
    }

    $failed = @($s.results | Where-Object { -not $_.ok })
    $warned = @($s.results | Where-Object { $_.ok -and @($_.warnings).Count -gt 0 })

    if ($failed.Count -eq 0 -and $warned.Count -eq 0) { exit 0 }

    $lines = @()
    foreach ($f in $failed) {
        $why = switch ($f.reason) {
            "token"   { "token เสีย -> รัน เพิ่มนักกีฬา.bat" }
            "network" { "เน็ต/เซิร์ฟเวอร์มีปัญหา (รอบหน้าลองใหม่เอง)" }
            "timeout" { "ค้างเกิน 20 นาที" }
            default   { "ล้มเหลว -> ดู log" }
        }
        $lines += "$($f.slug): $why"
    }
    foreach ($w in $warned) {
        $lines += "$($w.slug): ข้อมูลน่าสงสัย $(@($w.warnings).Count) จุด (ดู log)"
    }

    $title = if ($failed.Count -gt 0) { "Garmin sync ล้มเหลว $($failed.Count) คน" }
             else { "Garmin sync: ข้อมูลมีจุดน่าสงสัย" }
    Show-Toast $title ($lines -join "`n")
} catch {
    Write-Output "notify_sync.ps1 error (ไม่กระทบ sync): $_"
}
exit 0
