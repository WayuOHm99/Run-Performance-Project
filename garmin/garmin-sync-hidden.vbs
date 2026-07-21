' Run-Performance Garmin sync launcher — รัน garmin-sync-auto.bat แบบไม่มีหน้าต่าง
' Task Scheduler เรียกไฟล์นี้วันละครั้ง เพื่อดึงข้อมูล Garmin (กิจกรรม+wellness)
' ของนักกีฬาทุกคนที่มี token ลง garmin.db อัตโนมัติ โดยไม่มีหน้าต่าง cmd โผล่
' output ไปที่ C:\Backup\garmin-sync-log.txt (redirect ในไฟล์ .bat)
CreateObject("WScript.Shell").Run "cmd /c ""D:\Run-Performance\garmin\garmin-sync-auto.bat""", 0, False
