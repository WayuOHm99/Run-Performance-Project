' Hidden launcher for the dashboard (no console window).
' Binds to 127.0.0.1:8501 only. Phone access goes through "tailscale serve",
' never through a LAN/public port. See docs\PRIVATE_ACCESS.md.
Here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
Garmin = CreateObject("Scripting.FileSystemObject").GetParentFolderName(Here)
Cmd = "cmd /c cd /d """ & Garmin & """ && "".venv\Scripts\python.exe"" -m streamlit run scripts\dashboard.py" & _
      " --server.address 127.0.0.1 --server.port 8501 --server.headless true"
ExitCode = CreateObject("WScript.Shell").Run(Cmd, 0, True)
WScript.Quit ExitCode
