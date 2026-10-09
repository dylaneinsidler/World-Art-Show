# Sets up World Art Show on this PC: a "World Art Show" shortcut on the Desktop that opens it on two screens
# (the art on the left, its story on the right), and a daily task that collects DeviantArt's picks for the
# show (DeviantArt blocks GitHub's servers, so this PC does it).
#   Install:  right-click this file > Run with PowerShell
#   Remove:   run it with -Uninstall
#
# The show runs from a copy in AppData, which refreshes itself from this folder every time it starts.
# That way it still opens if this folder is on a drive that isn't ready yet, like Google Drive right
# after the PC wakes from sleep. Keep editing the files here, not the copy.

param([switch]$Uninstall)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'World Art Show.lnk'
$taskName = 'World Art Show - DeviantArt picks'
$home_ = Join-Path $env:LOCALAPPDATA 'WorldArtShow'
$keyFile = Join-Path $home_ 'deviantart-key.txt'
$app = Join-Path $home_ 'app'

if ($Uninstall) {
    Remove-Item $shortcut -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item $app -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host 'World Art Show removed (Desktop shortcut, daily task, and its copy in AppData). Your DeviantArt key is kept.'
    Start-Sleep -Seconds 4
    return
}

New-Item -ItemType Directory -Force $app | Out-Null
robocopy $here $app index.html about.html *.js *.css *.ps1 *.vbs *.ico /R:1 /W:1 /NJH /NJS /NFL /NDL /NP | Out-Null
Set-Content (Join-Path $app 'source.txt') $here
# Windows won't quietly run files downloaded from the internet until they're unblocked.
Get-ChildItem $here -File -Recurse | Unblock-File
Get-ChildItem $app -File | Unblock-File

$link = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcut)
$link.TargetPath = Join-Path $env:SystemRoot 'System32\wscript.exe'
$link.Arguments = "`"$(Join-Path $app 'launch.vbs')`""
$link.WorkingDirectory = $app
$link.IconLocation = "$(Join-Path $app 'art.ico'),0"
$link.Description = 'A new piece of art every minute on the left screen, its story on the right'
$link.Save()

# The DeviantArt key lives here, outside the synced folder and the repository.
New-Item -ItemType Directory -Force $home_ | Out-Null
if (-not (Test-Path $keyFile)) {
    Set-Content $keyFile -Encoding UTF8 -Value @(
        'client_id=paste your client_id here',
        'client_secret=paste your client_secret here'
    )
}

# Once a day (or as soon as the PC is on after that), collect DeviantArt's newest picks and send them up.
$python = (Get-Command pyw.exe, pythonw.exe -ErrorAction SilentlyContinue | Select-Object -First 1).Source
if ($python) {
    $action = New-ScheduledTaskAction -Execute $python -WorkingDirectory $here `
        -Argument "`"$(Join-Path $here 'tools\fetch_deviantart.py')`" --log"
    $trigger = New-ScheduledTaskTrigger -Daily -At '9:00 AM'
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
        -Principal $principal -Description 'Collects DeviantArt picks for World Art Show.' -Force | Out-Null
} else {
    Write-Host 'Python is not installed, so DeviantArt picks will not be collected on this PC.'
}

Write-Host 'Done. Double-click "World Art Show" on your Desktop.'
Start-Sleep -Seconds 4
