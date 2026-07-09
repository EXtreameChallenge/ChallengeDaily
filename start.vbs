Option Explicit
Dim WshShell, fso, scriptDir, clientDir, electronExe, iconPath, shortcutPath, shortcut

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
clientDir = fso.BuildPath(scriptDir, "client")

' 清理可能干扰的 Python 环境变量
WshShell.Environment("PROCESS")("PYTHONHOME") = ""
WshShell.Environment("PROCESS")("PYTHONPATH") = ""
WshShell.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"
WshShell.Environment("PROCESS")("ELECTRON_IS_DEV") = "0"

electronExe = fso.BuildPath(clientDir, "node_modules\electron\dist\electron.exe")
iconPath = fso.BuildPath(clientDir, "public\icon.ico")
shortcutPath = fso.BuildPath(scriptDir, "ChallengeDaily.lnk")

' 前置依赖检查：如果 node_modules 不存在，提示用户先安装依赖
If Not fso.FolderExists(fso.BuildPath(clientDir, "node_modules")) Then
    MsgBox "未检测到前端依赖，请先在 client 目录执行 npm install", vbExclamation, "ChallengeDaily"
    WScript.Quit(1)
End If

' 前置构建检查：如果 dist/index.html 不存在，提示用户先构建
If Not fso.FileExists(fso.BuildPath(clientDir, "dist\index.html")) Then
    MsgBox "未检测到前端构建产物，请先在 client 目录执行 npm run build", vbExclamation, "ChallengeDaily"
    WScript.Quit(1)
End If

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
