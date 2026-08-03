# notify_sync.ps1 — เด้ง Windows toast เมื่อรอบ sync Garmin มีปัญหา
#
# .bat ของแต่ละสายเรียกไฟล์นี้หลัง fetch_all.py จบทุกรอบ (ส่ง exit code มาทาง -SyncExit)
# อ่านสถานะ "ของสายตัวเอง" (data\sync_lane\<lane>.json — ต้องแยกสาย เพราะ sync_status.json
# ถูกทุกสายเขียนทับกัน: full 21:00 ล้ม แล้ว wellness 21:08 ผ่าน จะกลบร่องรอยหมด) แล้วตัดสิน:
#   - มีคนล้มเหลว (token/เน็ต/timeout)        -> toast แดง บอกรายคน + วิธีแก้
#   - sync ผ่านแต่ sanity check เจอข้อมูลเพี้ยน -> toast เตือน บอกจำนวนจุด
#   - ทุกอย่างปกติ                              -> เงียบ (ไม่มี toast)
# toast ค้างอยู่ใน Action Center ของ Windows — ไม่อยู่หน้าจอตอนเด้งก็ย้อนดูได้
#
# "รอบนี้เขียนสถานะจริงไหม" ตัดสินจาก start-marker (data\sync_*_run_start.txt ที่ bat เขียน
# ก่อนรัน fetch_all) — ไม่ใช่เดาจากอายุไฟล์ (heuristic เดิม >1 ชม. false-fire ตอนกดมือ).
# ถ้า run_at ของสายเก่ากว่าเวลาเริ่มรอบ = fetch_all ไม่ได้เขียน (ไม่ได้รัน/ตายก่อน).
#
# -CheckStale (สาย wellness เรียก ทุก 30 นาที = จังหวะเต้นของระบบ): เฝ้าดูว่ามีสายไหน
# "เงียบหายไป" ไหม — สายตายเงียบคือปัญหาที่เจ็บที่สุด เพราะไม่มีอะไรเตือนเลย
#
# กติกา: สคริปต์แจ้งเตือนต้องไม่ทำให้ Task ล้มเอง — ทุก error ในนี้กลืนเงียบ (exit 0 เสมอ)

