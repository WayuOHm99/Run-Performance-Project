' Run-Performance Garmin sync launcher — รัน garmin-sync-auto.bat แบบไม่มีหน้าต่าง
' Task Scheduler เรียกไฟล์นี้วันละครั้ง เพื่อดึงข้อมูล Garmin (กิจกรรม+wellness)
' ของนักกีฬาทุกคนที่มี token ลง garmin.db อัตโนมัติ โดยไม่มีหน้าต่าง cmd โผล่
' output ไปที่ C:\Backup\garmin-sync-log.txt (redirect ในไฟล์ .bat)
' bWaitOnReturn ต้องเป็น True: ให้ wscript รอจน batch/python จบจริง ไม่งั้น Task Scheduler
' คิดว่างานจบแล้วทั้งที่ python ยังรันอยู่ → กลไก IgnoreNew ไม่ทำงาน → รอบใหม่มาฆ่า
' process ลูกกลางทาง (KeyboardInterrupt ใน log 21 ก.ค. 69)
CreateObject("WScript.Shell").Run "cmd /c ""D:\Run-Performance\garmin\garmin-sync-auto.bat""", 0, True
