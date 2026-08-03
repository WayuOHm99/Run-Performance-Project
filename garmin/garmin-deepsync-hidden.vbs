' Hidden launcher for the monthly deep wellness resync.
' Hidden matters here: this lane runs for minutes, and a console window that CAN be
' closed WILL be closed - the 2026-08-02 round died that way (exit 0xC000013A) at
' "Day 1/46" and nothing reported it, because a killed .bat never reaches its notify
' line. bWaitOnReturn = True so Task Scheduler waits for python to really finish.
Here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "cmd /c """ & Here & "\garmin-deepsync-auto.bat""", 0, True
