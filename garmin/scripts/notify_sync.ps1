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
# -CheckStale (สาย wellness เรียก ทุก 30 นาที = จังหวะเต้นของระบบ): เฝ้าดูทุกสาย
# (full/fast/wellness/reconcile/deep/backup) ว่า "เงียบหายไป" หรือ "เริ่มรอบแล้วไม่จบ" ไหม —
# สายตายเงียบคือปัญหาที่เจ็บที่สุด เพราะไม่มีอะไรเตือนเลย ยิ่งสายที่นาน ๆ เดินที
# (reconcile รายสัปดาห์ / deep ทุก 4 สัปดาห์) ยิ่งไม่มีใครสังเกต
#
# กติกา: สคริปต์แจ้งเตือนต้องไม่ทำให้ Task ล้มเอง — ทุก error ในนี้กลืนเงียบ (exit 0 เสมอ)

param(
    [int]$SyncExit = 0,
    [string]$StartMarker = "sync_run_start.txt",
    [string]$Lane = "",
    [ValidateSet("", "drift")][string]$FailureContext = "",
    [switch]$CheckStale,
    # -StaleOnly: รอบนี้ไม่ได้ทำงานจริง (ข้ามเพราะชน lock) จึงไม่มี "ผลของรอบ" ให้ตรวจ —
    # เอาไว้ให้สาย wellness ยังเดิน watchdog ได้แม้รอบตัวเองถูกข้าม ไม่งั้นช่วงที่มีสายอื่น
    # ค้างกอด lock ยาว ๆ (= ช่วงที่น่าจะมีปัญหาที่สุด) watchdog จะเงียบไปพร้อมกันทั้งระบบ
    [switch]$StaleOnly,
    # Test/portable seams: production leaves these blank and uses garmin/data + Windows toast.
    [string]$DataDir = "",
    [string]$NotificationLog = "",
    [string]$NowIso = "",
    [ValidateRange(1, 10080)][int]$CooldownMinutes = 360
)

$ErrorActionPreference = "Stop"
$script:Now = if ($NowIso) { [DateTimeOffset]::Parse($NowIso) } else { [DateTimeOffset]::Now }
$script:Conditions = @()
$script:ScopeComplete = @{}
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Add-Condition(
    [string]$Scope, [string]$Key, [string]$Title, [string]$Body
) {
    $script:Conditions += [pscustomobject]@{
        scope = $Scope; key = $Key; title = $Title; body = $Body
    }
}

function Get-WarningIdentity([string]$Warning) {
    # Use the full warning only to derive a local opaque identity.  Dates, activity IDs,
    # and health details stay in the protected lane log and never enter toast/state text.
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Warning)
        $hex = [System.BitConverter]::ToString($sha.ComputeHash($bytes)).Replace("-", "")
        return $hex.Substring(0, 16).ToLowerInvariant()
    }
    finally { $sha.Dispose() }
}

function Get-WarningLabel([string]$Warning) {
    if ($Warning -match '^wellness endpoint degraded') { return "Garmin wellness ตอบไม่ครบ" }
    if ($Warning -match '^wellness ว่างทั้งวัน') { return "wellness ว่างทั้งวัน" }
    if ($Warning -match '^wellness เป็น partial snapshot') { return "wellness ยังมาไม่ครบ" }
    if ($Warning -match '^วิ่ง .*ไม่มี HR') { return "กิจกรรมวิ่งไม่มี HR" }
    if ($Warning -match '^วิ่ง .*ไม่มีระยะทาง') { return "กิจกรรมวิ่งไม่มีระยะทาง" }
    if ($Warning -match '^กิจกรรม .*เวลารวม') { return "กิจกรรมไม่มีเวลารวม" }
    if ($Warning -match '^reconcile:') { return "รายการกิจกรรมเปลี่ยนจาก Garmin" }
    return "ข้อมูลมีจุดน่าสงสัย"
}

