# World Art Show on the PC starts here, from the Desktop shortcut (via launch.vbs).
#
# It runs from a copy in AppData that install.ps1 made, refreshed from your World Art Show folder on every
# start. That folder may be on Google Drive, which disconnects for a minute or so when the PC wakes from
# sleep; if it isn't back in time, the last copy runs.

$app = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Get-Content (Join-Path $app 'source.txt') -ErrorAction SilentlyContinue | Select-Object -First 1
$data = Split-Path -Parent $app

# Refresh the copy, giving Google Drive up to 20 seconds to reconnect.
if ($source -and $source -ne $app) {
    # [IO.Path]::Combine, not Join-Path: Join-Path errors out when the drive letter itself is missing.
    $marker = [IO.Path]::Combine($source, 'launch.ps1')
    $deadline = (Get-Date).AddSeconds(20)
    while (-not (Test-Path -LiteralPath $marker) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
    if (Test-Path -LiteralPath $marker) {
        robocopy $source $app index.html about.html *.js *.css *.ps1 *.vbs *.ico /R:1 /W:1 /NJH /NJS /NFL /NDL /NP | Out-Null
    }
}

# DeviantArt blocks GitHub's servers, so this PC collects DeviantArt's daily picks and sends them up
# (tools\fetch_deviantart.py, in your World Art Show folder). Start that in the background when the show
# opens, at most every 6 hours; the daily task (see install.ps1) does it too.
$fetcher = if ($source) { [IO.Path]::Combine($source, 'tools', 'fetch_deviantart.py') }
$lastRun = Join-Path $data 'deviantart-last-run.txt'
$python = (Get-Command pyw.exe, pythonw.exe -ErrorAction SilentlyContinue | Select-Object -First 1).Source
$collecting = Get-CimInstance Win32_Process -Filter "Name LIKE 'py%'" | Where-Object { $_.CommandLine -like '*fetch_deviantart.py*' }
if ($python -and $fetcher -and (Test-Path -LiteralPath $fetcher) -and -not $collecting -and
        (Test-Path (Join-Path $data 'deviantart-key.txt')) -and
        (-not (Test-Path $lastRun) -or (Get-Item $lastRun).LastWriteTime -lt (Get-Date).AddHours(-6))) {
    Start-Process $python -WindowStyle Hidden -WorkingDirectory $source -ArgumentList "`"$fetcher`" --log"
}

& (Join-Path $app 'launch.ps1')
