# Sets up World Art Show on this PC: a "World Art Show" shortcut on the Desktop, and a daily task that collects
# DeviantArt's picks for the show (DeviantArt blocks GitHub's servers, so this PC does it).
#   Install:  right-click this file > Run with PowerShell
#   Remove:   run it with -Uninstall

param([switch]$Uninstall)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'World Art Show.lnk'
$taskName = 'World Art Show - DeviantArt picks'
$home_ = Join-Path $env:LOCALAPPDATA 'WorldArtShow'
$keyFile = Join-Path $home_ 'deviantart-key.txt'

if ($Uninstall) {
    Remove-Item $shortcut -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host 'World Art Show removed (Desktop shortcut and daily task).'
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
$link.Description = 'New art by living artists from around the world, a new piece every minute'
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
