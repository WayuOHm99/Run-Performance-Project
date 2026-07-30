' Hidden launcher for the frequent lightweight Garmin activity sync.
Here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "cmd /c """ & Here & "\garmin-fast-sync-auto.bat""", 0, True
