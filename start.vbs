Option Explicit
Dim WshShell, fso, scriptDir, clientDir
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
clientDir = fso.BuildPath(scriptDir, "client")

WshShell.Environment("PROCESS")("PYTHONHOME") = ""
WshShell.Environment("PROCESS")("PYTHONPATH") = ""
WshShell.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"
WshShell.Environment("PROCESS")("ELECTRON_IS_DEV") = "0"

Dim electronExe
electronExe = fso.BuildPath(clientDir, "node_modules\electron\dist\electron.exe")

WshShell.CurrentDirectory = clientDir
WshShell.Run """" & electronExe & """ .", 1, False