function Show-Toast([string]$Title, [string]$Body) {
    if ($NotificationLog) {
        $parent = Split-Path $NotificationLog -Parent
        if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        $entry = [ordered]@{
            at = $script:Now.ToString("o"); title = $Title; body = $Body
        } | ConvertTo-Json -Compress
        [System.IO.File]::AppendAllText($NotificationLog, $entry + [Environment]::NewLine, $utf8NoBom)
        Write-Output "notification-sink: $Title"
        return
    }
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

function Publish-Scope([string]$Scope, [string]$DataRoot) {
    $items = @($script:Conditions | Where-Object { $_.scope -eq $Scope } |
        Select-Object key, title, body)
    $safeScope = $Scope -replace "[^a-zA-Z0-9_.-]", "_"
    $conditionPath = Join-Path $DataRoot "notify_conditions_$safeScope.json"
    $statePath = Join-Path $DataRoot "notify_state.json"
    $json = ConvertTo-Json -InputObject @($items) -Depth 4 -Compress
    [System.IO.Directory]::CreateDirectory($DataRoot) | Out-Null
    [System.IO.File]::WriteAllText($conditionPath, $json, $utf8NoBom)
    try {
        $garminRoot = Split-Path $PSScriptRoot -Parent
        $python = Join-Path $garminRoot ".venv\Scripts\python.exe"
        if (-not (Test-Path $python)) {
            $python = Join-Path $garminRoot ".venv/bin/python"
        }
        $policy = Join-Path $PSScriptRoot "notification_policy.py"
        $nowText = $script:Now.ToString("o")
        $observation = if ($script:ScopeComplete[$Scope] -eq $true) { "complete" }
                       else { "unknown" }
        $previousErrorAction = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        # notification_policy.py พ่น UTF-8 (-X utf8) แต่ PowerShell ถอดรหัส stdout ของลูก
        # ตาม [Console]::OutputEncoding ซึ่งเป็น OEM codepage ของสภาพแวดล้อม (เช่น IBM437
        # ตอนถูกเรียกโดยไม่มี console ติดมา อย่างใน Scheduled Task) ทำให้ข้อความไทยใน toast
        # กลายเป็น α╕üα╕┤α╕ê... ต้องปักหมุด UTF-8 ไว้เอง ห้ามพึ่ง codepage ของเครื่อง
        $previousOutputEncoding = [Console]::OutputEncoding
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        try {
            $raw = & $python -X utf8 $policy --state $statePath --scope $Scope `
                --conditions $conditionPath --now $nowText `
                --cooldown-minutes $CooldownMinutes --observation $observation 2>&1
        }
        finally {
            $ErrorActionPreference = $previousErrorAction
            [Console]::OutputEncoding = $previousOutputEncoding
        }
        if ($LASTEXITCODE -ne 0) {
            $details = ($raw | Out-String).Trim()
            throw "notification policy failed: $details"
        }
        $result = ($raw -join "`n") | ConvertFrom-Json

        $alerts = @($result.alerts)
        if ($alerts.Count -gt 0) {
            $title = if ($alerts.Count -eq 1) { $alerts[0].title }
                     else { "Garmin: พบปัญหาใหม่/ถึงเวลาเตือน $($alerts.Count) รายการ" }
            Show-Toast $title (($alerts | ForEach-Object { $_.body }) -join "`n")
        }
        $recoveries = @($result.recoveries)
        if ($recoveries.Count -gt 0) {
            $body = ($recoveries | ForEach-Object { "$($_.body) — กลับมาปกติแล้ว" }) -join "`n"
            Show-Toast "Garmin: ปัญหาคลี่คลาย $($recoveries.Count) รายการ" $body
        }
    }
    finally {
        Remove-Item -LiteralPath $conditionPath -Force -ErrorAction SilentlyContinue
    }
}

# ── ผลของรอบที่เพิ่งจบ ───────────────────────────────────────

function Test-Round([string]$StatusPath, [string]$StartPath) {
    $scope = "round-" + $(if ($Lane) { $Lane } else { "manual" })
    $script:ScopeComplete[$scope] = $false
    # เวลาเริ่มรอบนี้ (bat เขียนก่อนรัน fetch_all) — ใช้ตัดสินว่าสถานะถูกเขียน "รอบนี้" จริงไหม
    $runStart = $null
    if (Test-Path $StartPath) {
        try {
            $runStart = [datetime]::Parse((Get-Content $StartPath -Raw).Trim())
        }
        catch {
            Add-Condition $scope "start-marker-invalid" "Garmin sync ล้มเหลว" `
                "start marker เสีย/อ่านไม่ได้ — เปิด log C:\Backup\run-performance-logs\garmin-sync-*.log"
            return
        }
    }
    elseif ($Lane) {
        Add-Condition $scope "start-marker-missing" "Garmin sync ล้มเหลว" `
            "ไม่มี start marker ของรอบนี้ — prep_log ทำงานไม่สำเร็จ"
        return
    }

    if (-not (Test-Path $StatusPath)) {
        Add-Condition $scope "status-missing" "Garmin sync ล้มเหลว" `
            "ไม่มีไฟล์สถานะ — เปิด log C:\Backup\run-performance-logs\garmin-sync-*.log"
        return
    }

    try {
        $s = Get-Content $StatusPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $s.run_at) { throw "status ไม่มี run_at" }
        $statusTime = [datetime]$s.run_at
        $results = @($s.results)
        if ($results.Count -eq 0) { throw "status ไม่มี results" }
        foreach ($result in $results) {
            $okProperty = if ($null -ne $result) { $result.PSObject.Properties['ok'] } else { $null }
            if ($null -eq $okProperty -or $okProperty.Value -isnot [bool]) {
                throw "status results[].ok ต้องเป็น boolean"
            }
        }
    }
    catch {
        Add-Condition $scope "status-invalid" "Garmin sync ล้มเหลว" `
            "ไฟล์สถานะเสีย/อ่านไม่ได้ — เปิด log C:\Backup\run-performance-logs\garmin-sync-*.log"
        return
    }

    # สถานะรอบนี้จริงไหม: run_at ต้อง >= เวลาเริ่มรอบ (เผื่อ jitter 5 วิ). ถ้าไม่มี start-marker
    # (เช่นรัน fetch_all มือตรง ๆ ไม่ผ่าน bat) ถือว่า fresh เพื่อไม่เตือนพร่ำเพรื่อ
    $isFresh = ($null -eq $runStart) -or ($statusTime -ge $runStart.AddSeconds(-5))
    if (-not $isFresh) {
        Add-Condition $scope "status-not-fresh" "Garmin sync ล้มเหลว" `
            "fetch_all ไม่ได้เขียนสถานะรอบนี้ (ไม่ได้รัน/ตายก่อน) — เปิด log C:\Backup\run-performance-logs\garmin-sync-*.log"
        return
    }

    # From this point results are structurally valid and belong to this round,
    # so an absent prior condition is real recovery rather than "unknown".
    $script:ScopeComplete[$scope] = $true

    $failed = @($s.results | Where-Object { -not $_.ok })
    $warned = @($s.results | Where-Object { $_.ok -and @($_.warnings).Count -gt 0 })
    if ($SyncExit -ne 0 -and $failed.Count -eq 0) {
        if ($FailureContext -eq "drift") {
            Add-Condition $scope "launcher-drift-$SyncExit" `
                "Garmin data quality/schema drift" `
                "พบข้อมูลน่าสงสัยหรือ schema drift (exit $SyncExit) — เปิด deepsync log"
        }
        else {
            Add-Condition $scope "launcher-exit-$SyncExit" "Garmin sync ล้มเหลว" `
                "worker/launcher คืน exit code $SyncExit แม้ status เดิมจะดูสำเร็จ — เปิด log"
        }
        return
    }
    if ($failed.Count -eq 0 -and $warned.Count -eq 0) { return }

    foreach ($f in $failed) {
        $why = switch ($f.reason) {
            "token"   { "token เสีย -> รัน เพิ่มนักกีฬา.bat" }
            "network" { "เน็ต/เซิร์ฟเวอร์มีปัญหา (รอบหน้าลองใหม่เอง)" }
            "timeout" { "ค้างเกินเวลาที่ให้ต่อคน" }
            "payload" { "Garmin payload ผิดรูปแบบ/ข้อมูลตอบกลับเสีย -> ดู log" }
            default   { "ล้มเหลว -> ดู log" }
        }
        $safeReason = if ($f.reason -match '^[a-zA-Z0-9_-]+$') { $f.reason } else { "error" }
        Add-Condition $scope "athlete-$($f.slug)-$safeReason" `
            "Garmin sync ล้มเหลว" "$($f.slug): $why"
    }
    foreach ($w in $warned) {
        $safeSlug = ([string]$w.slug) -replace '[^a-zA-Z0-9_.-]', '_'
        $seenWarnings = @{}
        foreach ($warning in @($w.warnings)) {
            $warningText = [string]$warning
            $identity = Get-WarningIdentity $warningText
            if ($seenWarnings.ContainsKey($identity)) { continue }
            $seenWarnings[$identity] = $true
            Add-Condition $scope "athlete-$safeSlug-warning-$identity" `
                "Garmin sync: ข้อมูลมีจุดน่าสงสัย" `
                "$($w.slug): $(Get-WarningLabel $warningText) (ดู log)"
        }
    }
}


# ── เฝ้าสายที่เงียบหาย ────────────────────────────────────────
# เพดานอายุของแต่ละสาย = คาบเดินจริง + เผื่อรอบที่ข้ามเพราะ lock (ต้องหลวมพอไม่ให้เตือนพร่ำ)
# สายนาน ๆ ครั้งก็ต้องเฝ้าด้วย — ยิ่งห่างยิ่งไม่มีใครสังเกตว่ามันตายไปแล้ว (deepsync
# 2 ส.ค. 69 ตายตั้งแต่นาทีแรก ไม่มีอะไรเตือนเลย รอบถัดไปคืออีก 4 สัปดาห์)
$STALE_LIMIT_MIN = [ordered]@{ full = 900; fast = 75; wellness = 90
                               reconcile = 12240; deep = 44640; backup = 1800 }
$STALE_LABEL = @{ full = "sync เต็ม (08:00/21:00)"; fast = "กิจกรรม (ทุก 15 นาที)";
                  wellness = "wellness (ทุก 30 นาที)";
                  reconcile = "เช็คกิจกรรมถูกลบ (ทุกอาทิตย์)";
                  deep = "deep resync (ทุก 4 สัปดาห์)";
                  backup = "สำรองข้อมูล (ทุกคืน 22:00)" }
# start-marker ของแต่ละสาย — .bat เขียนก่อนเริ่มรอบ และลบทิ้งเองเมื่อข้ามรอบ (exit 75)
# marker ที่ค้างอยู่โดยไม่มีสถานะของรอบนั้นตามมา = รอบนั้น "เริ่มแล้วไม่จบ" ซึ่งเป็นรูที่
# ใหญ่ที่สุดของระบบเตือน: รอบที่โดนฆ่ากลางทางเตือนตัวเองไม่ได้เลย เพราะ .bat ไม่ได้เดิน
# ไปถึงบรรทัด notify — marker คือร่องรอยเดียวที่เหลือ
$STALE_MARKER = @{ full = "sync_run_start.txt"; fast = "sync_fast_run_start.txt";
                   wellness = "sync_wellness_run_start.txt";
                   reconcile = "sync_reconcile_run_start.txt";
                   deep = "sync_deep_run_start.txt";
                   backup = "sync_backup_run_start.txt" }
# เผื่อเวลาที่รอบหนึ่งใช้จริง ก่อนจะสรุปว่า "ตายกลางคัน" ไม่ใช่ "กำลังรันอยู่ตอนนี้"
$RUN_GRACE_MIN = @{ full = 30; fast = 10; wellness = 10; reconcile = 60; deep = 90; backup = 60 }
# heartbeat ที่ส่งออกนอกเครื่องไม่ใช่หนึ่งใน 6 สาย sync ด้านบน (ค่าพวกนั้นต้องตรงกับ
# dashboard.py เป๊ะ ๆ) จึงแยกค่าไว้ต่างหาก. ทำไมต้องเฝ้าตรงนี้: จาก GitHub ความเงียบ
# แปลได้ทั้ง "เครื่องหลับ" และ "publisher พัง" — แยกไม่ออก (18 ส.ค. 69 เครื่องหลับ
# 16:19-20:17 เปิด incident หลอก 3 รอบ) แต่ในเครื่องแยกออก เพราะรู้ว่าตื่นมานานแค่ไหน
# เพดาน = คาบส่งจริง 2 ชม. + เผื่ออีกหนึ่งช่อง (retry ของ task ห่าง 15 นาที 2 ครั้ง)
$HEARTBEAT_MARKER = "heartbeat_published_at.txt"
$HEARTBEAT_STALE_LIMIT_MIN = 180
$HEARTBEAT_LABEL = "heartbeat ออกนอกเครื่อง (ทุก 2 ชม.)"

function Read-TimeFile([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    try { return [datetime]::Parse((Get-Content $Path -Raw).Trim()) } catch { return $null }
}

function Test-StaleLanes([string]$DataDir) {
    # เครื่องปิด/หลับ = ทุกสายเก่าหมดโดยธรรมชาติ ไม่ใช่ความผิดพลาด → ใช้ heartbeat ของ
    # รอบก่อนหน้าดูว่าเพิ่งกลับมาไหม ถ้าใช่ ข้ามรอบนี้ (รอบหน้าอีก 30 นาทีค่อยว่ากัน)
    $hbPath = Join-Path $DataDir "notify_heartbeat.txt"
    $scope = "stale"
    $script:ScopeComplete[$scope] = $false
    $now = $script:Now.LocalDateTime
    $awakePath = Join-Path $DataDir "notify_awake_since.txt"
    $prev = Read-TimeFile $hbPath
    $now.ToString("o") | Set-Content -NoNewline -Encoding ASCII -Path $hbPath
    if ($null -eq $prev -or ($now - $prev).TotalMinutes -gt 45) {
        # เพิ่งกลับมา — เวลาที่หายไปคือเวลาที่เครื่องหลับ ไม่ใช่เวลาที่ระบบพัง ต้องรีเซ็ต
        # นาฬิกา "ตื่นตั้งแต่" ด้วย ไม่งั้นรอบถัดไป (อีก 30 นาที) จะเอาอายุที่สะสมตอนหลับ
        # ไปตัดสินว่า publisher พัง = เตือนหลอกแบบเดียวกับที่ GitHub เคยทำ
        $now.ToString("o") | Set-Content -NoNewline -Encoding ASCII -Path $awakePath
        return
    }
    $awakeSince = Read-TimeFile $awakePath
    if ($null -eq $awakeSince) {
        $awakeSince = $now
        $now.ToString("o") | Set-Content -NoNewline -Encoding ASCII -Path $awakePath
    }
    $awakeMin = ($now - $awakeSince).TotalMinutes

    $laneDir = Join-Path $DataDir "sync_lane"
    $observationComplete = $true
    foreach ($name in $STALE_LIMIT_MIN.Keys) {
        $runAt = $null
        $p = Join-Path $laneDir "$name.json"
        if (Test-Path $p) {
            try {
                $rawStatus = Get-Content $p -Raw -Encoding UTF8 | ConvertFrom-Json
                if (-not $rawStatus.run_at) { throw "run_at missing" }
                $runAt = [datetime]$rawStatus.run_at
            }
            catch {
                $observationComplete = $false
                Add-Condition $scope "lane-$name-status-invalid" `
                    "Garmin sync มีไฟล์สถานะเสีย" `
                    "$($STALE_LABEL[$name]): ไฟล์สถานะอ่านไม่ได้ — เปิด log"
                $runAt = $null
            }
        }
        # สายที่เพิ่มเข้ามาใหม่แล้วลืมใส่ marker/grace ต้องไม่ทำให้ watchdog ทั้งตัวตาย
        # เงียบ ๆ (Join-Path กับ $null โยน error แล้ว try ข้างนอกจะกลืนหายไปทั้งฟังก์ชัน)
        $marker = $STALE_MARKER[$name]
        $startAt = if ($marker) { Read-TimeFile (Join-Path $DataDir $marker) } else { $null }
        if ($marker -and (Test-Path (Join-Path $DataDir $marker)) -and $null -eq $startAt) {
            $observationComplete = $false
            Add-Condition $scope "lane-$name-marker-invalid" `
                "Garmin sync มี start marker เสีย" `
                "$($STALE_LABEL[$name]): อ่านเวลาเริ่มรอบไม่ได้ — เปิด log"
            continue
        }
        $grace = if ($RUN_GRACE_MIN[$name]) { $RUN_GRACE_MIN[$name] } else { 60 }

        # (1) รอบที่เริ่มแล้วไม่จบ — เริ่มไปแล้วแต่ไม่มีสถานะของรอบนั้นตามมา
        if ($startAt -and (($null -eq $runAt) -or ($runAt -lt $startAt.AddSeconds(-5)))) {
            if (($now - $startAt).TotalMinutes -gt $grace) {
                Add-Condition $scope "lane-$name-unfinished" `
                    "Garmin sync มีรอบเริ่มแล้วไม่จบ" `
                    ("{0}: รอบ {1:d/M HH:mm} เริ่มแล้วไม่จบ (โดนปิด/เครื่องดับกลางทาง)" `
                        -f $STALE_LABEL[$name], $startAt)
            }
            # ยังอยู่ในช่วงที่รอบนี้อาจกำลังรันอยู่ — ไม่ต้องไปวัดอายุสถานะเก่าซ้ำ
            continue
        }

        # (2) สายที่ไม่มีรอบใหม่มานานเกินคาบ (สายที่ยังไม่เคยเดินเลย ไม่ต้องเตือน)
        if ($null -eq $runAt) { continue }
        if ($runAt -gt $now.AddMinutes(10)) {
            Add-Condition $scope "lane-$name-future" `
                "Garmin sync มีเวลาในอนาคต" `
                "$($STALE_LABEL[$name]): run_at อยู่ในอนาคต — เช็คนาฬิกาเครื่อง/ไฟล์สถานะ"
            continue
        }
        $ageMin = [int]($now - $runAt).TotalMinutes
        if ($ageMin -gt $STALE_LIMIT_MIN[$name]) {
            Add-Condition $scope "lane-$name-stale" `
                "Garmin sync มีสายที่หยุดเดิน" `
                ("$($STALE_LABEL[$name]): ไม่มีรอบใหม่เกินเพดานที่กำหนด" +
                 "`nเช็ค Task Scheduler + log C:\Backup\run-performance-logs\garmin-sync-*.log")
        }
    }

    # publisher ของ heartbeat — นับเฉพาะเวลาที่เครื่องตื่นจริง ความเงียบระหว่างหลับ
    # อธิบายตัวเองได้อยู่แล้ว ไม่ต้องเตือน
    $hbMarkerPath = Join-Path $DataDir $HEARTBEAT_MARKER
    $publishedAt = Read-TimeFile $hbMarkerPath
    if ((Test-Path $hbMarkerPath) -and $null -eq $publishedAt) {
        $observationComplete = $false
        Add-Condition $scope "heartbeat-marker-invalid" `
            "Garmin: heartbeat มี marker เสีย" `
            "$($HEARTBEAT_LABEL): อ่านเวลาส่งล่าสุดไม่ได้ — เปิด log"
    }
    elseif ($null -ne $publishedAt -and $awakeMin -gt $HEARTBEAT_STALE_LIMIT_MIN) {
        if ($publishedAt -gt $now.AddMinutes(10)) {
            Add-Condition $scope "heartbeat-future" `
                "Garmin: heartbeat มีเวลาในอนาคต" `
                "$($HEARTBEAT_LABEL): เวลาส่งล่าสุดอยู่ในอนาคต — เช็คนาฬิกาเครื่อง"
        }
        elseif (($now - $publishedAt).TotalMinutes -gt $HEARTBEAT_STALE_LIMIT_MIN) {
            Add-Condition $scope "heartbeat-stale" `
                "Garmin: heartbeat หยุดส่ง" `
                ("$($HEARTBEAT_LABEL): เครื่องตื่นมา $([int]$awakeMin) นาทีแล้วยังไม่มีรอบส่งใหม่" +
                 "`nเช็ค Task Scheduler งาน Run-Performance-SystemHealth")
        }
    }
    $script:ScopeComplete[$scope] = $observationComplete
}

try {
    $dataDir = if ($DataDir) { $DataDir }
               else { Join-Path (Split-Path $PSScriptRoot -Parent) "data" }
    # สถานะของสายตัวเอง — ไม่ระบุ -Lane (เช่นรันมือ) ค่อย fallback ไฟล์รวมแบบเดิม
    $lanePath = if ($Lane) { Join-Path (Join-Path $dataDir "sync_lane") "$Lane.json" } else { $null }
    $statusPath = if ($lanePath -and (Test-Path $lanePath)) { $lanePath }
                  else { Join-Path $dataDir "sync_status.json" }
    $startPath = Join-Path $dataDir $StartMarker

    if (-not $StaleOnly) {
        Test-Round $statusPath $startPath
        $roundScope = "round-" + $(if ($Lane) { $Lane } else { "manual" })
        Publish-Scope $roundScope $dataDir
    }
    if ($CheckStale) {
        Test-StaleLanes $dataDir
        Publish-Scope "stale" $dataDir
    }
} catch {
    Write-Output "notify_sync.ps1 error (ไม่กระทบ sync): $_"
}
exit 0