param(
    [int]$SyncExit = 0,
    [string]$StartMarker = "sync_run_start.txt",
    [string]$Lane = "",
    [switch]$CheckStale
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

# ── ผลของรอบที่เพิ่งจบ ───────────────────────────────────────

function Test-Round([string]$StatusPath, [string]$StartPath) {
    # เวลาเริ่มรอบนี้ (bat เขียนก่อนรัน fetch_all) — ใช้ตัดสินว่าสถานะถูกเขียน "รอบนี้" จริงไหม
    $runStart = $null
    if (Test-Path $StartPath) {
        try { $runStart = [datetime]::Parse((Get-Content $StartPath -Raw).Trim()) } catch {}
    }

    if (-not (Test-Path $StatusPath)) {
        # ไม่มีไฟล์สถานะเลย — แจ้งถ้ารอบนี้ exit ผิดปกติ
        if ($SyncExit -ne 0) {
            Show-Toast "Garmin sync ล้มเหลว" "ไม่มีไฟล์สถานะ — เปิด log C:\Backup\garmin-sync-*.log"
        }
        return
    }

    $s = Get-Content $StatusPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $statusTime = [datetime]$s.run_at

    # สถานะรอบนี้จริงไหม: run_at ต้อง >= เวลาเริ่มรอบ (เผื่อ jitter 5 วิ). ถ้าไม่มี start-marker
    # (เช่นรัน fetch_all มือตรง ๆ ไม่ผ่าน bat) ถือว่า fresh เพื่อไม่เตือนพร่ำเพรื่อ
    $isFresh = ($null -eq $runStart) -or ($statusTime -ge $runStart.AddSeconds(-5))
    if (-not $isFresh) {
        Show-Toast "Garmin sync ล้มเหลว" "fetch_all ไม่ได้เขียนสถานะรอบนี้ (ไม่ได้รัน/ตายก่อน) — เปิด log C:\Backup\garmin-sync-*.log"
        return
    }

    $failed = @($s.results | Where-Object { -not $_.ok })
    $warned = @($s.results | Where-Object { $_.ok -and @($_.warnings).Count -gt 0 })
    if ($failed.Count -eq 0 -and $warned.Count -eq 0) { return }

    $lines = @()
    foreach ($f in $failed) {
        $why = switch ($f.reason) {
            "token"   { "token เสีย -> รัน เพิ่มนักกีฬา.bat" }
            "network" { "เน็ต/เซิร์ฟเวอร์มีปัญหา (รอบหน้าลองใหม่เอง)" }
            "timeout" { "ค้างเกินเวลาที่ให้ต่อคน" }
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
}


# ── เฝ้าสายที่เงียบหาย ────────────────────────────────────────
# เพดานอายุของแต่ละสาย = คาบเดินจริง + เผื่อรอบที่ข้ามเพราะ lock (ต้องหลวมพอไม่ให้เตือนพร่ำ)
$STALE_LIMIT_MIN = @{ full = 900; fast = 75; wellness = 90 }
$STALE_LABEL = @{ full = "sync เต็ม (08:00/21:00)"; fast = "กิจกรรม (ทุก 15 นาที)";
                  wellness = "wellness (ทุก 30 นาที)" }
$STALE_COOLDOWN_MIN = 360     # เตือนซ้ำได้ทุก 6 ชม. พอให้รู้ตัวโดยไม่รำคาญ

function Test-StaleLanes([string]$DataDir) {
    # เครื่องปิด/หลับ = ทุกสายเก่าหมดโดยธรรมชาติ ไม่ใช่ความผิดพลาด → ใช้ heartbeat ของ
    # รอบก่อนหน้าดูว่าเพิ่งกลับมาไหม ถ้าใช่ ข้ามรอบนี้ (รอบหน้าอีก 30 นาทีค่อยว่ากัน)
    $hbPath = Join-Path $DataDir "notify_heartbeat.txt"
    $now = Get-Date
    $prev = $null
    if (Test-Path $hbPath) {
        try { $prev = [datetime]::Parse((Get-Content $hbPath -Raw).Trim()) } catch {}
    }
    $now.ToString("o") | Set-Content -NoNewline -Encoding ASCII -Path $hbPath
    if ($null -eq $prev -or ($now - $prev).TotalMinutes -gt 45) { return }

    $laneDir = Join-Path $DataDir "sync_lane"
    $stale = @()
    foreach ($name in $STALE_LIMIT_MIN.Keys) {
        $p = Join-Path $laneDir "$name.json"
        if (-not (Test-Path $p)) { continue }   # สายที่ยังไม่เคยตั้ง ไม่ต้องเตือน
        try {
            $runAt = [datetime]((Get-Content $p -Raw -Encoding UTF8 | ConvertFrom-Json).run_at)
        } catch { continue }
        $ageMin = [int]($now - $runAt).TotalMinutes
        if ($ageMin -gt $STALE_LIMIT_MIN[$name]) {
            $stale += "{0}: เงียบมา {1:N1} ชม." -f $STALE_LABEL[$name], ($ageMin / 60)
        }
    }
    if ($stale.Count -eq 0) { return }

    # กันเตือนซ้ำถี่ ๆ ทุก 30 นาทีจนคนเลิกสนใจ
    $lastPath = Join-Path $DataDir "notify_stale_last.txt"
    if (Test-Path $lastPath) {
        try {
            $last = [datetime]::Parse((Get-Content $lastPath -Raw).Trim())
            if (($now - $last).TotalMinutes -lt $STALE_COOLDOWN_MIN) { return }
        } catch {}
    }
    $now.ToString("o") | Set-Content -NoNewline -Encoding ASCII -Path $lastPath
    Show-Toast "Garmin sync มีสายที่หยุดเดิน" (($stale -join "`n") +
        "`nเช็ค Task Scheduler + log C:\Backup\garmin-sync-*.log")
}

try {
    $dataDir = Join-Path (Split-Path $PSScriptRoot -Parent) "data"
    # สถานะของสายตัวเอง — ไม่ระบุ -Lane (เช่นรันมือ) ค่อย fallback ไฟล์รวมแบบเดิม
    $lanePath = if ($Lane) { Join-Path (Join-Path $dataDir "sync_lane") "$Lane.json" } else { $null }
    $statusPath = if ($lanePath -and (Test-Path $lanePath)) { $lanePath }
                  else { Join-Path $dataDir "sync_status.json" }
    $startPath = Join-Path $dataDir $StartMarker

    Test-Round $statusPath $startPath
    if ($CheckStale) { Test-StaleLanes $dataDir }
} catch {
    Write-Output "notify_sync.ps1 error (ไม่กระทบ sync): $_"
}
exit 0
