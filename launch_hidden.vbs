Set files = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDirectory = files.GetParentFolderName(WScript.ScriptFullName)
powerShellScript = files.BuildPath(scriptDirectory, "script.ps1")

command = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File """ & powerShellScript & """"

shell.Run command, 0, False