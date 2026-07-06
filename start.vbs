Option Explicit
Dim WshShell, fso, scriptDir, clientDir, electronExe, iconPath, shortcutPath, shortcut
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
clientDir = fso.BuildPath(scriptDir, "client")

WshShell.Environment("PROCESS")("PYTHONHOME") = ""
WshShell.Environment("PROCESS")("PYTHONPATH") = ""
WshShell.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"
WshShell.Environment("PROCESS")("ELECTRON_IS_DEV") = "0"

electronExe = fso.BuildPath(clientDir, "node_modules\electron\dist\electron.exe")
iconPath = fso.BuildPath(clientDir, "public\icon.ico")
shortcutPath = fso.BuildPath(scriptDir, "ChallengeDaily.lnk")

' 创建/更新带项目图标的快捷方式，确保任务栏显示正确图标
On Error Resume Next
Set shortcut = WshShell.CreateShortcut(shortcutPath)
shortcut.TargetPath = electronExe
shortcut.WorkingDirectory = clientDir
shortcut.Arguments = "."
shortcut.IconLocation = iconPath & ",0"
shortcut.WindowStyle = 1
shortcut.Description = "ChallengeDaily - AI 智能工作日报助手"
shortcut.Save
On Error GoTo 0

WshShell.CurrentDirectory = clientDir
WshShell.Run """" & shortcutPath & """", 1, False
