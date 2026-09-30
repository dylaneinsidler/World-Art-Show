# World Art Show: opens the art window, large and centered on the screen the mouse is on.
# Started from the Desktop shortcut (see install.ps1). If the window is already open, this brings it to the front.

# The show lives on the website (the same one the iPad uses), which GitHub keeps up to date with new art.
$showUrl = 'https://dylaneinsidler.github.io/World-Art-Show/'
$windowShare = 0.84   # the window's share of the screen's width and height

$ErrorActionPreference = 'SilentlyContinue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
# The window's browser profile lives in AppData, not next to these files: thousands of small files that change
# constantly, which would churn a synced folder like Google Drive. It also keeps the show's memory of what it
# has already shown.
$profileDir = Join-Path $env:LOCALAPPDATA 'WorldArtShow\browser-profile'

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WorldArtShowNative {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hwnd, int cmd);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int w, int h, uint flags);
    public static void BringToFront(IntPtr hwnd) {
        if (IsIconic(hwnd)) ShowWindow(hwnd, 9);                                   // un-minimize
        SetWindowPos(hwnd, new IntPtr(-1), 0, 0, 0, 0, 0x0043);                   // on top of everything...
        SetWindowPos(hwnd, new IntPtr(-2), 0, 0, 0, 0, 0x0043);                   // ...then an ordinary window again
        SetForegroundWindow(hwnd);
    }
}
"@
# Measure the screen in real pixels, the same units the browser uses for its window.
[WorldArtShowNative]::SetProcessDPIAware() | Out-Null

# DeviantArt blocks GitHub's servers, so this PC collects DeviantArt's daily picks and sends them up
# (toolsetch_deviantart.py). Start that in the background when the show opens, at most every 6 hours.
$home_ = Join-Path $env:LOCALAPPDATA 'WorldArtShow'
$lastRun = Join-Path $home_ 'deviantart-last-run.txt'
$python = (Get-Command pyw.exe, pythonw.exe -ErrorAction SilentlyContinue | Select-Object -First 1).Source
$collecting = Get-CimInstance Win32_Process -Filter "Name LIKE 'py%'" | Where-Object { $_.CommandLine -like '*fetch_deviantart.py*' }
if ($python -and -not $collecting -and (Test-Path (Join-Path $home_ 'deviantart-key.txt')) -and
        (-not (Test-Path $lastRun) -or (Get-Item $lastRun).LastWriteTime -lt (Get-Date).AddHours(-6))) {
    Start-Process $python -WindowStyle Hidden -ArgumentList "`"$(Join-Path $here 'toolsetch_deviantart.py')`" --log"
}

# Already open: bring it forward instead of opening a second window.
$running = Get-CimInstance Win32_Process -Filter "Name='chrome.exe' OR Name='msedge.exe'" |
    Where-Object { $_.CommandLine -like '*WorldArtShow\browser-profile*' -and $_.CommandLine -notlike '*--type=*' }
foreach ($p in $running) {
    $hwnd = (Get-Process -Id $p.ProcessId).MainWindowHandle
    if ($hwnd -and $hwnd -ne [IntPtr]::Zero) {
        [WorldArtShowNative]::BringToFront($hwnd)
        return
    }
    # Still running but its window is gone (it was just closed): let it finish so a fresh one can open.
    Stop-Process -Id $p.ProcessId -Force
    Start-Sleep -Milliseconds 800
}

$browser = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show('World Art Show needs Google Chrome or Microsoft Edge.', 'World Art Show') | Out-Null
    return
}

# Skip the browser's "restore pages?" prompt if it was closed by a shutdown.
$prefs = Join-Path $profileDir 'Default\Preferences'
if (Test-Path $prefs) {
    $text = [IO.File]::ReadAllText($prefs) -replace '"exit_type":"Crashed"', '"exit_type":"Normal"'
    # The browser reopens a window where it was last closed; forget that so it always opens centered.
    $text = $text -replace '"app_window_placement":\{("[^"]*":\{"[^"]*":\{[^{}]*\}\},?)*\}', '"app_window_placement":{}'
    [IO.File]::WriteAllText($prefs, $text, (New-Object Text.UTF8Encoding $false))
}

Add-Type -AssemblyName System.Windows.Forms
$area = [System.Windows.Forms.Screen]::FromPoint([System.Windows.Forms.Cursor]::Position).WorkingArea
$width = [int]($area.Width * $windowShare)
$height = [int]($area.Height * $windowShare)
$x = $area.X + [int](($area.Width - $width) / 2)
$y = $area.Y + [int](($area.Height - $height) / 2)

$proc = Start-Process $browser -PassThru -ArgumentList @(
    "--user-data-dir=`"$profileDir`"",
    '--no-first-run', '--no-default-browser-check', '--hide-crash-restore-bubble',
    "--app=$showUrl", "--window-position=$x,$y", "--window-size=$width,$height"
)

# With display scaling above 100%, the browser reads the size above in its own units; set it exactly.
# And make sure the window opens in front rather than behind whatever was active.
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 250
    $proc.Refresh()
    if ($proc.HasExited) { break }
    if ($proc.MainWindowHandle -ne [IntPtr]::Zero) {
        [WorldArtShowNative]::SetWindowPos($proc.MainWindowHandle, [IntPtr]::Zero, $x, $y, $width, $height, 0x0004) | Out-Null
        [WorldArtShowNative]::BringToFront($proc.MainWindowHandle)
        break
    }
}
