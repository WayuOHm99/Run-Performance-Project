' Hidden launcher for the full Garmin activity and wellness sync.
' Wait for the batch so Task Scheduler sees the real duration and exit code; otherwise
' IgnoreNew cannot prevent overlapping child processes. The path is location-relative.
' Output is redirected to C:\Backup\run-performance-logs\garmin-sync-full.log.
Here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
ExitCode = CreateObject("WScript.Shell").Run("cmd /c """ & Here & "\garmin-sync-auto.bat""", 0, True)
WScript.Quit ExitCode
