# METRICS — แคตาล็อกตัวเลขทุกตัวที่ระบบเก็บ (ตรวจสอบย้อนกลับได้)

**เอกสารนี้ตอบคำถามเดียว:** ตัวเลขบน Dashboard แต่ละตัวมาจาก endpoint ไหน แปลงอะไรไปบ้าง อ้างอิงวันไหน สดแค่ไหน และตอนไม่มีค่าระบบบอกเราได้แค่ไหน
สร้างโดยอ่านโค้ด (`03_backfill.py`, `02_init_schema.py`, `dashboard*.py`, `app_pages/*.py`, `data_quality.py`, `check_drift.py`, `fetch_all.py`) และนับแถวใน `garmin/data/garmin.db` แบบ read-only — **ไม่ได้ยิง Garmin API** จึงข้อไหนต้องดู payload จริงจะเขียนว่า "ยังไม่ยืนยัน"

## ส่วนหัว: ตรวจเมื่อไหร่ นับอย่างไร

| รายการ | ค่า |
|---|---|
| วันที่ตรวจ | 2026-09-30 (อ่าน DB เวลา 2026-09-30 06:00 UTC = 13:00 น. Bangkok) |
| commit ของโค้ด | HEAD = `b62d62b` บน branch `refactor/garmin-only-intensity` — **มี commit ใหม่เข้ามาระหว่างที่เขียนเอกสารนี้** (19a9eb1 settle review → 2cc6374 intraday → b62d62b กราฟ intraday) เนื้อหาสะท้อนโค้ดถึง commit ที่ระบุ; ถ้า HEAD ไปไกลกว่านี้ให้ตรวจส่วน 'lane' และเลขบรรทัดใหม่ |
| ไลบรารี | `garminconnect` 0.3.11 (`garmin/uv.lock`) |
| หน้าต่าง coverage | 90 วันปฏิทิน Bangkok = 2026-07-03 .. 2026-09-30 (รวมวันนี้ที่ยังไม่จบ) |
| ตัวเลขเปลี่ยนเมื่อไหร่ | ทุกครั้งที่ sync รัน (fast 15 นาที / wellness 30 นาที) — อ่านเป็นภาพ ณ เวลาที่ระบุเท่านั้น |

**coverage = แถวที่ช่องนั้นไม่ใช่ NULL ÷ จำนวนแถวทั้งหมดของคนนั้นในหน้าต่าง** เรียงเป็น `tong · dan · p'kao` (ตัวหารเป็นจำนวน *แถว* ไม่ใช่จำนวนวัน — ถ้าวันไหนไม่มีแถวเลยจะไม่ถูกนับในตัวหาร) SQL ที่รันจริง (ต่อช่อง ต่อคน; เปิดด้วย `file:...garmin.db?mode=ro` + `PRAGMA query_only=ON`):

```sql
-- wellness / race_prediction / body_composition (date_col = calendar_date)
SELECT COUNT(*) AS total, COUNT(<column>) AS non_null
FROM <table>
WHERE athlete_id = ? AND calendar_date BETWEEN '2026-07-03' AND '2026-09-30';

-- fact_activity (นับเฉพาะกิจกรรมที่ยังไม่ถูกลบ)
SELECT COUNT(*), COUNT(<column>) FROM fact_activity
WHERE athlete_id = ? AND deleted_at IS NULL
  AND substr(start_time_local,1,10) BETWEEN '2026-07-03' AND '2026-09-30';

-- fact_activity_split (ผูกผ่านกิจกรรม)
SELECT COUNT(*), COUNT(s.<column>) FROM fact_activity_split s
JOIN fact_activity a ON a.activity_id = s.activity_id
WHERE a.athlete_id = ? AND a.deleted_at IS NULL
  AND substr(a.start_time_local,1,10) BETWEEN '2026-07-03' AND '2026-09-30';

-- fact_personal_record / fact_gear / dim_athlete_device: snapshot ไม่มีวันที่ → นับทั้งตารางต่อคน
SELECT COUNT(*), COUNT(<column>) FROM <table> WHERE athlete_id = ?;
```

ตารางกลุ่ม "ความสามารถของอุปกรณ์" (หัวข้อ 4) ใช้ SQL เดียวกันแต่ **ไม่จำกัดวันที่** (ทั้งประวัติ)

### คำย่อที่ใช้ในตาราง

| คำย่อ | ความหมาย |
|---|---|
| **A** | lane fast กิจกรรม: `fetch_all.py --days 0 --activities-only` ทุก 15 นาที (:05/:20/:35/:50) — ดึง summary ของวันนี้ + splits เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0; ไม่ดึง detail/weather; ค่าเดิมที่ full sync เคยเติมไม่ถูกทับด้วย NULL |
| **W** | lane wellness-fast: `--days 0 --wellness-fast` ทุก 30 นาที (:12/:42) — 4 endpoint ของ *วันนี้* (stats, HRV, sleep, readiness) + intraday HR/stress อีก 2 call (2cc6374) |
| **W\*** | W + งานของ *เมื่อวาน*: **repair** (ถ้าแถวเมื่อวานไม่ครบ พัก 6 ชม./ครั้ง) และ **settle review** (ตรวจซ้ำแม้ครบ ทุก 3 ชม. ภายใน 36 ชม. หลังวันจบ) ใช้ 5 endpoint = 4 ตัวข้างบน + `get_respiration_data` |
| **F** | lane full: `--days 3 --catch-up-slots 08:00,21:00` — ทำจริงวันละ 2 ครั้ง; ดึง **4 วันปฏิทิน** (today-3..today, เพราะลูปรวมวันแรกและวันสุดท้าย) ครบ 9 endpoint/วัน + activities + extras |
| **R** | lane reconcile: `--days 90 --reconcile` อาทิตย์ 09:30 — ดึงรายชื่อกิจกรรม 91 วัน; mark `deleted_at`/กู้คืน; นำเข้าเฉพาะกิจกรรมที่ DB ยังไม่มี (พร้อม detail/weather/splits) |
| **D** | lane deep: `--days 45 --skip-activities` ทุก 4 สัปดาห์ 10:30 — wellness + extras **46 วัน** (ไม่ดึงกิจกรรม) แล้วรัน `check_drift.py` |
| **N1** | `_bounded_number(value, min, max)`: ไม่ใช่ตัวเลข / bool / NaN / Inf / ต่ำกว่า min / สูงกว่า max → **NULL แบบเงียบ** (ไม่มี log ว่าถูกปัด) ตัวเลข 0 ที่อยู่ในช่วงถูกเก็บเป็น 0 |
| null-safe merge | wellness: `_insert_wellness_row`/`_update_wellness_fields` กรองค่า None ออกก่อนเขียน = ค่า NULL รอบใหม่ **ไม่ทับ** ค่าเดิม · activity/split/extras: `COALESCE(excluded.x, ตารางเดิม)` แบบเดียวกัน (ยกเว้น personal record ที่แทนทั้งแถว) |
| ไม่แสดง | ช่องนี้เก็บลง DB แต่ไม่มีหน้าไหนใน dashboard ปัจจุบันอ่าน (ตรวจด้วย grep ทุกไฟล์ใน `app_pages/` + `dashboard*.py`) |

**หน้า dashboard:** `team` = ทีม, `body` = ร่างกาย, `training` = การซ้อม, `estimates` = ค่าประเมิน Garmin, `session` = เซสชัน. **`latest_field`** = ค่าล่าสุดที่ไม่ใช่ NULL *ของช่องนั้นช่องเดียว* (เรียงตาม calendar_date → timestamp ต้นทางถ้ามี → fetched_at) พร้อมบอกวันของมัน; หน้า team ใช้ **แถวของวันที่เลือกวันเดียว** (`day_row`) ไม่หยิบข้ามวัน; กราฟวาดค่ารายวันดิบ วันที่ไม่มีข้อมูลเว้นว่าง (`calendar_aligned_frame`) ไม่มีการเฉลี่ย/เทียบฐาน/สูตรของระบบ ยกเว้นผลรวมหน้า training (ระยะวิ่ง = ผลบวก `distance_m` ของ RUN_TYPES, เวลา = ผลบวก `duration_sec` ทุกชนิด, จำนวนกิจกรรม, จำนวนวันที่มีกิจกรรม, นาทีโซน HR รายสัปดาห์เริ่มวันจันทร์)

### ค่าที่ **ระบบคำนวณเอง** (ไม่ใช่ตัวเลขดิบของ Garmin) — ตรวจสอบเป็นพิเศษ

| ช่อง | ที่ทำ | ผลกระทบ |
|---|---|---|
| `fact_activity.avg_pace_min_per_km` | `03_backfill.py` `fetch_and_insert_activities`: (duration/60)/(distance/1000) | เป็นเพซจาก *duration ÷ distance* ไม่ใช่เพซที่ Garmin รายงาน; ยังไม่เคยเทียบกับ Garmin Connect (เช็คลิสต์รายเดือนยังว่าง) |
| `fact_activity_split.avg_pace_min_km` | `fetch_and_insert_splits`: สูตรเดียวกัน | รอบสั้นควรอ่านจากเวลา (docs/PROJECT.md) |
| `lactate_threshold_pace_min_km` | `fetch_and_insert_extras`: 1000/speed/60 และถ้า speed<1 คูณ 10 | heuristic จากกรณีของ p'kao เคยเจอ 0.3306 |
| `weight_kg` | weight ÷ 1000 | สมมติว่า API ส่งกรัม |
| `weather_temp_c` / `weather_apparent_temp_c` | (F−32)×5/9 | API ส่ง °F |
| `recovery_time_min` | บังคับ 0 เมื่อ `recoveryTimeChangePhrase` = REACHED_ZERO | ตามวลีของ Garmin |
| `fitness_age` | ปัด 0.1 และเขียนลงแถว *วันที่รัน* | ไม่ใช่วันที่ Garmin วัด |
| `split_num` | นับ 1..n ตามลำดับที่ตอบมา | ไม่ใช่ `lapIndex` ของ Garmin |

---

## fact_daily_wellness

PK = (`athlete_id`, `calendar_date`). N (จำนวนแถว) ต่อคน tong · dan · p'kao = 90 · 90 · 90 — แถวถูกสร้างล่วงหน้าแม้ยังไม่มีค่า (`INSERT OR IGNORE`) จึงตัวหาร = 90 ทุกคน ไม่ได้แปลว่า "มีข้อมูล 90 วัน". `athlete_id`/`calendar_date` เป็นคีย์ ไม่ทำแถว

