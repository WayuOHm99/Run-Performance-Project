' Run-Performance LINE sync launcher ? runs sync-auto.bat with NO visible window.
' Task Scheduler calls this every 15 min so athlete data lands on disk in the
' background, instead of the coach waiting ~9s for a manual pull. Output goes to
' C:\Backup\sync-log.txt (redirected inside sync-auto.bat).
' Path is derived from this script's own folder (never hardcoded), so renaming or
' moving the project folder does not break the scheduled task.
Here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "cmd /c """ & Here & "\sync-auto.bat""", 0, False
