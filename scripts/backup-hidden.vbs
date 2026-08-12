' Hidden launcher for the nightly project backup.
'
' Every Garmin lane already runs windowless for one reason: a console window that CAN
' be closed WILL be closed. Backup was the last job still launched as cmd.exe + .bat
' directly, and it paid for it - the 2026-08-03 22:00 run died mid-mirror (exit
' 0xC000013A) without a sound, and this job holds the ONLY copy of garmin.db
' (garmin\data\ is git-ignored, so nothing else has a second copy).
'
' bWaitOnReturn = True so Task Scheduler waits for robocopy + the db snapshot to end.
'
' The .bat has a Thai filename, and a .vbs saved as plain ASCII cannot contain Thai
' literals - so build the name from code points. VBScript strings are UTF-16 in
' memory and .Run calls the wide API, so the real Unicode name reaches cmd.exe intact.
Dim Here, BatName, CmdLine, ExitCode
Here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
BatName = ChrW(&H0E2A) & ChrW(&H0E33) & ChrW(&H0E23) & ChrW(&H0E2D) & ChrW(&H0E07) & _
          ChrW(&H0E02) & ChrW(&H0E49) & ChrW(&H0E2D) & ChrW(&H0E21) & ChrW(&H0E39) & _
          ChrW(&H0E25) & ".bat"
' "auto" = do not pause waiting for Enter at the end (there is no window to press it in)
CmdLine = "cmd /c """"" & Here & "\" & BatName & """ auto"""
ExitCode = CreateObject("WScript.Shell").Run(CmdLine, 0, True)
WScript.Quit ExitCode
