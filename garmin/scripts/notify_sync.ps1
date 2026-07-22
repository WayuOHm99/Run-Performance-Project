# notify_sync.ps1 — เด้ง Windows toast เมื่อรอบ sync Garmin มีปัญหา
#
# garmin-sync-auto.bat เรียกไฟล์นี้หลัง fetch_all.py จบทุกรอบ (ส่ง exit code มาทาง -SyncExit)
# อ่าน data\sync_status.json แล้วตัดสิน:
#   - มีคนล้มเหลว (token/เน็ต/timeout)        -> toast แดง บอกรายคน + วิธีแก้
#   - sync ผ่านแต่ sanity check เจอข้อมูลเพี้ยน -> toast เตือน บอกจำนวนจุด
#   - ทุกอย่างปกติ                              -> เงียบ (ไม่มี toast)
# toast ค้างอยู่ใน Action Center ของ Windows — ไม่อยู่หน้าจอตอนเด้งก็ย้อนดูได้
#
# กติกา: สคริปต์แจ้งเตือนต้องไม่ทำให้ Task ล้มเอง — ทุก error ในนี้กลืนเงียบ (exit 0 เสมอ)

param([int]$SyncExit = 0)

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
    $statusPath = Join-Path (Split-Path $PSScriptRoot -Parent) "data\sync_status.json"

    if (-not (Test-Path $statusPath)) {
        # fetch_all ตายก่อนเขียนสถานะ — ยังต้องแจ้งถ้า exit code บอกว่าพัง
        if ($SyncExit -ne 0) {
            Show-Toast "Garmin sync ล้มเหลว" "ไม่มีไฟล์สถานะ — เปิด log C:\Backup\garmin-sync-log.txt"
        }
        exit 0
    }

    $s = Get-Content $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json

    # ไฟล์สถานะเก่าค้างจากรอบก่อน (fetch_all รอบนี้ตายก่อนเขียน) — เชื่อ exit code แทน
    $ageHours = ((Get-Date) - [datetime]$s.run_at).TotalHours
    if ($ageHours -gt 1 -and $SyncExit -ne 0) {
        Show-Toast "Garmin sync ล้มเหลว" "รอบล่าสุดตายก่อนเขียนสถานะ — เปิด log C:\Backup\garmin-sync-log.txt"
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
