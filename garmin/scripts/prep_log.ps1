# prep_log.ps1 — เตรียมไฟล์ log ของสาย sync หนึ่งสาย + เขียน start-marker ของรอบนี้
#
# ทำไมต้องมี (สำคัญ — นี่คือต้นตอ "ดึงไม่เสถียร" ที่เจอ 2 ส.ค. 69)
#   เดิมทุกสาย (full/fast/wellness/reconcile/deepsync) redirect ลง log ไฟล์เดียวกัน
#   cmd.exe เปิดไฟล์ redirect แบบหวงสิทธิ์ → สองงานชนกันเมื่อไหร่ อีกงาน "เปิดไฟล์ไม่ได้"
#   แล้ว **บรรทัดนั้นไม่ถูกรันเลย** ไม่ใช่แค่ log หาย → python ไม่ทำงาน ทั้งรอบหายเงียบ
#   (วัดจริง: สอง .bat เขียนพร้อมกัน บรรทัดหาย 94%; 2 ส.ค. full sync หายทั้งรอบ)
#   แก้ด้วย log แยกไฟล์ต่อสาย + ตัวนี้ดูแลหมุนไฟล์ไม่ให้โตไม่จำกัด
#
# ใช้: powershell -File scripts\prep_log.ps1 -LogPath <ไฟล์ log> [-Marker <ไฟล์ marker>]
# ถ้าเตรียม log/marker ไม่ได้ ต้องคืน non-zero ให้ Task Scheduler เห็นทันที
# ไฟล์นี้ต้องเซฟเป็น UTF-8 มี BOM (PS 5.1 อ่านไทยไม่มี BOM แล้ว parser พัง)

param(
    [Parameter(Mandatory = $true)][string]$LogPath,
    [string]$Marker = "",
    [int]$MaxMB = 5
)

$ErrorActionPreference = "Stop"

try {
    $dir = Split-Path -Parent $LogPath
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    # หมุนไฟล์เมื่อโตเกินกำหนด — เก็บรุ่นก่อนหน้าไว้ 1 ชุด (.1) พอสำหรับไล่ย้อนปัญหา
    if (Test-Path $LogPath) {
        if ((Get-Item $LogPath).Length -gt ($MaxMB * 1MB)) {
            $old = "$LogPath.1"
            if (Test-Path $old) { Remove-Item $old -Force }
            Move-Item $LogPath $old -Force
        }
    }

    # start-marker: เวลาเริ่มรอบนี้แบบ ISO — notify_sync ใช้ตัดสินว่า fetch_all
    # "เขียนสถานะรอบนี้จริงไหม" (ไม่ใช่เดาจากอายุไฟล์)
    if ($Marker) {
        (Get-Date).ToString("o") | Set-Content -NoNewline -Encoding ASCII -Path $Marker
    }
}
catch {
    Write-Error "prep_log failed: $($_.Exception.Message)"
    exit 1
}

exit 0
