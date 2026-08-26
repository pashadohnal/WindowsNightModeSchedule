Set shell = CreateObject("WScript.Shell")

command = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""script.ps1"""

shell.Run command, 0, False