| column | ความหมาย | endpoint + JSON path | หน่วยต้นทาง → แสดง | วันที่อ้างอิง | timestamp ต้นทาง | lane | กฎ null/0 | การรวม/แสดงบน dashboard | coverage 90 วัน (tong · dan · p'kao) |
|---|---|---|---|---|---|---|---|---|---|
| `resting_hr` | Resting HR ของวัน | `get_stats` → `restingHeartRate` | bpm → bpm | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | W* F D | N1 [1,300] | team การ์ด · body ไทล์/กราฟ/ตาราง (ค่าล่าสุดรายช่อง) | 87/90 · 90/90 · 90/90 |
| `hrv_weekly_avg` | HRV เฉลี่ย 7 คืนที่ Garmin คำนวณ | `get_hrv_data` → `hrvSummary.weeklyAvg` (สำรอง `weeklyAvg`) | ms → ms | คืนที่จบเช้า D (ตามคอนเวนชัน Garmin/คำอธิบายบนการ์ดทีม โค้ดไม่ตรวจ) | – | W* F D | N1 [1,1000] | body กราฟเท่านั้น (ถอดจากการ์ดทีมแล้วใน 19a9eb1) | 75/90 · 84/90 · 89/90 |
| `hrv_last_night` | HRV เฉลี่ยคืนล่าสุด | `get_hrv_data` → `hrvSummary.lastNightAvg` (สำรอง `lastNightAvg`) | ms → ms | คืนที่จบเช้า D (ตามคอนเวนชัน Garmin/คำอธิบายบนการ์ดทีม โค้ดไม่ตรวจ) | – | W* F D | N1 [1,1000] | team การ์ด · body | 78/90 · 82/90 · 86/90 |
| `hrv_status` | สถานะ HRV ตามคำของ Garmin | `get_hrv_data` → `hrvSummary.status` (สำรอง `status`) | ข้อความ → `garmin_label` (ตัดเลขท้าย, Title Case) | คืนที่จบเช้า D (ตามคอนเวนชัน Garmin/คำอธิบายบนการ์ดทีม โค้ดไม่ตรวจ) | – | W* F D | `_clean_text` ≤100 ตัว | team การ์ด · body ตาราง | 78/90 · 87/90 · 89/90 |
| `sleep_score` | คะแนนการนอน | `get_sleep_data` → `dailySleepDTO.sleepScores.overall.value` (สำรอง `overallScore`, `sleepScores.overall.value`) | คะแนน 0–100 | คืนที่จบเช้า D (ตามคอนเวนชัน Garmin/คำอธิบายบนการ์ดทีม โค้ดไม่ตรวจ) | – | W* F D | N1 [0,100] | team · body | 78/90 · 82/90 · 86/90 |
| `sleep_duration_sec` | เวลานอนรวม | `get_sleep_data` → `dailySleepDTO.sleepTimeSeconds` | วินาที → `fmt_hours` | คืนที่จบเช้า D (ตามคอนเวนชัน Garmin/คำอธิบายบนการ์ดทีม โค้ดไม่ตรวจ) | – | W* F D | N1 [0,172800] | team การ์ด · body ตาราง | 78/90 · 82/90 · 86/90 |
| `deep_sleep_sec` | หลับลึก | `get_sleep_data` → `dailySleepDTO.deepSleepSeconds` | วินาที → ชั่วโมงในกราฟ | คืนที่จบเช้า D (ตามคอนเวนชัน Garmin/คำอธิบายบนการ์ดทีม โค้ดไม่ตรวจ) | – | W* F D | N1 [0,172800]; 0 เก็บเป็น 0 | body กราฟระยะการนอน | 78/90 · 82/90 · 86/90 |
| `light_sleep_sec` | หลับตื้น | `get_sleep_data` → `dailySleepDTO.lightSleepSeconds` | วินาที → ชั่วโมง | คืนที่จบเช้า D (ตามคอนเวนชัน Garmin/คำอธิบายบนการ์ดทีม โค้ดไม่ตรวจ) | – | W* F D | เหมือนกัน | body กราฟระยะการนอน | 78/90 · 82/90 · 86/90 |
| `rem_sleep_sec` | REM | `get_sleep_data` → `dailySleepDTO.remSleepSeconds` | วินาที → ชั่วโมง | คืนที่จบเช้า D (ตามคอนเวนชัน Garmin/คำอธิบายบนการ์ดทีม โค้ดไม่ตรวจ) | – | W* F D | เหมือนกัน (มีค่า 0 จริงในฐาน) | body กราฟระยะการนอน | 78/90 · 82/90 · 86/90 |
| `awake_sec` | เวลาตื่นระหว่างนอน | `get_sleep_data` → `dailySleepDTO.awakeSleepSeconds` | วินาที → ชั่วโมง | คืนที่จบเช้า D (ตามคอนเวนชัน Garmin/คำอธิบายบนการ์ดทีม โค้ดไม่ตรวจ) | – | W* F D | เหมือนกัน (มีค่า 0 จริงในฐาน) | body กราฟระยะการนอน | 78/90 · 82/90 · 86/90 |
| `body_battery_high` | Body Battery สูงสุดของวัน | `get_stats` → `bodyBatteryHighestValue` | ระดับ 5–100 | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response; วันนี้ยังขยับ | – | W* F D | N1 [5,100]; high/low เป็นคู่เดียวกัน — ค่าใดค่าหนึ่งไม่ผ่านหรือ high<low → ทิ้งทั้งคู่ | team (หมายเหตุใต้ BB) · body กราฟ | 88/90 · 90/90 · 90/90 |
| `body_battery_low` | Body Battery ต่ำสุดของวัน | `get_stats` → `bodyBatteryLowestValue` | ระดับ 5–100 | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response; วันนี้ยังขยับ | – | W* F D | เหมือน high | team · body กราฟ | 88/90 · 90/90 · 90/90 |
| `bb_at_wake` | Body Battery ตอนตื่น | `get_stats` → `bodyBatteryAtWakeTime` | ระดับ 5–100 | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | W* F D | N1 [5,100] | ไม่แสดง | 78/90 · 82/90 · 86/90 |
| `bb_charged` | Body Battery ที่ชาร์จเข้าทั้งวัน | `get_stats` → `bodyBatteryChargedValue` | หน่วยสะสม (ไม่ใช่ระดับ) | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | W* F D | N1 [0,1000] | body กราฟ | 88/90 · 90/90 · 90/90 |
| `bb_drained` | Body Battery ที่ใช้ไปทั้งวัน | `get_stats` → `bodyBatteryDrainedValue` | หน่วยสะสม | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | W* F D | N1 [0,1000] | body กราฟ | 88/90 · 90/90 · 90/90 |
| `bb_during_sleep` | Body Battery ที่เปลี่ยนระหว่างนอน | `get_stats` → `bodyBatteryDuringSleep` | หน่วยสะสม | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | W* F D | N1 [0,1000] | ไม่แสดง | 78/90 · 82/90 · 86/90 |
| `bb_most_recent` | Body Battery ณ การ sync ล่าสุด | `get_stats` → `bodyBatteryMostRecentValue` | ระดับ 5–100 | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response; ค่าของ 'ตอนนี้' สำหรับวันนี้ | – | W* F D | N1 [5,100] | team การ์ด (ค่าหลัก) · body ไทล์ | 88/90 · 90/90 · 90/90 |
| `stress_avg` | Stress เฉลี่ย | `get_stats` → `averageStressLevel` | 0–100 | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | W* F D | N1 [0,100] (ค่าติดลบของ Garmin → NULL) | team · body | 87/90 · 90/90 · 90/90 |
| `max_stress` | Stress สูงสุด | `get_stats` → `maxStressLevel` | 0–100 | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | W* F D | N1 [0,100] | team หมายเหตุ · body กราฟ | 87/90 · 90/90 · 90/90 |
| `steps` | จำนวนก้าว | `get_stats` → `totalSteps` | ก้าว | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response; วันนี้ยังสะสม | – | W* F D | N1 [0,1e6]; 0 เก็บเป็น 0 | team · body ตาราง | 88/90 · 90/90 · 90/90 |
| `steps_goal` | เป้าก้าวรายวัน | `get_stats` → `dailyStepGoal` | ก้าว | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | W* F D | N1 [0,1e6] | ไม่แสดง | 90/90 · 90/90 · 90/90 |
| `floors_ascended` | ชั้นที่ขึ้น | `get_stats` → `floorsAscended` | ชั้น | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | W* F D | N1 [0,10000] | ไม่แสดง | 90/90 · 90/90 · 90/90 |
| `active_kilocalories` | แคลอรี่กิจกรรม | `get_stats` → `activeKilocalories` | kcal | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | W* F D | N1 [0,100000] | ไม่แสดง | 90/90 · 90/90 · 90/90 |
| `bmr_kilocalories` | แคลอรี่พื้นฐาน | `get_stats` → `bmrKilocalories` | kcal | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | W* F D | N1 [0,100000] | ไม่แสดง | 90/90 · 90/90 · 90/90 |
| `active_seconds` | เวลาที่ active | `get_stats` → `activeSeconds` | วินาที | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | W* F D | N1 [0,86400] | ไม่แสดง | 90/90 · 90/90 · 90/90 |
| `avg_waking_respiration` | อัตราหายใจตอนตื่น | `get_stats` → `avgWakingRespirationValue` ก่อน, ไม่มีค่อยเติมจาก `get_respiration_data` → `avgWakingRespirationValue` | ครั้ง/นาที | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | W* F D | N1 [1,100] | body กราฟ | 87/90 · 90/90 · 90/90 |
| `avg_sleep_respiration` | อัตราหายใจตอนหลับ | `get_respiration_data` → `avgSleepRespirationValue` | ครั้ง/นาที | คืนที่จบเช้า D (ตามคอนเวนชัน Garmin/คำอธิบายบนการ์ดทีม โค้ดไม่ตรวจ) | – | F D (+W* เฉพาะเมื่อวาน) | N1 [1,100] | body กราฟ | 77/90 · 81/90 · 86/90 |
| `highest_respiration` | อัตราหายใจสูงสุด | `get_respiration_data` → `highestRespirationValue` | ครั้ง/นาที | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | F D (+W* เมื่อวาน) | N1 [1,100] | ไม่แสดง | 85/90 · 90/90 · 89/90 |
| `lowest_respiration` | อัตราหายใจต่ำสุด | `get_respiration_data` → `lowestRespirationValue` | ครั้ง/นาที | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | F D (+W* เมื่อวาน) | N1 [1,100] | ไม่แสดง | 85/90 · 90/90 · 89/90 |
| `training_readiness` | Training Readiness (ค่าประมาณของ Garmin) | `get_training_readiness` (list) → snapshot ที่ timestamp ใหม่สุด → `score` (สำรอง `trainingReadinessScore`) | คะแนน 0–100 | snapshot ล่าสุดของ D (เปลี่ยนระหว่างวัน) | `timestamp` → `readiness_timestamp_utc` | W* F D | N1 [0,100] | team (เฉพาะคนที่เคยได้รับ) · body ไทล์/กราฟ | 0/90 · 0/90 · 89/90 |
| `readiness_level` | ระดับของ Readiness | `get_training_readiness` → `level` | ข้อความ → `garmin_label` | เหมือน readiness | เหมือน readiness | W* F D | `_clean_text` ≤100 | team · body | 0/90 · 0/90 · 89/90 |
| `readiness_feedback` | ข้อความสั้นของ Garmin | `get_training_readiness` → `feedbackShort` | ข้อความ | เหมือน readiness | เหมือน readiness | W* F D | ≤500 ตัว | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `readiness_feedback_long` | ข้อความยาว | `get_training_readiness` → `feedbackLong` | ข้อความ | เหมือน readiness | เหมือน readiness | W* F D | ≤2000 ตัว | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `readiness_timestamp_utc` | เวลา snapshot ของ Readiness (UTC) | `get_training_readiness` → `timestamp` | epoch/ISO → ISO UTC มี Z (วินาที) | เวลาจริงของ snapshot | ตัวมันเองคือ timestamp ต้นทาง | W* F D | แปลงไม่ได้ → NULL (naive ถือเป็น UTC) | body ไทล์ ('dd/mm HH:MM UTC') · ใช้เรียงลำดับใน `latest_field` | 0/90 · 0/90 · 89/90 |
| `readiness_timestamp_local` | เวลา snapshot (เวลาท้องถิ่นตาม Garmin) | `get_training_readiness` → `timestampLocal` | ข้อความตามที่ส่งมา (ไม่แปลง) | เหมือนข้างบน | ตัวมันเอง | W* F D | `_clean_text` ≤100 | body ไทล์ ('dd/mm HH:MM น.') — เลือกก่อน utc | 0/90 · 0/90 · 89/90 |
| `readiness_input_context` | บริบทที่ Garmin ใช้คำนวณ | `get_training_readiness` → `inputContext` | ข้อความ | เหมือน readiness | – | W* F D | ≤200 ตัว | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `readiness_device_id` | ID เครื่องที่ส่ง snapshot | `get_training_readiness` → `deviceId` | ID | เหมือน readiness | – | W* F D | ≤100 ตัว; ห้ามขึ้นรายงาน | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `readiness_sleep_factor_pct` | ปัจจัยการนอนต่อ Readiness | `get_training_readiness` → `sleepScoreFactorPercent` | % 0–100 | เหมือน readiness | – | W* F D | N1 [0,100] | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `readiness_sleep_factor_feedback` | ข้อความปัจจัยการนอน | → `sleepScoreFactorFeedback` | ข้อความ | เหมือน readiness | – | W* F D | ≤500 ตัว | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `acute_load` | Acute Load ที่ Garmin ใช้ใน Readiness | → `acuteLoad` | หน่วย Garmin | เหมือน readiness | – | W* F D | N1 [0,100000] | ไม่แสดง (ถอดตามนโยบาย 30 ก.ย. 69) | 0/90 · 0/90 · 89/90 |
| `acwr_percent` | สัดส่วนปัจจัย 'acute:chronic' ใน Readiness (ไม่ใช่อัตราส่วน ACWR) | → `acwrFactorPercent` | % 0–100 | เหมือน readiness | – | W* F D | N1 [0,100] | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `acwr_factor_feedback` | ข้อความปัจจัยข้างบน | → `acwrFactorFeedback` | ข้อความ | เหมือน readiness | – | W* F D | ≤500 ตัว | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `hrv_factor_pct` | ปัจจัย HRV ต่อ Readiness | → `hrvFactorPercent` | % 0–100 | เหมือน readiness | – | W* F D | N1 [0,100] | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `hrv_factor_feedback` | ข้อความปัจจัย HRV | → `hrvFactorFeedback` | ข้อความ | เหมือน readiness | – | W* F D | ≤500 ตัว | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `recovery_time_min` | Recovery Time | → `recoveryTime`; ถ้า `recoveryTimeChangePhrase`='REACHED_ZERO' บังคับเป็น 0 | นาที → `fmt_recovery_time` (ชม./นาที) | เหมือน readiness | – | W* F D | N1 [0,5760]; 0 = ฟื้นครบ (ตามวลีของ Garmin) ไม่ใช่ 'ไม่มีค่า' | team การ์ด (บรรทัด Garmin words) | 0/90 · 0/90 · 89/90 |
| `recovery_time_factor_pct` | ปัจจัย Recovery ต่อ Readiness | → `recoveryTimeFactorPercent` | % 0–100 | เหมือน readiness | – | W* F D | N1 [0,100] | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `recovery_time_factor_feedback` | ข้อความปัจจัย Recovery | → `recoveryTimeFactorFeedback` | ข้อความ | เหมือน readiness | – | W* F D | ≤500 ตัว | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `recovery_time_change_phrase` | วลีการเปลี่ยนของ Recovery | → `recoveryTimeChangePhrase` | ข้อความ | เหมือน readiness | – | W* F D | ≤200 ตัว | ไม่แสดง | 0/90 · 0/90 · 81/90 |
| `stress_history_pct` | ปัจจัย Stress history ต่อ Readiness | → `stressHistoryFactorPercent` | % 0–100 | เหมือน readiness | – | W* F D | N1 [0,100] | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `stress_history_factor_feedback` | ข้อความปัจจัย Stress | → `stressHistoryFactorFeedback` | ข้อความ | เหมือน readiness | – | W* F D | ≤500 ตัว | ไม่แสดง | 0/90 · 0/90 · 89/90 |
| `training_status` | Training Status (ข้อความของ Garmin) | `get_training_status` → `mostRecentTrainingStatus.latestTrainingStatusData.<deviceId>.trainingStatusFeedbackPhrase` (สำรอง `.trainingStatus`, แล้ว `trainingStatus`/`currentDayTrainingStatus` ระดับบน); เลือกเครื่องแรกใน dict ที่มีค่า | ข้อความ → `garmin_label` | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | F D | ≤500 ตัว; ไม่มีค่า → NULL | team บรรทัด Garmin words · body ตาราง | 0/90 · 0/90 · 89/90 |
| `vo2max_trend` | VO2max รายวัน (generic/วิ่ง) | `get_max_metrics` → รายการ → `generic.vo2MaxPreciseValue` (สำรอง `vo2MaxValue`) | ml/kg/min | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response; Garmin อัปเดตเฉพาะวันที่มีวิ่ง outdoor เข้าเกณฑ์ | – | F D | N1 [1,150] | estimates ไทล์/กราฟ | 59/90 · 60/90 · 3/90 |
| `fitness_age` | Fitness Age | `get_fitnessage_data(end_date)` → `fitnessAge` (ถ้ามี `invalidReason` ไม่เขียน) | ปี (ปัด 0.1) | **วันที่รัน (end_date)** ไม่ใช่วันที่ Garmin วัด | – | F D | N1 [1,120]; ต้อง=USER_UNDER_AGE (คอมเมนต์ในโค้ด) | estimates ไทล์ | 0/90 · 56/90 · 56/90 |
| `endurance_score` | Endurance Score | `get_endurance_score(D)` → `overallScore` | คะแนน | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | F D | N1 [0,100000] | estimates ไทล์ | 0/90 · 0/90 · 89/90 |
| `hill_score_overall` | Hill Score รวม | `get_hill_score(D)` → `overallScore` | คะแนน | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | F D | N1 [0,100] | estimates ไทล์ | 0/90 · 0/90 · 85/90 |
| `hill_score_strength` | Hill Score ด้านแรง | `get_hill_score(D)` → `strengthScore` | คะแนน | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | F D | N1 [0,100] | ไม่แสดง | 0/90 · 0/90 · 85/90 |
| `hill_score_endurance` | Hill Score ด้านทน | `get_hill_score(D)` → `enduranceScore` | คะแนน | ตามคำขอ D (วัน Bangkok) — ไม่อ่านวันจาก response | – | F D | N1 [0,100] | ไม่แสดง | 0/90 · 0/90 · 85/90 |
| `lactate_threshold_hr` | HR ที่ Lactate Threshold | `get_lactate_threshold(latest=True)` → `speed_and_heart_rate.heartRate` | bpm | แถวของ `speed_and_heart_rate.calendarDate` (วันที่ Garmin วัด) เฉพาะค่า 'ล่าสุด' ค่าเดียว | `calendarDate` ใช้เป็นคีย์แถว | F D | N1 [1,300]; ไม่มี calendarDate → ไม่เขียน | estimates ไทล์ (latest_field) | 0/90 · 0/90 · 3/90 |
| `lactate_threshold_pace_min_km` | เพซที่ Lactate Threshold | เดียวกัน → `speed_and_heart_rate.speed` (ถ้า <1 คูณ 10) แล้ว **ระบบคำนวณ** 1000/speed/60 | m/s → นาที/กม. (ทศนิยม) → M:SS | เหมือนข้างบน | เหมือนข้างบน | F D | speed N1 [0.01,20]; pace N1 [1,30] | estimates ไทล์ | 0/90 · 0/90 · 3/90 |
| `repair_attempted_at_utc` | เวลาที่ระบบพยายามซ่อมเมื่อวานล่าสุด (นาฬิกาของเรา) | – (metadata ของระบบ) | ISO UTC Z | – | นาฬิการะบบ | W (เมื่อวาน) | บันทึกเมื่อ endpoint หลักไม่ล้มทั้งหมด; ไม่ได้พิสูจน์ว่าได้ค่าครบ | ไม่แสดง | 14/90 · 2/90 · 3/90 |
| `settle_reviewed_at_utc` | เวลาตรวจทานเมื่อวานซ้ำล่าสุด (settle review) | – (metadata; เพิ่มใน 19a9eb1) | ISO UTC Z | – | นาฬิการะบบ | W (เมื่อวาน ทุก 3 ชม. ภายใน 36 ชม.) | โค้ดข้ามเงียบถ้าคอลัมน์ยังไม่มีใน DB | ไม่แสดง | ไม่มีคอลัมน์ใน DB จริง |
| `fetched_at` | เวลา UTC ที่แถวถูกเขียนล่าสุด (ระดับแถว — ดูหัวข้อ 2) | – (ระบบ) `strftime('%Y-%m-%dT%H:%M:%fZ','now')` | ISO UTC Z ms → เวลาไทย 'dd/mm HH:MM น.' | – | นาฬิการะบบ | ทุก lane ที่เขียนแถว | ตั้งใหม่ทุกครั้งที่เขียน ≥1 ค่า (ยกเว้น settle review ที่ไม่มีอะไรเปลี่ยน) | team การ์ด (แถวของวันที่เลือก) · sidebar = MAX ทั้งทีม | 90/90 · 90/90 · 90/90 |

**หมายเหตุอ่านตาราง wellness**

- คอลัมน์ `settle_reviewed_at_utc` ถูกเพิ่มใน `02_init_schema.py` เมื่อ commit `19a9eb1` แต่ **DB จริงยังไม่มีคอลัมน์นี้** (ตรวจ ณ เวลาข้างบน: ไม่มี) — ไม่มีตัวไหนรัน `02_init_schema.py` ให้อัตโนมัติ (grep: มีแค่การเรียกด้วยมือ) โค้ด `_settle_review_due` จึงคืน False เงียบ ๆ = **settle review ยังไม่ทำงานจริง** จนกว่าจะรัน `02_init_schema.py` ทางแก้: รันสคริปต์นั้นหนึ่งครั้ง (idempotent, เพิ่มคอลัมน์อย่างเดียว)
- กลุ่มการนอนทั้งชุด (`sleep_*`, `hrv_last_night`, `bb_at_wake`, `bb_during_sleep`) มี coverage เท่ากันเป๊ะต่อคน = มาพร้อมกัน/หายพร้อมกัน สอดคล้องกับคำอธิบายใน docs/PROJECT.md ว่าเป็น "ข้อมูลกลางคืนไม่มา"
- ชื่อคอลัมน์ `acwr_percent` ชวนเข้าใจผิด: ไม่ใช่ ACWR ratio แต่เป็น **สัดส่วนปัจจัยของ Readiness** (`acwrFactorPercent`) — Dashboard ไม่แสดงตามนโยบาย 30 ก.ย. 69

## fact_wellness_intraday

PK = (`athlete_id`, `metric`, `ts_utc`) — จุดละราว 2–3 นาทีของ HR / Stress / Body Battery (ตามที่ docstring ของ `intraday.py` ประมาณไว้ ยังไม่มีข้อมูลจริงให้นับ) เก็บ 180 วัน (`INTRADAY_RETENTION_DAYS`) ลบด้วย `prune` ตอน F/D; **เพิ่มใน commit `2cc6374` และกราฟขึ้นหน้าเว็บใน `b62d62b`** ส่วนตารางนี้ **ยังไม่มีใน DB จริง** ณ เวลาตรวจ. ตารางนี้ไม่มี N ให้นับ coverage ต่อคน เพราะเก็บเป็นแถวต่อจุด (metric อยู่ในคอลัมน์ `metric`) — ตัวหารที่มีความหมายคือจำนวนจุดที่คาดต่อวัน ซึ่งขึ้นกับนาฬิกา

| column | ความหมาย | endpoint + JSON path | หน่วยต้นทาง → แสดง | วันที่อ้างอิง | timestamp ต้นทาง | lane | กฎ null/0 | การรวม/แสดงบน dashboard | coverage 90 วัน (tong · dan · p'kao) |
|---|---|---|---|---|---|---|---|---|---|
| `athlete_id / metric / ts_utc` | คีย์: คน · ชนิด (`heart_rate`, `stress`, `body_battery`) · เวลาของจุด | – | – | – | `ts_utc` คือ timestamp ต้นทางระดับจุด | W (วันนี้ ทุก 30 นาที) · F D (เมื่อวาน 1 ครั้ง/รอบ + prune >180 วัน) | จุดเดิม (คีย์เดียวกัน) ถูกเขียนทับทุกรอบ | กราฟ 'ระหว่างวัน' (body) และ 'เทียบระหว่างวันทั้งทีม' (team) | ตารางยังไม่มีใน DB จริง (ยังไม่รัน `02_init_schema.py`) = 0 แถว |
| `calendar_date` | วันปฏิทินของจุด | `get_heart_rates` / `get_stress_data` → `calendarDate` | YYYY-MM-DD | `calendar_date` = `calendarDate` ของ payload (สำรอง: วันที่ที่ขอ) ต่างจากตารางรายวันที่ใช้วันที่ขออย่างเดียว | – | W (วันนี้ ทุก 30 นาที) · F D (เมื่อวาน 1 ครั้ง/รอบ + prune >180 วัน) | รูปแบบผิด/ไม่มี → ใช้วันที่ที่ขอ | ใช้กรองวัน (`load_intraday`) | ตารางยังไม่มีใน DB จริง (ยังไม่รัน `02_init_schema.py`) = 0 แถว |
| `ts_utc (heart_rate)` | เวลาของจุด HR | `get_heart_rates` → `heartRateValues[]` (คู่ [timestamp ms, ค่า] หาตำแหน่งจาก `heartRateValueDescriptors` key `timestamp`/`heartrate`) | epoch ms → ISO UTC Z (วินาที) → เวลาไทยแบบ naive ตอนแสดง | – | ตัวมันเอง | W (วันนี้ ทุก 30 นาที) · F D (เมื่อวาน 1 ครั้ง/รอบ + prune >180 วัน) | ไม่ใช่ตัวเลขบวก → ข้ามจุด | กราฟแกน 00:00–24:00 ไทย | ตารางยังไม่มีใน DB จริง (ยังไม่รัน `02_init_schema.py`) = 0 แถว |
| `value (heart_rate)` | HR รายจุด | → ค่าที่สอง (`heartrate`) | bpm | – | ts_utc | W (วันนี้ ทุก 30 นาที) · F D (เมื่อวาน 1 ครั้ง/รอบ + prune >180 วัน) | **≤0 หรือไม่ใช่ตัวเลข → NULL (ไม่ใช่ 0)**; ไม่มี upper bound | กราฟ HR; เส้นขาดเมื่อจุดห่าง >15 นาที (`INTRADAY_GAP_MINUTES`) | ตารางยังไม่มีใน DB จริง (ยังไม่รัน `02_init_schema.py`) = 0 แถว |
| `value (stress)` | Stress รายจุด | `get_stress_data` → `stressValuesArray[]` (descriptors `stressValueDescriptorsDTOList` key `timestamp`/`stressLevel`) | 0–100 ตามที่ Garmin ส่ง (ไม่มี upper bound ในโค้ด) | – | ts_utc | W (วันนี้ ทุก 30 นาที) · F D (เมื่อวาน 1 ครั้ง/รอบ + prune >180 วัน) | **ค่าลบ = รหัสของ Garmin (วัดไม่ได้/ทำกิจกรรม) → value NULL + เก็บรหัสดิบใน `source_code`**; 0 เก็บเป็น 0 | กราฟ Stress | ตารางยังไม่มีใน DB จริง (ยังไม่รัน `02_init_schema.py`) = 0 แถว |
| `value (body_battery)` | Body Battery รายจุด | `get_stress_data` → `bodyBatteryValuesArray[]` (descriptors `bodyBatteryValueDescriptorsDTOList`, index/key แบบ `bodyBatteryValueDescriptorIndex`/`Key` = `timestamp`/`bodyBatteryLevel`) | ระดับ 0–100 | – | ts_utc | W (วันนี้ ทุก 30 นาที) · F D (เมื่อวาน 1 ครั้ง/รอบ + prune >180 วัน) | **นอก 0–100 → NULL**; ช่วง 0–100 กว้างกว่ารายวันที่ใช้ 5–100 | กราฟ Body Battery | ตารางยังไม่มีใน DB จริง (ยังไม่รัน `02_init_schema.py`) = 0 แถว |
| `source_code` | รหัสลบของ Garmin เมื่อ stress วัดไม่ได้ | → `stressLevel` (ติดลบ) เป็นจำนวนเต็ม | รหัสดิบ | – | – | W (วันนี้ ทุก 30 นาที) · F D (เมื่อวาน 1 ครั้ง/รอบ + prune >180 วัน) | ใช้กับ stress เท่านั้น อื่น ๆ NULL | ไม่แสดง (กราฟดูแต่ value) | ตารางยังไม่มีใน DB จริง (ยังไม่รัน `02_init_schema.py`) = 0 แถว |
| `fetched_at` | เวลา UTC ที่จุดถูก upsert ล่าสุด | – (ระบบ) | ISO UTC Z ms | – | นาฬิการะบบ | W (วันนี้ ทุก 30 นาที) · F D (เมื่อวาน 1 ครั้ง/รอบ + prune >180 วัน) | **ทุกรอบ W เขียนทับทั้งวัน จึงเลื่อน fetched_at ของทุกจุดแม้ค่าเท่าเดิม** | ไม่แสดง | ตารางยังไม่มีใน DB จริง (ยังไม่รัน `02_init_schema.py`) = 0 แถว |

คุณสมบัติที่ต่างจากตารางรายวัน: (1) **เป็นตารางเดียวที่มี timestamp ต้นทางระดับจุด** จึงตอบได้จริงว่า 'จุด HR/Stress/Body Battery ล่าสุดจากนาฬิกาคือเวลาไหน' ด้วย `MAX(ts_utc)` (2) อ่าน `calendarDate` จาก payload (ตารางรายวันไม่ตรวจ) (3) ตรวจตำแหน่งคอลัมน์จาก descriptor key ทุกครั้ง; key หาย → ไม่เก็บ metric นั้นและบันทึก failure reason `payload` (4) array ว่าง = 'ไม่มีข้อมูล' ไม่ใช่ failure — ตรงกับสถานะ 'ยังไม่ได้รับ' อย่างชัดเจนกว่าตารางรายวัน; และ `getattr(garmin, endpoint, None)` ไม่มี → ข้ามเงียบ (ไม่ใช่ schema drift) (5) ค่าบน dashboard เป็นเวลา Asia/Bangkok แบบ naive ผ่าน `tz_convert("Asia/Bangkok")` ใน `dashboard_data.load_intraday` (อีกจุดที่เขียนชื่อโซนเป็นข้อความ)

## fact_activity

PK = `activity_id`. N (จำนวนแถว) ต่อคน tong · dan · p'kao = 139 · 175 · 67 (เฉพาะแถว `deleted_at IS NULL` ในหน้าต่าง). ทุกฟิลด์ที่มาจาก `get_activities_by_date` อ่านตรง ๆ จาก `act.get(...)` **โดยไม่มี bounds/sentinel filter** (ต่างจาก wellness) — ค่าแปลก ๆ จะเข้า DB ตามที่ Garmin ส่ง. `athlete_id` เป็นคีย์อ้างอิง

| column | ความหมาย | endpoint + JSON path | หน่วยต้นทาง → แสดง | วันที่อ้างอิง | timestamp ต้นทาง | lane | กฎ null/0 | การรวม/แสดงบน dashboard | coverage 90 วัน (tong · dan · p'kao) |
|---|---|---|---|---|---|---|---|---|---|
| `activity_id` | รหัสกิจกรรมของ Garmin (PK) | `get_activities_by_date` → `activityId` | จำนวนเต็ม | – | – | A F R(รายการใหม่) | ต้องเป็นจำนวนเต็ม 1..2^63-1 ไม่งั้นทั้งรอบล้ม (`InvalidEndpointPayloadError`) | ใช้เป็นคีย์เปิด splits | 139/139 · 175/175 · 67/67 |
| `activity_type` | ชนิดกิจกรรม | → `activityType.typeKey` | ข้อความ | – | – | A F R(รายการใหม่) | ไม่มี → '' | กรองชนิดวิ่ง (`RUN_TYPES`: running/track/trail/treadmill) ใน training | 139/139 · 175/175 · 67/67 |
| `activity_name` | ชื่อที่นักกีฬา/Garmin ตั้ง | → `activityName` | ข้อความ | – | – | A F R(รายการใหม่) | COALESCE | ทุกตารางกิจกรรม (`activity_title`) | 139/139 · 175/175 · 67/67 |
| `start_time_local` | เวลาเริ่ม (local) | → `startTimeLocal` | ข้อความ 'YYYY-MM-DD HH:MM:SS' ไม่มีโซน | **คือวันที่อ้างอิงของกิจกรรม** | ตัวมันเอง | A F R(รายการใหม่) | COALESCE | กรองช่วงวัน · แสดง 'dd/mm HH:MM' | 139/139 · 175/175 · 67/67 |
| `start_time_utc` | เวลาเริ่ม (GMT) | → `startTimeGMT` | ข้อความ 'YYYY-MM-DD HH:MM:SS' (GMT) | – | ตัวมันเอง | A F R(รายการใหม่) | COALESCE | ไม่แสดง | 139/139 · 175/175 · 67/67 |
| `duration_sec` | ระยะเวลากิจกรรม | → `duration` | วินาที → `fmt_sec` | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ ไม่มี bounds | ทุกหน้า · training รวมเวลา (ทุกชนิด) | 139/139 · 175/175 · 67/67 |
| `moving_duration_sec` | เวลาเคลื่อนที่ | → `movingDuration` | วินาที | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 139/139 · 175/175 · 67/67 |
| `distance_m` | ระยะทาง | → `distance` | เมตร → km | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ; 0 เก็บเป็น 0 (หลาย session ในร่ม) | ทุกหน้า · training รวมเฉพาะ RUN_TYPES | 139/139 · 175/175 · 66/67 |
| `avg_hr` | HR เฉลี่ย | → `averageHR` | bpm | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | ทุกหน้า | 139/139 · 174/175 · 67/67 |
| `max_hr` | HR สูงสุด | → `maxHR` | bpm | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | training ตาราง · session | 139/139 · 174/175 · 67/67 |
| `min_hr` | HR ต่ำสุด | `get_activity(id)` → `summaryDTO.minHR` | bpm | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | F R(รายการใหม่) — เฉพาะกิจกรรมที่ type มีคำว่า running | ล้มเหลว/ไม่มี → NULL; fast lane คงค่าเดิมไว้ | แสดงเฉพาะ session | 136/139 · 165/175 · 33/67 |
| `avg_pace_min_per_km` | เพซเฉลี่ย **ที่ระบบคำนวณ** | (duration/60)/(distance/1000) ปัด 2 ตำแหน่ง จาก `duration` และ `distance` (ไม่ใช่ค่าเพซของ Garmin) | นาที/กม. ทศนิยม → M:SS | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | NULL ถ้า duration หรือ distance เป็น 0/ว่าง | team · training ตาราง · session | 136/139 · 165/175 · 34/67 |
| `avg_speed_mps` | ความเร็วเฉลี่ย | → `averageSpeed` | m/s → km/h (×3.6) | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 139/139 · 175/175 · 66/67 |
| `max_speed_mps` | ความเร็วสูงสุด | → `maxSpeed` | m/s → km/h | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 136/139 · 165/175 · 34/67 |
| `avg_grade_adjusted_speed_mps` | ความเร็วปรับความชัน | → `avgGradeAdjustedSpeed` | m/s → km/h | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 133/139 · 164/175 · 6/67 |
| `calories` | แคลอรี่ | → `calories` | kcal | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 139/139 · 175/175 · 67/67 |
| `bmr_calories` | แคลอรี่พื้นฐานช่วงกิจกรรม | → `bmrCalories` | kcal | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | ไม่แสดง | 139/139 · 175/175 · 66/67 |
| `training_effect_aerobic` | Aerobic Training Effect | → `aerobicTrainingEffect` | 0–5 | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | training ตาราง · session | 139/139 · 175/175 · 67/67 |
| `training_effect_anaerobic` | Anaerobic Training Effect | → `anaerobicTrainingEffect` | 0–5 | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | 0 เป็นค่าจริงที่พบบ่อย | แสดงเฉพาะ session | 139/139 · 175/175 · 67/67 |
| `training_effect_label` | ผลการซ้อมตามคำ Garmin | → `trainingEffectLabel` | ข้อความ → `garmin_label` | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 139/139 · 175/175 · 67/67 |
| `vo2max_value` | VO2max ที่กิจกรรมนี้ประเมิน | → `vO2MaxValue` | ml/kg/min | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 95/139 · 109/175 · 6/67 |
| `avg_cadence` | Cadence เฉลี่ย | → `averageRunningCadenceInStepsPerMinute` | spm | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 137/139 · 165/175 · 34/67 |
| `max_cadence` | Cadence สูงสุด | → `maxRunningCadenceInStepsPerMinute` | spm | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 137/139 · 165/175 · 34/67 |
| `avg_stride_length_cm` | ความยาวก้าว | → `avgStrideLength` | cm (ตามชื่อคอลัมน์ ยังไม่ได้ตรวจกับ payload) | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 137/139 · 165/175 · 34/67 |
| `avg_ground_contact_time_ms` | Ground Contact Time | → `avgGroundContactTime` | ms | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 135/139 · 165/175 · 33/67 |
| `avg_vertical_oscillation_cm` | Vertical Oscillation | → `avgVerticalOscillation` | cm | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 136/139 · 165/175 · 33/67 |
| `avg_vertical_ratio` | Vertical Ratio | → `avgVerticalRatio` | % | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 136/139 · 165/175 · 33/67 |
| `elevation_gain_m` | ไต่ขึ้น | → `elevationGain` | m | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | 0 เป็นค่าจริง | แสดงเฉพาะ session | 135/139 · 164/175 · 7/67 |
| `elevation_loss_m` | ลดระดับ | → `elevationLoss` | m | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | 0 เป็นค่าจริง | แสดงเฉพาะ session | 135/139 · 164/175 · 7/67 |
| `min_elevation_m` | จุดต่ำสุด | → `minElevation` | m | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 135/139 · 164/175 · 7/67 |
| `max_elevation_m` | จุดสูงสุด | → `maxElevation` | m | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 135/139 · 164/175 · 7/67 |
| `avg_power` | Power เฉลี่ย | → `avgPower` | W | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 136/139 · 165/175 · 33/67 |
| `max_power` | Power สูงสุด | → `maxPower` | W | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 136/139 · 165/175 · 33/67 |
| `normalized_power` | Normalized Power | → `normPower` | W | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 136/139 · 165/175 · 33/67 |
| `training_load` | Training Load ของกิจกรรม (Garmin) | → `activityTrainingLoad` | หน่วย Garmin | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | training กราฟ/ตาราง · session | 0/139 · 0/175 · 67/67 |
| `impact_load` | Impact Load | `get_activity(id)` → `summaryDTO.impactLoad` | หน่วย Garmin | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | F R(รายการใหม่) — เฉพาะกิจกรรมที่ type มีคำว่า running | ล้มเหลว/ไม่มี → NULL | แสดงเฉพาะ session | 0/139 · 0/175 · 33/67 |
| `begin_stamina` | Stamina ตอนเริ่ม | `get_activity(id)` → `summaryDTO.beginPotentialStamina` | % | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | F R(รายการใหม่) — เฉพาะกิจกรรมที่ type มีคำว่า running | ล้มเหลว/ไม่มี → NULL | แสดงเฉพาะ session | 0/139 · 0/175 · 33/67 |
| `end_stamina` | Stamina ตอนจบ | `get_activity(id)` → `summaryDTO.endPotentialStamina` | % | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | F R(รายการใหม่) — เฉพาะกิจกรรมที่ type มีคำว่า running | ล้มเหลว/ไม่มี → NULL | แสดงเฉพาะ session | 0/139 · 0/175 · 33/67 |
| `hr_zone1_sec` | เวลาในโซน HR 1 | → `hrTimeInZone_1` | วินาที → นาที | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | 0 เก็บเป็น 0 | training กราฟรายสัปดาห์ (sum) · session | 139/139 · 174/175 · 67/67 |
| `hr_zone2_sec` | โซน 2 | → `hrTimeInZone_2` | วินาที → นาที | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | เหมือนกัน | เหมือนกัน | 139/139 · 174/175 · 67/67 |
| `hr_zone3_sec` | โซน 3 | → `hrTimeInZone_3` | วินาที → นาที | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | เหมือนกัน | เหมือนกัน | 139/139 · 174/175 · 67/67 |
| `hr_zone4_sec` | โซน 4 | → `hrTimeInZone_4` | วินาที → นาที | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | เหมือนกัน | เหมือนกัน | 139/139 · 174/175 · 67/67 |
| `hr_zone5_sec` | โซน 5 | → `hrTimeInZone_5` | วินาที → นาที | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | เหมือนกัน | เหมือนกัน | 139/139 · 174/175 · 67/67 |
| `steps` | ก้าวระหว่างกิจกรรม | → `steps` | ก้าว | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | ไม่แสดง | 139/139 · 175/175 · 65/67 |
| `moderate_intensity_min` | นาทีหนักปานกลาง | → `moderateIntensityMinutes` | นาที | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 138/139 · 171/175 · 66/67 |
| `vigorous_intensity_min` | นาทีหนักมาก | → `vigorousIntensityMinutes` | นาที | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 138/139 · 171/175 · 66/67 |
| `diff_body_battery` | Body Battery ที่ใช้ไปในกิจกรรม | → `differenceBodyBattery` | หน่วย Body Battery | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 139/139 · 170/175 · 66/67 |
| `sweat_loss_ml` | เหงื่อ (ประมาณ) | → `waterEstimated` | ml (ตามชื่อคอลัมน์ ยังไม่ได้ตรวจ) | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 139/139 · 175/175 · 66/67 |
| `start_latitude` | พิกัดเริ่ม (lat) | → `startLatitude` | องศา | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ไม่มี = ในร่ม/ไม่มี GPS | แสดงเฉพาะ session | 135/139 · 164/175 · 6/67 |
| `start_longitude` | พิกัดเริ่ม (lon) | → `startLongitude` | องศา | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | เหมือนกัน | แสดงเฉพาะ session | 135/139 · 164/175 · 6/67 |
| `location_name` | ชื่อสถานที่ | → `locationName` | ข้อความ | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | A F R(รายการใหม่) | ผ่านค่าดิบ | แสดงเฉพาะ session | 135/139 · 164/175 · 6/67 |
| `weather_temp_c` | อุณหภูมิ | `get_activity_weather(id)` → `temp` (°F) แล้ว **ระบบแปลง** (F−32)×5/9 ปัด 0.1 | °F → °C | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | F R(รายการใหม่) — เฉพาะวิ่งที่มี `startLatitude` | ไม่ใช่ตัวเลข → NULL | แสดงเฉพาะ session | 135/139 · 163/175 · 6/67 |
| `weather_apparent_temp_c` | อุณหภูมิที่รู้สึก | → `apparentTemp` (°F → °C) | °F → °C | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | เหมือนข้างบน | เหมือนข้างบน | ไม่แสดง | 135/139 · 163/175 · 6/67 |
| `weather_humidity` | ความชื้น | → `relativeHumidity` | % (ผ่านค่าดิบ) | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | เหมือนข้างบน | ผ่านค่าดิบ | แสดงเฉพาะ session | 125/139 · 151/175 · 5/67 |
| `weather_wind_kph` | ความเร็วลม | → `windSpeed` **ไม่แปลงหน่วย** | ไม่ทราบ (ชื่อคอลัมน์และหน้าเว็บบอก km/h; อุณหภูมิมาเป็น °F จึงสงสัยว่าอาจเป็น mph — ยังไม่ยืนยัน) | วันที่ของ `start_time_local` (เวลาท้องถิ่นของนาฬิกา ณ ตอนเริ่ม) | – | เหมือนข้างบน | ผ่านค่าดิบ | session 'ลม ... km/h' | 135/139 · 163/175 · 6/67 |
| `deleted_at` | เวลาที่ reconcile พบว่ากิจกรรมถูกลบฝั่ง Garmin | – (ระบบ) `datetime.now()` เวลาเครื่อง (naive) | ISO ไม่มีโซน | – | นาฬิกาเครื่อง | F R (reconcile) | NULL = ยังอยู่; ทุก query กรอง `deleted_at IS NULL` | ไม่แสดง (ใช้กรอง) | 0/139 · 0/175 · 0/67 |
| `fetched_at` | เวลา UTC ที่แถวถูก upsert ล่าสุด | – (ระบบ) | ISO UTC Z ms | – | นาฬิการะบบ | A F R | ตั้งใหม่ทุก upsert แม้ค่าเท่าเดิม | sidebar MAX รวมทีม | 139/139 · 175/175 · 67/67 |

## fact_activity_split

PK = (`activity_id`, `split_num`); ไม่มี `athlete_id` (ผูกผ่าน `fact_activity`). N (จำนวนแถว) ต่อคน tong · dan · p'kao = 1066 · 1476 · 362 (จำนวน split). ไม่มี `fetched_at` และไม่มี bounds ในทุกช่อง — จึงบอกไม่ได้ว่ารอบไหนถูกดึงเมื่อไหร่

| column | ความหมาย | endpoint + JSON path | หน่วยต้นทาง → แสดง | วันที่อ้างอิง | timestamp ต้นทาง | lane | กฎ null/0 | การรวม/แสดงบน dashboard | coverage 90 วัน (tong · dan · p'kao) |
|---|---|---|---|---|---|---|---|---|---|
| `split_num` | ลำดับรอบ (1..n ตามลำดับที่ Garmin ส่ง) | `get_activity_splits(id)` → list หรือ dict `lapDTOs` / `splitSummaries` (เลือกอันแรกที่ไม่ว่าง) | จำนวนเต็ม (ระบบนับเอง ไม่ใช่ lapIndex ของ Garmin) | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | แถวที่ split_num > จำนวนรอบใหม่ถูกลบ | ตาราง lap | 1066/1066 · 1476/1476 · 362/362 |
| `distance_m` | ระยะรอบ | → `distance` | เมตร | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | ผ่านค่าดิบ; รอบ 0 m แสดงตามจริง (ตัดสิน 7 ส.ค. 69) | ตาราง lap | 1066/1066 · 1476/1476 · 361/362 |
| `duration_sec` | เวลารอบ | → `duration` (ถ้า 0/ว่างใช้ `elapsedDuration`) | วินาที → `fmt_sec` | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | `or` = 0 ถูกมองเป็นว่าง | ตาราง lap | 1066/1066 · 1476/1476 · 362/362 |
| `avg_hr` | HR เฉลี่ยรอบ | → `averageHR` | bpm | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | ผ่านค่าดิบ | ตาราง + กราฟ HR ต่อ lap | 1066/1066 · 1476/1476 · 362/362 |
| `max_hr` | HR สูงสุดรอบ | → `maxHR` | bpm | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | ผ่านค่าดิบ | ตาราง + กราฟ | 1066/1066 · 1476/1476 · 362/362 |
| `avg_cadence` | Cadence เฉลี่ย | → `averageRunCadence` หรือ `averageRunningCadenceInStepsPerMinute` หรือ `averageCadence` (ตัวแรกที่ไม่ใช่ 0/ว่าง) | spm | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | `or` chain: 0 ถูกข้าม | ตาราง | 1063/1066 · 1475/1476 · 349/362 |
| `max_cadence` | Cadence สูงสุด | → `maxRunCadence` หรือ `maxRunningCadenceInStepsPerMinute` | spm | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | `or` chain | ตาราง | 1063/1066 · 1475/1476 · 349/362 |
| `avg_power` | Power เฉลี่ย | → `averagePower` | W | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | ผ่านค่าดิบ (0 เก็บ) | ตาราง | 1066/1066 · 1476/1476 · 352/362 |
| `max_power` | Power สูงสุด | → `maxPower` | W | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | ผ่านค่าดิบ | ตาราง | 1066/1066 · 1476/1476 · 352/362 |
| `normalized_power` | Normalized Power | → `normalizedPower` หรือ `normPower` | W | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | `or` chain | ตาราง | 1038/1066 · 1450/1476 · 346/362 |
| `avg_speed_mps` | ความเร็วเฉลี่ย | → `averageSpeed` | m/s → km/h | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | ผ่านค่าดิบ | ตาราง (km/h) | 1066/1066 · 1476/1476 · 361/362 |
| `avg_stride_length_cm` | ความยาวก้าว | → `strideLength` | cm (ยังไม่ตรวจ) | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | ผ่านค่าดิบ | ตาราง | 1063/1066 · 1475/1476 · 349/362 |
| `ground_contact_time_ms` | Ground Contact | → `groundContactTime` | ms | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | ผ่านค่าดิบ | ตาราง | 1051/1066 · 1469/1476 · 339/362 |
| `vertical_oscillation_cm` | Vertical Oscillation | → `verticalOscillation` | cm | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | ผ่านค่าดิบ | ตาราง | 1062/1066 · 1475/1476 · 349/362 |
| `vertical_ratio` | Vertical Ratio | → `verticalRatio` | % | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | ผ่านค่าดิบ | ตาราง | 1058/1066 · 1472/1476 · 349/362 |
| `elevation_gain_m` | ไต่รอบ | → `elevationGain` | m | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | 0 เป็นค่าจริง | ตาราง | 1061/1066 · 1471/1476 · 43/362 |
| `elevation_loss_m` | ลดรอบ | → `elevationLoss` | m | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | 0 เป็นค่าจริง | ตาราง | 1061/1066 · 1471/1476 · 43/362 |
| `intensity_type` | ชนิดรอบตาม Garmin (เช่น warmup/active/rest) | → `intensityType` | ข้อความ → `garmin_label` | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | ผ่านค่าดิบ | ตาราง | 1064/1066 · 1475/1476 · 354/362 |
| `avg_pace_min_km` | เพซรอบ **ที่ระบบคำนวณ** | (duration/60)/(distance/1000) ปัด 2 | นาที/กม. → M:SS | ผูกกับกิจกรรม (วันตาม `start_time_local` ของ activity_id) | – | A (เฉพาะกิจกรรมที่ยังไม่มี split และ distance>0) · F (ทุกกิจกรรม distance>0 ในหน้าต่าง) · R (รายการใหม่) | NULL ถ้า distance≤0 หรือ duration ว่าง | ตาราง (รอบสั้นควรอ่านจากเวลา) | 1064/1066 · 1476/1476 · 351/362 |

## fact_race_prediction

PK = (`athlete_id`, `calendar_date`). N (จำนวนแถว) ต่อคน tong · dan · p'kao = 89 · 90 · 90

| column | ความหมาย | endpoint + JSON path | หน่วยต้นทาง → แสดง | วันที่อ้างอิง | timestamp ต้นทาง | lane | กฎ null/0 | การรวม/แสดงบน dashboard | coverage 90 วัน (tong · dan · p'kao) |
|---|---|---|---|---|---|---|---|---|---|
| `calendar_date` | วันของค่าคาดการณ์ (PK คู่กับ athlete) | `get_race_predictions(start,end,'daily')` (list) → `calendarDate` | YYYY-MM-DD | แถวของ `calendarDate` (วันที่ Garmin ระบุ) | ตัวมันเอง | F (ช่วง today-3..today) · D (today-45..today) | รูปแบบวันที่ผิด → ข้ามแถว | estimates | 89/89 · 90/90 · 90/90 |
| `time_5k_sec` | เวลาคาดการณ์ 5K | → `time5K` | วินาที → `fmt_sec` | แถวของ `calendarDate` (วันที่ Garmin ระบุ) | – | F D | N1 [1,604800]; ทั้งสี่ช่อง NULL → ไม่สร้างแถว; COALESCE | estimates ไทล์ (latest_field) + กราฟ 5K/10K เป็นนาที | 89/89 · 90/90 · 90/90 |
| `time_10k_sec` | 10K | → `time10K` | วินาที | แถวของ `calendarDate` (วันที่ Garmin ระบุ) | – | F D | เหมือนกัน | เหมือนกัน | 89/89 · 90/90 · 90/90 |
| `time_half_sec` | Half Marathon | → `timeHalfMarathon` | วินาที | แถวของ `calendarDate` (วันที่ Garmin ระบุ) | – | F D | เหมือนกัน | ไทล์ | 89/89 · 90/90 · 90/90 |
| `time_full_sec` | Marathon | → `timeMarathon` | วินาที | แถวของ `calendarDate` (วันที่ Garmin ระบุ) | – | F D | เหมือนกัน | ไทล์ | 89/89 · 90/90 · 90/90 |
| `fetched_at` | เวลา UTC ที่แถวถูกเขียน | – (ระบบ) | ISO UTC Z | – | นาฬิการะบบ | F D | ตั้งใหม่ทุก upsert | ไม่แสดง | 89/89 · 90/90 · 90/90 |

## fact_body_composition

PK = (`athlete_id`, `calendar_date`). N (จำนวนแถว) ต่อคน tong · dan · p'kao = 2 · 0 · 1. ตารางมีค่าเฉพาะคนที่ชั่ง/กรอกน้ำหนัก; ทั้งประวัติ `bmi` และ `body_fat_pct` = 0 แถวในทั้งสามคน (นับจริง: tong/dan/p'kao = [0, 0, 0] / [0, 0, 0])

| column | ความหมาย | endpoint + JSON path | หน่วยต้นทาง → แสดง | วันที่อ้างอิง | timestamp ต้นทาง | lane | กฎ null/0 | การรวม/แสดงบน dashboard | coverage 90 วัน (tong · dan · p'kao) |
|---|---|---|---|---|---|---|---|---|---|
| `calendar_date` | วันที่ชั่ง (PK) | `get_body_composition(start,end)` → `dateWeightList[].calendarDate` | YYYY-MM-DD | แถวของ `calendarDate` (สำรอง: `date` epoch ms → **วัน UTC**) | – | F (4 วัน) · D (46 วัน) — ชั่งย้อนเก่ากว่านี้ scheduled lane ไม่เก็บ | ไม่มีวันที่ → ข้ามแถว | estimates | 2/2 · 0/0 · 1/1 |
| `weight_kg` | น้ำหนัก | → `weight` | กรัม (โค้ดถือว่าเป็นกรัม) → kg ปัด 2 | แถวของ `calendarDate` (สำรอง: `date` epoch ms → **วัน UTC**) | – | F D | N1 [1000,500000] g | estimates ไทล์ (latest_field) | 2/2 · 0/0 · 1/1 |
| `bmi` | BMI | → `bmi` | หน่วย BMI | แถวของ `calendarDate` (สำรอง: `date` epoch ms → **วัน UTC**) | – | F D | N1 [5,100] | estimates ไทล์ | 0/2 · 0/0 · 0/1 |
| `body_fat_pct` | ไขมันร่างกาย | → `bodyFat` | % | แถวของ `calendarDate` (สำรอง: `date` epoch ms → **วัน UTC**) | – | F D | N1 [0,100] | estimates ไทล์ | 0/2 · 0/0 · 0/1 |
| `fetched_at` | เวลา UTC ที่แถวถูกเขียน | – (ระบบ) | ISO UTC Z | – | นาฬิการะบบ | F D | ตั้งใหม่ทุก upsert | ไม่แสดง | 2/2 · 0/0 · 1/1 |

## fact_personal_record

PK = (`athlete_id`, `record_type_id`) — snapshot ปัจจุบันของบัญชี ไม่มีมิติวัน จึงนับทั้งตาราง: จำนวนแถว tong · dan · p'kao = 11 · 15 · 11. Reconcile ตามหลัง b53c5ce: ประเภทที่ไม่อยู่ใน response ถูกลบ (ยกเว้น response ว่างทั้งหมดที่ไม่แตะอะไร)

| column | ความหมาย | endpoint + JSON path | หน่วยต้นทาง → แสดง | วันที่อ้างอิง | timestamp ต้นทาง | lane | กฎ null/0 | การรวม/แสดงบน dashboard | coverage 90 วัน (tong · dan · p'kao) |
|---|---|---|---|---|---|---|---|---|---|
| `record_type_id` | รหัสชนิด PR (PK คู่กับ athlete) | `get_personal_record()` → list หรือ dict `personalRecords[]` → `typeId` | จำนวนเต็ม | snapshot ปัจจุบัน ไม่ผูกวัน | – | F D | N1 [1,1e6] | estimates ตาราง | 11/11 · 15/15 · 11/11 |
| `record_label` | ชื่อรายการ | ไม่ได้มาจาก API (`prTypeLabelKey` เป็น null) — ตารางแปลง `PR_LABELS` ในโค้ดครอบ typeId 1–9, 12–14 | ข้อความ | – | – | F D | typeId นอกตาราง → NULL → หน้าเว็บเขียน 'รายการที่ Garmin ไม่ได้ระบุชื่อ (รหัส n)' | estimates ตาราง | 9/11 · 11/15 · 9/11 |
| `value` | ค่าสถิติ | → `value` | ขึ้นกับชนิด: เวลา=วินาที · ระยะ=เมตร · ก้าว=ก้าว → `fmt_sec`/km/m/ก้าว; ชนิดที่ไม่รู้แสดงค่าดิบ | – | – | F D | N1 [0,1e9]; แถวจริงถูกแทนทั้งแถว (ไม่ COALESCE); PR ที่หายจาก Garmin ถูกลบ (b53c5ce) | estimates ตาราง | 11/11 · 15/15 · 11/11 |
| `activity_id` | กิจกรรมที่ทำ PR | → `activityId` | จำนวนเต็ม | – | – | F D | N1 [1,∞) | ไม่แสดง | 11/11 · 15/15 · 11/11 |
| `achieved_date` | วันที่ทำ PR | → `prStartTimeGmtFormatted` (สำรอง `prStartTimeGmt`) 10 ตัวแรก หรือ epoch ms → UTC date | วันที่ | `achieved_date` เป็น **วัน GMT/UTC** ของกิจกรรมที่ทำ PR (ไม่ใช่วัน Bangkok) | – | F D | แปลงไม่ได้ → NULL | estimates ตาราง 'ทำได้เมื่อ' | 11/11 · 15/15 · 11/11 |
| `fetched_at` | เวลา UTC ที่แถวถูกเขียน | – (ระบบ) | ISO UTC Z | – | นาฬิการะบบ | F D | ตั้งใหม่ทุก upsert | ไม่แสดง | 11/11 · 15/15 · 11/11 |

## fact_gear

PK = (`athlete_id`, `gear_uuid`). จำนวนแถว tong · dan · p'kao = 3 · 7 · 0 (ทั้งตาราง). **ไม่แสดงบน dashboard** ตามคำสั่ง 22 ก.ค. 69 ในบัญชีที่ `get_gear` ไม่ส่งอะไรมา ตารางจะว่าง (p'kao)

| column | ความหมาย | endpoint + JSON path | หน่วยต้นทาง → แสดง | วันที่อ้างอิง | timestamp ต้นทาง | lane | กฎ null/0 | การรวม/แสดงบน dashboard | coverage 90 วัน (tong · dan · p'kao) |
|---|---|---|---|---|---|---|---|---|---|
| `gear_uuid` | รหัสอุปกรณ์ (PK) | `get_user_profile()` → `profileId`\|`id`\|`userProfileId` → `get_gear(profileId)` → `uuid` | ข้อความ | – | – | F D | ผ่าน `_clean_identifier` | **ไม่แสดง** (เอาออก 22 ก.ค. 69) | 3/3 · 7/7 · 0/0 |
| `gear_name` | ชื่อ | → `displayName` (สำรอง `customMakeModel`) | ข้อความ | – | – | F D | ≤200 | ไม่แสดง | 3/3 · 7/7 · 0/0 |
| `gear_type` | ชนิด | → `gearTypeName` | ข้อความ | – | – | F D | ≤100 | ไม่แสดง | 3/3 · 7/7 · 0/0 |
| `custom_make_model` | รุ่น | → `customMakeModel` | ข้อความ | – | – | F D | ≤200 | ไม่แสดง | 3/3 · 7/7 · 0/0 |
| `date_begin` | วันที่เริ่มใช้ | → `dateBegin` 10 ตัวแรก | วันที่ | – | – | F D | แปลงไม่ได้ → NULL | ไม่แสดง | 3/3 · 7/7 · 0/0 |
| `retired` | ปลดระวางหรือไม่ | → `gearStatusName` (== 'retired' → 1) | 0/1 | – | – | F D | ไม่มี status → NULL (ไม่ใช่ 0) | ไม่แสดง | 3/3 · 7/7 · 0/0 |
| `total_distance_m` | ระยะสะสม | `get_gear_stats(uuid)` → `totalDistance` | ตามชื่อคอลัมน์ = เมตร (ยังไม่ตรวจกับ payload) | – | – | F D | N1 [0,1e9] | ไม่แสดง | 3/3 · 7/7 · 0/0 |
| `total_activities` | จำนวนกิจกรรมสะสม | `get_gear_stats(uuid)` → `totalActivities` | จำนวน | – | – | F D | N1 [0,1e7] | ไม่แสดง | 3/3 · 7/7 · 0/0 |
| `fetched_at` | เวลา UTC ที่แถวถูกเขียน | – (ระบบ) | ISO UTC Z | – | นาฬิการะบบ | F D | ตั้งใหม่ทุก upsert | ไม่แสดง | 3/3 · 7/7 · 0/0 |

## dim_athlete_device

PK = (`athlete_id`, `device_id`). จำนวนแถว tong · dan · p'kao = 1 · 2 · 2 (ทั้งตาราง)

| column | ความหมาย | endpoint + JSON path | หน่วยต้นทาง → แสดง | วันที่อ้างอิง | timestamp ต้นทาง | lane | กฎ null/0 | การรวม/แสดงบน dashboard | coverage 90 วัน (tong · dan · p'kao) |
|---|---|---|---|---|---|---|---|---|---|
| `device_id` | รหัสอุปกรณ์ (PK คู่กับ athlete) | `get_devices()` → list หรือ dict `devices[]` → `deviceId` (สำรอง `unitId`) | ID | – | – | F D | ผ่าน `_clean_identifier`; ห้ามใส่ log/รายงาน | ไม่แสดง | 1/1 · 2/2 · 2/2 |
| `product_display_name` | ชื่อรุ่น | → `productDisplayName` (สำรอง `productName`) | ข้อความ | – | – | F D | COALESCE | ป้ายรุ่นในการ์ดทีม + popover (`device_inventory_labels`) | 1/1 · 2/2 · 2/2 |
| `display_name` | ชื่อที่ผู้ใช้ตั้ง | → `displayName` | ข้อความ | – | – | F D | COALESCE | สำรองเมื่อไม่มี product name | 1/1 · 2/2 · 2/2 |
| `is_primary_device` | เป็นเครื่องหลักหรือไม่ | → `isPrimaryDevice` (สำรอง `primaryDevice`, `primary`) | 0/1 | – | – | F D | ไม่รู้จักค่า → NULL | ใช้เรียงลำดับ (`ORDER BY is_primary_training_device DESC, is_primary_device DESC`) | 1/1 · 2/2 · 2/2 |
| `is_primary_activity_tracker` | เป็นเครื่องบันทึกกิจกรรมหลัก | → `isPrimaryActivityTracker` (สำรอง `primaryActivityTracker`) | 0/1 | – | – | F D | NULL ทุกแถวใน DB | ไม่แสดง | 0/1 · 0/2 · 0/2 |
| `is_primary_training_device` | เป็นเครื่องฝึกหลัก | → `isPrimaryTrainingDevice` (สำรอง `primaryTrainingDevice`) | 0/1 | – | – | F D | NULL ทุกแถวใน DB | ใช้เรียงลำดับ | 0/1 · 0/2 · 0/2 |
| `last_seen_at_utc` | เวลาที่รอบ F/D เห็นเครื่องนี้ในรายการ (นาฬิการะบบ ไม่ใช่เวลา sync ของเครื่อง) | – (ระบบ) | ISO UTC Z → 'dd/mm/yyyy' เวลาไทย | – | นาฬิการะบบ | F D | เกิน 90 วัน → ตัดออกจากป้าย | popover 'พบล่าสุด' | 1/1 · 2/2 · 2/2 |

**ข้อสังเกตที่พบตอนไล่ dashboard:** การ์ดทีมเขียนรุ่นนาฬิกาจาก `devices[0]` ของ `load_athlete_devices` ซึ่งเรียงด้วย `is_primary_training_device DESC, is_primary_device DESC`; เพราะ `is_primary_training_device` เป็น NULL ทุกแถว และ p'kao มีสองเครื่องที่ `is_primary_device=1` (`HRM 600` สายรัดอก กับ fenix 8) ผลเรียงจึงไม่แน่นอนตามสเปก SQL — ตอนตรวจ (SELECT ตามคำสั่งเดียวกัน) ผลคือ **`HRM 600` มาก่อน** จึงมีโอกาสที่การ์ด p'kao แสดงชื่อสายรัดอกแทนนาฬิกา (ต้องเปิดหน้าเว็บดูจริงเพื่อยืนยัน — ผมยังไม่ได้เปิด)

---

## 1. สถานะข้อมูล: ระบบแยกอะไรได้ในวันนี้

| สถานะ | แยกได้ไหม | ตรวจที่ไหนในโค้ด | ช่องว่าง / ต้องมีอะไรเพิ่ม |
|---|---|---|---|
| **มีข้อมูล** | ได้ (ระดับช่อง) | `dashboard_domain.value_of` (ไม่ใช่ NULL); `day_status` → `complete_day` เมื่อ *อย่างน้อยหนึ่ง* ช่องใน `CORE_DAILY_FIELDS` (sleep_score, hrv_last_night, resting_hr, bb_most_recent, body_battery_high, stress_avg, steps) มีค่า; popover `summarize_metric_group` → `available`/`partial` | "มีข้อมูลของวันนั้น" = มีอย่างน้อยหนึ่งช่อง ไม่ได้แปลว่าครบ (วันที่มีแต่ steps ก็ขึ้นเขียว) การตรวจ *partial* ของเมื่อวานมีแค่ฝั่งหลังบ้าน (`03_backfill.sanity_check`, `data_quality.partial_snapshot_findings`) ไม่ขึ้นหน้าเว็บ |
| **ระหว่างวัน ยังไม่ครบวัน** | ได้แบบหยาบ (ปฏิทินอย่างเดียว) | `dashboard_domain.day_status` → `partial_today` เมื่อ `day == today` (Bangkok) และมีค่าบางช่อง | ตัดสินจากวันที่ ไม่ใช่จากข้อมูล; กิจกรรมไม่มีสถานะนี้; **เมื่อวานที่ Garmin ยังแก้ย้อนหลังได้ (หน้าต่าง 36 ชม. ของ settle review) แสดงเป็น "มีข้อมูลของวันนั้น" ปกติ** ต้องเพิ่ม: ธง 'ยังอยู่ในหน้าต่างปรับค่า' อ่านจาก `settle_reviewed_at_utc` (หลังรัน migration) |
| **ยังไม่ได้รับ** | ได้ (ระดับวัน/ช่อง/บัญชี) แต่ **ไม่รู้เหตุ** | `day_status` → `no_data` (ไม่มีแถว หรือ 7 ช่องหลักเป็น NULL หมด; ข้อความต่างกันระหว่างวันนี้/วันอื่น); `team.missing_note` ("ไม่มีของวันนี้ · ครั้งก่อน …"); popover `never_received` (ทั้งประวัติ = 0) / `outside_range` | ทุกสาเหตุ (นักกีฬาไม่ sync, ไม่ได้ใส่นาฬิกา, Garmin ยังไม่ประมวลผล, เรียก API ล้ม, ค่าถูก N1 ปัดทิ้ง, เครื่องไม่ส่ง) ตกกลุ่มเดียวกัน ต้องเพิ่มบันทึกผลการเรียกต่อ (athlete, date, endpoint) ดูหัวข้อ 5 ข้อ 2 |
| **อุปกรณ์ไม่รองรับ** | **ยังแยกไม่ได้ในระบบ** | มีแค่ `never_received` จากประวัติ + รายชื่อรุ่นใน `dim_athlete_device`; docs/PROJECT.md ห้ามฟันธงจากชื่อรุ่น | ไม่มีตาราง capability และไม่บันทึก "รูปร่าง" ของ response ที่ว่าง (`[]`, `{}`, key เป็น null, `invalidReason`); ต้องเพิ่ม: บันทึกชนิดของคำตอบว่างต่อ endpoint ต่อบัญชี (ยิงอ่านอย่างเดียว) — หลักฐาน API มีเฉพาะในบันทึกของ Claude (ดูหัวข้อ 4) |
| **เรียกล้มเหลว** | บางส่วน (ระดับรอบ ไม่ใช่ระดับวัน/ช่อง) | `03_backfill.safe_call(_failures=...)` บันทึก `{endpoint, reason}` ได้เฉพาะ endpoint wellness ทั้งหมด (`_call_wellness_endpoint`) และ `get_personal_record` (19a9eb1) ลง `data/sync_status/<slug>.json` → `endpoint_failures` (reason = token / network / payload; ทับทุกรอบ ไม่มีวันที่); intraday (`get_heart_rates`, `get_stress_data`, `intraday_store`) ก็เข้าทางนี้ (2cc6374); **ยกเว้น settle review ที่ตั้งใจไม่ส่งความล้มเหลวต่อ** (a03c73b — แค่ print จำนวน); ทั้งรอบล้ม → `write_status(ok=False, reason)`; ระดับ lane → `data/sync_lane/<lane>.json` `results[].reason` (ok/token/network/payload/error/timeout/status_missing) จากนั้น `health_report.py` และ `notify_sync.ps1` อ่าน | (ก) HTTP 404/204 คืน None เงียบ ๆ = 'ไม่มีข้อมูล' ปนกับความล้มเหลวจริง — คอมเมนต์ใน `fetch_and_insert_extras` ยอมรับเองว่าแยกไม่ได้ (ข) การเรียก activity detail/weather/splits, LT, fitness age, race, body, gear, devices ใช้ `safe_call` **ไม่ส่ง `_failures`** จึงล้มแล้วมองไม่เห็น (ค) หน้าสุขภาพของนักกีฬาไม่อ่านสถานะ sync; มีเฉพาะหน้า **สถานะระบบ** (`app_pages/system.py`, 031a244) ที่อ่าน `data/sync_status/<slug>.json` แล้วแสดง ผล/สาเหตุ (token|network)/*จำนวน* endpoint ที่ล้ม/เวลาเสร็จ — **ไม่บอกชื่อ endpoint, วันที่, หรือช่องที่กระทบ** และไม่อ่าน `sync_lane/*.json` (ส่วนนั้นผ่าน `health_report.run_all_checks()`) |
| **ล่าช้า** | ระดับ lane เท่านั้น (เห็นได้บนหน้า 'สถานะระบบ' ผ่าน `health_report`) | `health_report.check_lane_freshness` + `notify_sync.ps1 $STALE_LIMIT_MIN` (full 900 / fast 75 / wellness 90 / reconcile 12240 / deep 44640 / backup 1800 นาที); `data_quality.DEVICE_SILENT_ERROR_DAYS=3` (นาฬิกาเงียบต่อเนื่อง) | ไม่มีสถานะ 'ล่าช้า' ต่อช่อง; แยก 'Garmin ประมวลผลช้า' ออกจาก 'นักกีฬายังไม่ sync' ไม่ได้ (docs ยอมรับว่าเพดานความสดคือจังหวะที่นักกีฬา sync); หน้าสุขภาพบอกความสดแค่ผ่าน `fetched_at` (ดูหัวข้อ 2) และเวลา snapshot ของ Readiness; intraday (เมื่อมีตาราง) ให้ `MAX(ts_utc)` = เวลาจุดล่าสุดจากนาฬิกา ซึ่งเป็นสัญญาณความสดฝั่งต้นทางอย่างเดียวของ HR/Stress/Body Battery |
| **ไม่ผ่านการตรวจ** | **ตอน ingest ทำได้ แต่ไม่เหลือร่องรอย** | ingest: `_bounded_number`, `_atomic_body_battery_values` (คู่ high/low), `_validated_activities` (รายการกิจกรรมผิดรูป → ล้มทั้งรอบ), split payload ผิดรูป → เก็บของเดิมและ print เท่านั้น; ภายหลัง: `data_quality.range_findings` (`RANGE_RULES` เฉพาะ wellness) + ความสัมพันธ์ BB high≥low, respiration high≥low; รัน `check_drift.py` หลัง deep lane | ค่าที่ N1 ปัดทิ้งกลายเป็น NULL ธรรมดา (ไปตกกลุ่ม 'ยังไม่ได้รับ') เพราะไม่มีตัวนับ/ค่าดิบเก็บไว้; activity/split ไม่มี range rule เลย; findings ไม่ขึ้น dashboard |
| **ไม่ทราบสาเหตุ** | เป็นค่าเริ่มต้นโดยปริยาย | ทุกอย่างที่ไม่เข้าข้อข้างบน = NULL/ขาด โดยไม่มีป้าย | ระบบไม่มีป้าย 'ไม่ทราบ' ชัดเจน — 'ยังไม่ได้รับ' ทำหน้าที่นี้ไปด้วย |

**สิ่งที่ระบบแยกได้จริงและมีประโยชน์ (หลังบ้าน):** `data_quality.partial_snapshot_findings` แยก *"นาฬิกาเงียบทั้งวัน"* (ไม่มีกิจกรรมของเมื่อวานและ silent streak <3 วัน → WARNING) ออกจาก *"มีกิจกรรมของวันนั้นแต่ wellness หาย"* (`device_signal` → ERROR ชี้ pipeline) และ `03_backfill.sanity_check` เตือน "wellness ว่างทั้งวัน"/"partial snapshot" (เฉพาะวันที่จบแล้ว ภายใน `WELLNESS_GAP_WARN_DAYS`=14 วัน) — ทั้งหมดอยู่ใน `sync_status.warnings`/ผล `check_drift` ไม่ใช่บนหน้าเว็บ

---

## 2. ความสด (freshness)

**`fetched_at` เป็นเวลาระดับ *แถว* ไม่ใช่ระดับ endpoint หรือระดับช่อง** — ช่องว่างนี้ตรงไปตรงมา:

| ตาราง | `fetched_at` เลื่อนเมื่อไหร่ | ผลที่อ่านผิดได้ |
|---|---|---|
| `fact_daily_wellness` | ทุกครั้งที่ `_insert_wellness_row` (F/D) หรือ `_update_wellness_fields` (W, repair, LT, fitness age) เขียน ≥1 ช่อง — **แม้ค่าเท่าเดิม และแม้ endpoint อื่นของแถวนั้นไม่ได้ถูกเรียกเลย**; `INSERT OR IGNORE` สร้างแถวว่างก็ตั้ง fetched_at (dashboard นับเฉพาะแถวที่มีค่าหลักใน `load_latest_fetch`) ข้อยกเว้นเดียว: settle review คืนค่า fetched_at เดิมเมื่อไม่มีช่องไหนเปลี่ยน (ยังไม่ทำงานจริง — ดูข้างบน) | แถวเดียวประกอบจากหลาย endpoint: Body Battery รอบ 14:12 ทำให้แถวดู 'สด' แม้ Sleep/HRV ในแถวเดียวกันมาจากเมื่อเช้า; extras (fitness_age/LT) เขียนแถวของ end_date/lt_date แล้วเลื่อน fetched_at ของแถวนั้นด้วยงานที่ไม่เกี่ยวกับช่องอื่น |
| `fact_activity` | ทุก upsert (A ทุก 15 นาทีสำหรับกิจกรรมของวันนี้, F สำหรับ 4 วัน) แม้ค่าเท่าเดิม | `fetched_at` ของกิจกรรมบอกแค่ 'รอบล่าสุดที่เห็นรายการนี้' ไม่ใช่ 'ข้อมูลเปลี่ยนเมื่อไหร่' |
| `fact_race_prediction`, `fact_body_composition`, `fact_personal_record`, `fact_gear` | ทุก upsert ใน F/D | เหมือนกัน; race/body ครอบ 4 วัน (F) หรือ 46 วัน (D) ทุกครั้ง |
| `fact_activity_split` | ไม่มีคอลัมน์ fetched_at | บอกไม่ได้เลย |
| `fact_wellness_intraday` | ทุกรอบ W เขียนทับทั้งวัน (upsert ทุกจุด) | `fetched_at` บอกแค่รอบล่าสุดที่ดึง; ใช้ `ts_utc` ต่างหากสำหรับ 'ข้อมูลจากนาฬิกาถึงเวลาไหน' |

**หลักฐานจากฐานจริง:** ในหน้าต่าง 90 วัน มี **255 จาก 270 แถว** (ทั้งสามคนรวมกัน) ที่ `fetched_at` เกิดหลัง `calendar_date` เกิน 3 วัน = ถูกแตะซ้ำโดย lane ย้อนหลัง (deep/reconcile-window/extras) ดังนั้น `fetched_at` ไม่ได้แปลว่า 'ข้อมูลของวันนั้นมาถึงเมื่อไหร่' (SQL: `julianday(substr(fetched_at,1,10)) - julianday(calendar_date) > 3`; สาเหตุของแต่ละแถวผมไม่ได้แยก)

**ที่ dashboard ใช้ `fetched_at`:** (1) การ์ดทีม 'แถวนี้ดึงจาก Garmin ล่าสุด' = `fetched_at` ของแถววันที่เลือก (2) sidebar 'ดึงจาก Garmin ล่าสุด' = `load_latest_fetch()` เรียกโดยไม่ระบุคน = **`MAX(fetched_at)` รวมทั้งทีม** ของ activity กับ wellness-ที่มีค่าจริง — การดึงกิจกรรมของคนหนึ่งบังความเก่าของ wellness อีกคนได้ (3) ตัวช่วยเรียงใน `latest_field` เป็นอันดับสามรองจากวันที่และ timestamp ต้นทาง

**ช่องที่มี timestamp ต้นทางของตัวเอง**

| ช่อง | timestamp | ที่มา | หมายเหตุ |
|---|---|---|---|
| Readiness ทั้งชุด (`training_readiness`, `readiness_*`, factor ต่าง ๆ) | `readiness_timestamp_utc` (จาก `timestamp`), `readiness_timestamp_local` (จาก `timestampLocal`), `readiness_device_id` | snapshot ที่ใหม่สุดของวันนั้น | dashboard ใช้แสดง 'dd/mm HH:MM' และเรียงลำดับ |
| HR / Stress / Body Battery รายจุด (`fact_wellness_intraday`) | `ts_utc` ต่อจุด | ตัวเลขแรกในระบบที่บอกเวลาต้นทางจริงของค่า intraday | ยังไม่มีตารางใน DB จริง |
| กิจกรรม | `start_time_local`, `start_time_utc` | `startTimeLocal`, `startTimeGMT` | เวลา *เริ่ม* ไม่ใช่เวลาที่ Garmin ประมวลผลเสร็จ |
| Race prediction / body composition / LT | `calendar_date` ที่ Garmin ระบุ | `calendarDate` | ระดับวัน |
| PR | `achieved_date` | `prStartTimeGmtFormatted` | ระดับวัน (UTC) |
| `dim_athlete_device.last_seen_at_utc`, `repair_attempted_at_utc`, `settle_reviewed_at_utc`, `fetched_at`, `deleted_at` | เวลาของ **ระบบเรา** | นาฬิกาเครื่อง | ไม่ใช่เวลาที่เกิดเหตุฝั่ง Garmin |

**ไม่มี timestamp ต้นทางเลย:** Sleep, HRV, RHR, Body Battery, Stress, Steps, Respiration, Training Status, VO2max, Endurance/Hill, Fitness Age. payload ของ endpoint เหล่านี้อาจมีเวลา (เช่นเวลา sync ล่าสุดของนาฬิกา) แต่โค้ดไม่อ่านและผมยังไม่ได้ยิงตรวจ — **ยังไม่ยืนยันว่ามีหรือไม่**

**สรุปช่องว่าง:** ไม่มีทางรู้ว่าค่าหนึ่ง ๆ (เช่น Body Battery ล่าสุด, Sleep score) ถูก Garmin คำนวณ/ส่งมาเมื่อไหร่ หรือระบบเราเห็นมันเปลี่ยนครั้งสุดท้ายเมื่อไหร่ ทางแก้ที่ลงมือได้ (เรียงตามความคุ้ม): (1) รัน `02_init_schema.py` เพื่อให้ settle review ทำงาน (แก้แค่ fetched_at ของเมื่อวาน ราคาถูกสุด) (2) ยิงอ่านอย่างเดียวหนึ่งครั้งดูว่า `get_stats`/`get_sleep_data` มีเวลาต้นทางไหม แล้วเก็บเป็นคอลัมน์ (3) ถ้าต้องการระดับช่องจริง: ตารางข้างเคียง `fact_field_observation(athlete_id, calendar_date, field, value_hash, first_seen_at, last_changed_at)` เขียนเฉพาะเมื่อค่าเปลี่ยน — เป็นการเปลี่ยนโครงสร้าง ต้องได้อนุมัติก่อน (ตาม docs/PROJECT.md เรื่องขอบเขตระบบ)

---

## 3. กฎ timezone ตามที่โค้ดทำจริง

| เรื่อง | กฎ | ที่มา |
|---|---|---|
| วันทำการ (business date) | **Asia/Bangkok (UTC+7 คงที่)** — ใช้เป็นวันที่ส่งเข้า endpoint wellness, ขอบหน้าต่าง `--days N`, `calendar_date`, วันที่ที่ dashboard เรียก 'วันนี้', หน้าต่าง check_drift (เฉพาะวันที่จบแล้ว) | `03_backfill.py:2134` (`end_date`), `:1993` (sanity), `dashboard_domain.bangkok_date` |
| `fetched_at`, `last_seen_at_utc`, `repair_attempted_at_utc`, `settle_reviewed_at_utc`, `readiness_timestamp_utc` | **UTC** ข้อความ ISO ลงท้าย `Z` | `UTC_NOW_SQL` ใน `03_backfill.py`, `UTC_NOW_DEFAULT` ใน `02_init_schema.py` |
| การแสดงเวลา | UTC → เวลาไทยที่ชั้น dashboard เท่านั้น (`to_bangkok_timestamp`; ข้อความที่ไม่มีโซนถือเป็น UTC) | `dashboard_domain.py` |
| `start_time_local` vs `start_time_utc` | เก็บ **สองค่าตามที่ Garmin ส่ง** (`startTimeLocal` = เวลาท้องถิ่นของเครื่อง ณ ตอนเริ่ม ไม่มีโซน, `startTimeGMT`); dashboard, reconcile และ check_drift ใช้ 10 ตัวแรกของ `start_time_local` เป็น 'วันของกิจกรรม' | ทุก query ที่ `substr(start_time_local,1,10)` |
| สิ่งที่ตรวจในฐานจริง | ทั้ง 1537 กิจกรรม `start_time_local − start_time_utc` = **+7.0 ชม. ทุกแถว**; readiness local−utc = +7.0 ชม. ทุกแถว | ข้อสมมติ 'ทุกอย่างคือ Bangkok' จึงยังจริงในข้อมูลปัจจุบัน แต่ถ้านักกีฬาเดินทางข้ามโซน วันของกิจกรรมจะเป็นวันตามที่ตั้งเครื่อง ไม่ใช่วันไทย (โค้ดไม่ปรับ) |
| วันของ PR | `achieved_date` เป็นวัน **GMT/UTC**: วิ่ง 05:00 น. ไทยจะถูกบันทึกเป็นวันก่อนหน้า | `03_backfill.py` ช่วง Personal records (`prStartTimeGmtFormatted` 10 ตัวแรก / epoch ms → UTC) |
| วันของ intraday | `ts_utc` จาก epoch ms (UTC); `calendar_date` จาก `calendarDate` ของ payload (สำรอง: วันที่ที่ขอ = Bangkok); แสดงผลแปลงเป็น Bangkok ที่ `dashboard_data.py` (`tz_convert('Asia/Bangkok')`) และหน้าต่าง retention 180 วันนับจาก `ts_utc` เทียบเวลา UTC | `intraday.py`, `dashboard_data.load_intraday` |
| วันของน้ำหนัก | ใช้ `calendarDate`; ถ้าไม่มีสำรองด้วย `date` epoch ms → **วัน UTC** | `03_backfill.py:1783` |
| เวลาเครื่อง naive (ไม่มีโซน) | `deleted_at`, `finished_at` ใน `sync_status/<slug>.json`, `run_at` ใน `sync_lane/*.json`, ช่อง catch-up 08:00/21:00 คิดตามเวลาเครื่อง ไม่ใช่ Bangkok โดยตรง | `03_backfill.py:654`, `:1946`; `fetch_all.py:404`, `:423` (และ `:186`, `:384`) — เครื่องนี้ตั้งเป็น 'SE Asia Standard Time' (UTC+7) จึงไม่ต่างในทางปฏิบัติ แต่ถ้าเปลี่ยนเครื่อง/โซน ช่อง sync และเวลา `deleted_at` จะเลื่อนเงียบ ๆ |

**ตำแหน่งที่บวกชั่วโมงเองแบบ fixed offset** (grep `timedelta(hours=7)` / `+7` / `+07` ทั้ง `garmin/` และ `scripts/`; ไม่พบการ `+ timedelta(hours=7)` กับเวลา):

| ไฟล์:บรรทัด | สิ่งที่ทำ | หมายเหตุ |
|---|---|---|
| `garmin/scripts/03_backfill.py:40` | `BANGKOK_TZ = timezone(timedelta(hours=7))` ใช้ที่ `:1331` (หน้าต่าง settle review), `:1993` (sanity_check), `:2134` (ช่วงวันที่ sync ทั้งหมด) | fixed offset ไม่พึ่ง tzdata |
| `garmin/scripts/data_quality.py:20` | `BANGKOK = timezone(timedelta(hours=7), name="Asia/Bangkok")` ใช้ใน `bangkok_today`/`completed_window` | คอมเมนต์ในไฟล์อธิบายเหตุผล (ไม่พึ่ง tzdata) |
| `scripts/setup_scheduled_tasks.ps1:142, 170, 200` | `StartBoundary = '…+07:00'` ของ task reconcile/deep/restore-drill | ตั้งเวลา ไม่ใช่การแปลงข้อมูล |

ที่ใช้ `ZoneInfo("Asia/Bangkok")` แทน (ต้องมี tzdata บน Windows): `dashboard_domain.py:19`, `validate_sqlite_backup.py:19`, `validate_system_heartbeat.py` (`--timezone` ค่าเริ่มต้น). **มี 2 วิธีสร้าง 'Bangkok' คู่กัน** (fixed offset ฝั่ง sync/monitor, ZoneInfo ฝั่ง dashboard) — ให้ผลเท่ากันเพราะไทยไม่มี DST แต่ถ้าจะแก้ที่เดียวต้องแก้สองที่

---

## 4. ความสามารถของอุปกรณ์: อะไร 'ไม่เคยได้รับ'

รุ่นที่ผูกกับบัญชี (จาก `dim_athlete_device`; เก็บเฉพาะที่ Garmin ส่งใน `get_devices`): **tong** Forerunner 165 (primary=1) · **dan** Forerunner 165 (primary=1), Forerunner 55 (primary=0) · **p'kao** HRM 600 (primary=1), fenix 8 - 47mm, AMOLED (primary=1)

ตัวเลข = แถวที่ช่องนั้นมีค่า / แถวทั้งหมด **ตลอดประวัติ** (ไม่จำกัด 90 วัน — ตามกฎของ docs/PROJECT.md ที่ห้ามสรุปจากช่วงวันที่เลือก)

| metric | tong (ทั้งประวัติ: มีค่า/แถว) | dan | p'kao | สรุปที่ 'ยืนยันได้' |
|---|---|---|---|---|
| Training Readiness (`training_readiness`) | **ไม่เคยได้รับ** (0/394) | **ไม่เคยได้รับ** (0/394) | 393/394 | tong: ไม่เคยได้รับ · dan: ไม่เคยได้รับ · p'kao: เคยได้รับ |
| Recovery Time (`recovery_time_min`) | **ไม่เคยได้รับ** (0/394) | **ไม่เคยได้รับ** (0/394) | 393/394 | tong: ไม่เคยได้รับ · dan: ไม่เคยได้รับ · p'kao: เคยได้รับ |
| Acute Load ใน Readiness (`acute_load`) | **ไม่เคยได้รับ** (0/394) | **ไม่เคยได้รับ** (0/394) | 393/394 | tong: ไม่เคยได้รับ · dan: ไม่เคยได้รับ · p'kao: เคยได้รับ |
| Training Status (`training_status`) | **ไม่เคยได้รับ** (0/394) | 150/394 | 393/394 | tong: ไม่เคยได้รับ · dan: เคยได้รับ · p'kao: เคยได้รับ |
| Endurance Score | **ไม่เคยได้รับ** (0/394) | **ไม่เคยได้รับ** (0/394) | 393/394 | tong: ไม่เคยได้รับ · dan: ไม่เคยได้รับ · p'kao: เคยได้รับ |
| Hill Score (`hill_score_overall`) | **ไม่เคยได้รับ** (0/394) | **ไม่เคยได้รับ** (0/394) | 339/394 | tong: ไม่เคยได้รับ · dan: ไม่เคยได้รับ · p'kao: เคยได้รับ |
| VO2max รายวัน (`vo2max_trend`) | 142/394 | 246/394 | 14/394 | tong: เคยได้รับ · dan: เคยได้รับ · p'kao: เคยได้รับ |
| Fitness Age | **ไม่เคยได้รับ** (0/394) | 56/394 | 56/394 | tong: ไม่เคยได้รับ · dan: เคยได้รับ · p'kao: เคยได้รับ |
| Lactate Threshold HR | **ไม่เคยได้รับ** (0/394) | **ไม่เคยได้รับ** (0/394) | 3/394 | tong: ไม่เคยได้รับ · dan: ไม่เคยได้รับ · p'kao: เคยได้รับ |
| HRV คืนล่าสุด | 113/394 | 189/394 | 338/394 | tong: เคยได้รับ · dan: เคยได้รับ · p'kao: เคยได้รับ |
| Sleep score | 113/394 | 286/394 | 342/394 | tong: เคยได้รับ · dan: เคยได้รับ · p'kao: เคยได้รับ |
| Respiration ตอนหลับ | 112/394 | 284/394 | 339/394 | tong: เคยได้รับ · dan: เคยได้รับ · p'kao: เคยได้รับ |
| Body Battery สูงสุด | 275/394 | 392/394 | 394/394 | tong: เคยได้รับ · dan: เคยได้รับ · p'kao: เคยได้รับ |
| Training Load ต่อกิจกรรม | **ไม่เคยได้รับ** (0/239) | 673/1093 | 205/205 | tong: ไม่เคยได้รับ · dan: เคยได้รับ · p'kao: เคยได้รับ |
| Impact Load | **ไม่เคยได้รับ** (0/239) | **ไม่เคยได้รับ** (0/1093) | 54/205 | tong: ไม่เคยได้รับ · dan: ไม่เคยได้รับ · p'kao: เคยได้รับ |
| Stamina (`begin_stamina`) | **ไม่เคยได้รับ** (0/239) | **ไม่เคยได้รับ** (0/1093) | 53/205 | tong: ไม่เคยได้รับ · dan: ไม่เคยได้รับ · p'kao: เคยได้รับ |
| Running Power (`avg_power`) | 236/239 | 380/1093 | 55/205 | tong: เคยได้รับ · dan: เคยได้รับ · p'kao: เคยได้รับ |
| Ground Contact Time | 235/239 | 379/1093 | 54/205 | tong: เคยได้รับ · dan: เคยได้รับ · p'kao: เคยได้รับ |
| น้ำหนัก (`weight_kg`) | 2/2 | 1/1 | 1/1 | tong: เคยได้รับ · dan: เคยได้รับ · p'kao: เคยได้รับ |
| BMI | **ไม่เคยได้รับ** (0/2) | **ไม่เคยได้รับ** (0/1) | **ไม่เคยได้รับ** (0/1) | tong: ไม่เคยได้รับ · dan: ไม่เคยได้รับ · p'kao: ไม่เคยได้รับ |
| ไขมันร่างกาย | **ไม่เคยได้รับ** (0/2) | **ไม่เคยได้รับ** (0/1) | **ไม่เคยได้รับ** (0/1) | tong: ไม่เคยได้รับ · dan: ไม่เคยได้รับ · p'kao: ไม่เคยได้รับ |
| Race Predictor | 161/161 | 161/161 | 161/161 | tong: เคยได้รับ · dan: เคยได้รับ · p'kao: เคยได้รับ |

**วิธีอ่านและระดับหลักฐาน**

| ระดับ | ความหมาย | ตัวอย่างในระบบนี้ |
|---|---|---|
| **ไม่เคยได้รับ** (0 แถวตลอดประวัติ) | เป็นข้อเท็จจริงจาก DB เท่านั้น ไม่ได้บอกเหตุ | ทุกช่องที่เป็น **ไม่เคยได้รับ** ในตารางข้างบน — ใช้คำนี้ตามนโยบายของ dashboard ('ยังไม่เคยได้รับ') |
| **เคยได้รับแล้วหยุด** | ต้องดูวันที่ล่าสุด ห้ามเรียกว่าไม่รองรับ | dan: `training_status` ล่าสุด 2026-01-29 และ `training_load` ของกิจกรรมล่าสุด 2026-01-29; p'kao: `vo2max_trend` ล่าสุด 2026-07-31 (ตามเงื่อนไขวิ่ง outdoor), `lactate_threshold_hr` ล่าสุด 2026-08-26 |
| **ยืนยันด้วย API ว่าเครื่องไม่ส่ง** | หลักฐานเป็นผลการยิงจริง | (ก) `fitness_age` ของ tong: โค้ดใน `fetch_and_insert_extras` บันทึกว่า Garmin ตอบ `invalidReason: USER_UNDER_AGE` (อยู่ใน repo) (ข) Forerunner 165 (tong, dan): บันทึกของ Claude (memory `garmin-device-capability-gaps`) ระบุว่ายิง `get_training_readiness`/`get_training_status`/`get_endurance_score`/`get_hill_score` แล้วได้ `[]`/null/`{}` และ payload กิจกรรมไม่มีคีย์ `activityTrainingLoad`/`impactLoad`/`*PotentialStamina` เมื่อ 2 ก.ย. 69 — **หลักฐานข้อนี้ไม่อยู่ในเอกสารใน repo** (docs/PROJECT.md มีแค่ประโยคกว้าง ๆ 'ขึ้นกับรุ่นนาฬิกา/บัญชี') ผมยืนยันซ้ำเองไม่ได้ในงานนี้เพราะห้ามเรียก Garmin |

ข้อสังเกต: (1) `bmi`/`body_fat_pct` ไม่เคยได้รับในทั้งสามคน แม้บางคนเคยมีน้ำหนัก — สอดคล้องกับ 'ชั่งด้วยมือ/แอป ไม่ใช่ตาชั่งวัดองค์ประกอบ' แต่นี่เป็นข้อสันนิษฐาน ยังไม่ยืนยัน (2) `is_primary_activity_tracker`/`is_primary_training_device` เป็น NULL ทุกแถว = ชื่อคีย์ที่โค้ดอ่านอาจไม่ตรงกับที่ `get_devices` ส่งจริง (ยังไม่ยืนยัน) (3) p'kao มีสองเครื่องและ `training_status` อ่านจาก 'เครื่องแรกใน dict ที่มีค่า' ไม่ระบุว่าเครื่องไหน; `readiness_device_id` เก็บ ID เครื่องของ Readiness แต่ Dashboard ไม่แสดง

---

## 5. ข้อจำกัดและคำถามที่ยังตอบจากโค้ดไม่ได้ (พร้อมทางแก้ และลำดับ)

| # | ข้อจำกัด | ทำไมสำคัญ | ทางแก้ที่ลงมือได้ | ลำดับ/เหตุผล |
|---|---|---|---|---|
| 1 | **DB จริงยังไม่ได้ migrate**: ไม่มีคอลัมน์ `settle_reviewed_at_utc` (settle review คืน False เงียบ = ยังไม่ทำงาน) และไม่มีตาราง `fact_wellness_intraday` (lane W ยังยิง 2 call/รอบ/คน แต่เก็บลงไม่ได้ — โค้ด `_sync_intraday_day` จับ error แล้วบันทึก failure ชื่อ `intraday_store` ซึ่ง `classify_login_error` จะตีเป็น reason 'network' โดยปริยาย; **นี่เป็นข้อสรุปจากโค้ด ผมไม่ได้เห็นมันเกิดจริง** — รอบ wellness ล่าสุดที่ตรวจ 12:42 ไม่มี warning แต่อาจเกิดก่อนที่ commit intraday จะเข้า) | ค่าเมื่อวานที่ Garmin แก้ย้อนหลังไม่ถูกรับ และกราฟ intraday ที่เพิ่งขึ้นหน้าเว็บจะว่างจนกว่าจะมีตาราง | รัน `02_init_schema.py` หนึ่งครั้ง (idempotent เพิ่มคอลัมน์/ตารางเท่านั้น ไม่แตะข้อมูล) แล้วตรวจว่า `fact_wellness_intraday` เริ่มมีแถว และ `settle_reviewed_at_utc` ถูกประทับ | ทำก่อน — ต้นทุนต่ำสุด และปิดช่องว่างที่ docs/โค้ดอ้างว่าปิดแล้ว |
| 2 | ความล้มเหลวของ endpoint **ไม่ถูกเก็บระดับ (คน, วัน, ช่อง)** และหลาย endpoint ไม่ถูกบันทึกเลย; 404/204 = 'ไม่มีข้อมูล' ปนกับพังจริง (คอมเมนต์ในโค้ดยอมรับ) | เห็น NULL แล้วบอกไม่ได้ว่า 'ไม่มี' หรือ 'ดึงไม่ได้' | (ก) ส่ง `_failures` ให้ทุก `safe_call` (detail/weather/splits/extras); (ข) ให้ `safe_call` คืนสถานะ (`no_data` | `error`) แยกจากค่า; (ค) เก็บผลต่อรอบลง sync_status พร้อมวันที่ | หลังข้อ 1 — เมื่อมี 'พังจริง' เกิดขึ้นแล้วให้เป็นหลักฐาน (ตามกฎ 'ก่อนเสนองาน' ใน CLAUDE.md) |
| 3 | หน้าสุขภาพไม่มีป้าย 'เรียกล้มเหลว'/'ล่าช้า' ต่อช่อง; หน้า 'สถานะระบบ' บอกแค่จำนวน endpoint ที่ล้ม ไม่บอกชื่อ/วัน/ช่อง | โค้ชเห็นแต่ '–' และผู้ดูแลเห็นแค่ตัวเลข | แสดงรายชื่อ endpoint ที่ล้ม (มีอยู่แล้วใน `endpoint_failures`) บนหน้า 'สถานะระบบ'; ส่วนป้ายต่อช่องต้องรอข้อ 2 | รองจากข้อ 2 |
| 4 | `fetched_at` ระดับแถว ไม่ใช่ระดับช่อง (หัวข้อ 2) | เข้าใจความสดของค่าเฉพาะตัวผิดได้ | ดูทางแก้ 3 ข้อในหัวข้อ 2 | ตามหลังข้อ 1 |
| 5 | **null-safe merge ทำให้ Garmin 'ถอน' ค่าไม่ได้** — ถ้า Garmin เปลี่ยนค่าเป็นว่าง ค่าเก่าค้างตลอด (ยกเว้น PR ที่แทนทั้ง snapshot และกิจกรรมที่ถูกลบ) | ค่าที่ Garmin ตัดสินว่าไม่ถูกต้องยังโชว์ | ยังไม่ต้องแก้ — **ยังไม่มีหลักฐานว่าเกิดขึ้นจริง** (ตามกฎ 'จำเป็นตอนนี้ไหม'); เฝ้าดูเมื่อเช็คลิสต์รายเดือนเจอค่าไม่ตรง | เฝ้าดู |
| 6 | ค่าที่ถูก **N1 ปัดทิ้งไม่มีร่องรอย** | ค่าจริงที่อยู่นอกช่วงที่ตั้งไว้จะกลายเป็น 'ยังไม่ได้รับ' (คอมเมนต์ใน `_parse_stats` เล่าว่า `bb_charged` = 102 เป็นค่าจริงในฐาน ซึ่งจะถูกทิ้งถ้าใช้ช่วง 5–100) | นับจำนวนค่าที่ถูกปัดต่อรอบใส่ `warnings` (ไม่ต้องเก็บค่า) | เฝ้าดู |
| 7 | **หน่วยที่ยังไม่ยืนยันกับ payload:** `weather_wind_kph` (อุณหภูมิมา °F จึงสงสัยว่าลมเป็น mph แต่โค้ดไม่แปลงและหน้าเว็บบอก km/h), `avg_stride_length_cm`, `sweat_loss_ml`, `fact_gear.total_distance_m` | ตัวเลขบนหน้าเซสชันอาจผิดหน่วย | ยิงอ่านอย่างเดียว `get_activity_weather` 1 กิจกรรมเทียบกับค่าใน Garmin Connect; ถ้าเป็น mph → แก้หน่วยแล้ว migrate ค่าเก่า | ทำเมื่อผู้จัดการอนุมัติให้ยิง API (ผมห้ามยิงในงานนี้) |
| 8 | `avg_pace_min_per_km` คำนวณจาก `duration` ไม่ใช่เพซของ Garmin และไม่เคยถูกเทียบ | เพซบนการ์ด/ตารางอาจต่างจากแอป Garmin Connect | ทำเช็คลิสต์รายเดือนรอบแรก (docs/ตรวจทานข้อมูล-รายเดือน.md — บันทึกผลยังเขียนว่า 'ยังไม่เคยตรวจ') เทียบเพซ 1 กิจกรรม | ทำได้ทันที ไม่ต้องแก้โค้ด |
| 9 | ไม่ตรวจว่า **วันที่ใน response ตรงกับวันที่ขอ** (sleep/HRV/readiness ใช้ D ที่ส่งไปเก็บเลย; ไม่อ่าน `calendarDate` ของ response) และ 'sleep แถว D = คืนที่จบเช้า D' อ้างจากคำอธิบายบนการ์ดทีมและคอนเวนชัน Garmin ไม่ใช่การตรวจในโค้ด | ถ้าคอนเวนชันของ Garmin ต่างจากที่สมมติ ทุกค่านอนจะเลื่อนหนึ่งวัน | ยิงอ่านอย่างเดียวหนึ่งวัน เทียบ `dailySleepDTO.calendarDate` กับวันที่ขอ | ทำพร้อมข้อ 7 (ใช้การยิงอ่านชุดเดียวกัน) |
| 10 | การ์ดทีมของ p'kao อาจแสดง `HRM 600` เป็นรุ่นนาฬิกา (หัวข้อ dim_athlete_device) | ผู้อ่านเข้าใจเครื่องผิด | เปิดหน้าเว็บดู; ถ้าจริง กรองอุปกรณ์ที่ไม่ใช่นาฬิกาหรือเรียงด้วยชนิดที่ Garmin ระบุ | ตรวจหน้าเว็บก่อน (ผมยังไม่ได้เปิด) |
| 11 | `training_status` เลือก 'เครื่องแรกใน dict ที่มีค่า' สำหรับบัญชีหลายเครื่อง (dan, p'kao) | ถ้าสองเครื่องให้ค่าต่างกัน ไม่รู้ว่าเลือกเครื่องไหน | ยังไม่ต้องแก้ — ไม่มีหลักฐานว่ามีสองค่าต่างกันจริง | เฝ้าดู |
| 12 | ตาราง `fact_gear` และคอลัมน์ readiness factor จำนวนมากเก็บแล้วไม่แสดง | ไม่ใช่ความผิดพลาด (ตั้งใจตามนโยบาย) แต่เป็นตัวเลขที่ไม่มีใครเห็น | ไม่ต้องทำอะไร | – |

**คำถามที่ตอบจากโค้ดไม่ได้จริง ๆ:** (ก) payload ของ `get_stats`/`get_sleep_data`/`get_hrv_data` มีเวลาต้นทาง (เช่นเวลา sync ของนาฬิกา) ให้เก็บหรือไม่; (ข) Garmin ตอบ 404/204 หรือ `[]` ตอนไม่มีข้อมูลแต่ละ endpoint — โค้ดมีทั้งสองทางแต่ไม่ได้บันทึกว่าทางไหนเกิดจริง; (ค) `is_primary_*` ทำไมเป็น NULL; (ง) เหตุที่ 255 แถวถูกแตะซ้ำหลัง 3 วัน (deep/extras/reconcile-window หรือ backfill มือ) — ผมไม่ได้แยกตาม lane เพราะไม่มี lane ติดอยู่กับแถว
