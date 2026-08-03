' Hidden launcher for the weekly deleted-activity reconcile.
' Same reason as the deep sync launcher: a visible console window is a window someone
' closes, and a killed round cannot report itself. bWaitOnReturn = True so Task
' Scheduler waits for python to really finish.
Here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "cmd /c """ & Here & "\garmin-reconcile-auto.bat""", 0, True
