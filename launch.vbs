' Starts Dylan's World Art Show on the PC (start.ps1) with no console window flashing on screen.
' -MTA: launch.ps1's little web server answers instantly in that mode.
Set shell = CreateObject("WScript.Shell")
folder = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.Run "powershell.exe -MTA -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & folder & "\start.ps1""", 0, False
