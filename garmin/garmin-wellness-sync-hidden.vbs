' Hidden launcher for the frequent lightweight Garmin wellness sync.
Here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "cmd /c """ & Here & "\garmin-wellness-sync-auto.bat""", 0, True
