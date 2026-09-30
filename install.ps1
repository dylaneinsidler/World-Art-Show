# Puts a "World Art Show" shortcut on the Desktop.
#   Install:  right-click this file > Run with PowerShell
#   Remove:   run it with -Uninstall

param([switch]$Uninstall)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'World Art Show.lnk'

if ($Uninstall) {
    Remove-Item $shortcut -ErrorAction SilentlyContinue
    Write-Host 'World Art Show shortcut removed from the Desktop.'
    Start-Sleep -Seconds 4
    return
}

# Windows won't quietly run files downloaded from the internet until they're unblocked.
Get-ChildItem $here -File -Recurse | Unblock-File

$link = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcut)
$link.TargetPath = Join-Path $env:SystemRoot 'System32\wscript.exe'
$link.Arguments = "`"$(Join-Path $here 'launch.vbs')`""
$link.WorkingDirectory = $here
$link.IconLocation = "$(Join-Path $here 'art.ico'),0"
$link.Description = 'Art by living artists from around the world, a new piece every minute'
$link.Save()

Write-Host 'Done. Double-click "World Art Show" on your Desktop.'
Start-Sleep -Seconds 4
