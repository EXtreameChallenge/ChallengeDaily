Option Explicit
Dim WshShell, fso, scriptDir, clientDir, electronExe, iconPath, shortcutPath, shortcut

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
clientDir = fso.BuildPath(scriptDir, "client")

' Clear Python env vars that may interfere
WshShell.Environment("PROCESS")("PYTHONHOME") = ""
WshShell.Environment("PROCESS")("PYTHONPATH") = ""
WshShell.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"
WshShell.Environment("PROCESS")("ELECTRON_IS_DEV") = "0"

electronExe = fso.BuildPath(clientDir, "node_modules\electron\dist\electron.exe")
iconPath = fso.BuildPath(clientDir, "public\icon.ico")
shortcutPath = fso.BuildPath(scriptDir, "ChallengeDaily.lnk")

' Pre-check: if node_modules missing, prompt user to install deps
If Not fso.FolderExists(fso.BuildPath(clientDir, "node_modules")) Then
    MsgBox "Dependencies not found. Please run 'npm install' in client folder first.", vbExclamation, "ChallengeDaily"
    WScript.Quit
End If

' Pre-check: if dist/index.html missing, prompt user to build
If Not fso.FileExists(fso.BuildPath(clientDir, "dist\index.html")) Then
    MsgBox "Build output not found. Please run 'npm run build' in client folder first.", vbExclamation, "ChallengeDaily"
    WScript.Quit
End If

' Create/update shortcut with project icon for correct taskbar display
On Error Resume Next
Set shortcut = WshShell.CreateShortcut(shortcutPath)
shortcut.TargetPath = electronExe
shortcut.WorkingDirectory = clientDir
shortcut.Arguments = "."
shortcut.IconLocation = iconPath & ",0"
shortcut.WindowStyle = 1
shortcut.Description = "ChallengeDaily - AI Daily Report Assistant"
shortcut.Save
On Error GoTo 0

WshShell.CurrentDirectory = clientDir
WshShell.Run """" & shortcutPath & """", 1, False
