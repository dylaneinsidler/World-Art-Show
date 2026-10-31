# With only one monitor: both screens side by side on it, each a smaller copy of what it shows on its own monitor. The same file
# in every two-screen app (like close.js); launch.ps1 runs it right after it reads $screens.
#
# Each page still thinks it has a whole 1920 x 1080 monitor (Chrome is told to draw everything smaller, by $screenMode), so every
# app looks just as it does on two monitors, only smaller, and the X, Light / Dark and the screens talking to each other all work
# as usual. With two monitors or more this does nothing: $screenMode is plain full screen, as ever.
# (To try it with two monitors plugged in: $env:DYLAN_ONE_MONITOR = '1'.)

$screenMode = '--kiosk'
function Fit-OneMonitor($panels, [switch]$Once) { }

if (@($screens).Count -lt 2 -or $env:DYLAN_ONE_MONITOR) {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class DylanOneMonitor {
    [DllImport("user32.dll")] public static extern IntPtr GetDC(IntPtr hwnd);
    [DllImport("user32.dll")] public static extern int ReleaseDC(IntPtr hwnd, IntPtr hdc);
    [DllImport("gdi32.dll")] public static extern int GetDeviceCaps(IntPtr hdc, int index);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int w, int h, uint flags);
    // The monitor's true width in pixels, whatever Windows' display scaling is set to.
    public static int TrueWidth() { IntPtr dc = GetDC(IntPtr.Zero); int w = GetDeviceCaps(dc, 118); ReleaseDC(IntPtr.Zero, dc); return w; }
}
"@
    $oneScreen = @($screens)[0]
    $work = $oneScreen.WorkingArea
    # Half the room for each screen, 16:9 like a monitor, with room for the window's top bar, in the middle of the monitor.
    $halfWidth = [int][math]::Floor($work.Width / 2)
    $barHeight = 32
    $panelHeight = [math]::Min($work.Height, [int]($halfWidth * 9 / 16) + $barHeight)
    $panelTop = $work.Y + [int](($work.Height - $panelHeight) / 2)
    $oneMonitorAreas = @(
        @{ X = $work.X; Y = $panelTop; W = $halfWidth; H = $panelHeight },
        @{ X = $work.X + $halfWidth; Y = $panelTop; W = $halfWidth; H = $panelHeight }
    )
    # Draw 1920 across in the true pixels that half the monitor has.
    $trueWidth = [DylanOneMonitor]::TrueWidth()
    $zoom = [math]::Round($halfWidth * ($trueWidth / $oneScreen.Bounds.Width) / 1920, 4)
    $screenMode = "--force-device-scale-factor=$zoom"
    # What launch.ps1 sees: two "monitors", so it opens both pages the usual way. The window size here is only where Chrome
    # starts; Fit-OneMonitor puts each window exactly where it belongs once it's up.
    $screens = @(0, 1) | ForEach-Object {
        $a = $oneMonitorAreas[$_]
        [pscustomobject]@{ Bounds = [pscustomobject]@{ X = $a.X; Y = $a.Y; Width = 1920; Height = 1110 } }
    }
    # Puts each window in its place, once per window. Waits for slow ones (Chrome can be slow just after the PC wakes); -Once just
    # looks, for a launcher that checks again later.
    $oneMonitorPlaced = @{}
    function Fit-OneMonitor($panels, [switch]$Once) {
        $deadline = (Get-Date).AddSeconds(45)
        do {
            $waiting = $false
            foreach ($i in 0, 1) {
                $p = @($panels)[$i]
                $p.Refresh()
                $window = $p.MainWindowHandle
                if ($window -eq [IntPtr]::Zero) { if (-not $p.HasExited) { $waiting = $true }; continue }
                if ($oneMonitorPlaced[[string]$window]) { continue }
                $a = $oneMonitorAreas[$i]
                [DylanOneMonitor]::SetWindowPos($window, [IntPtr]::Zero, $a.X, $a.Y, $a.W, $a.H, 0x0014) | Out-Null   # keep its order and focus
                $oneMonitorPlaced[[string]$window] = $true
            }
            if ($waiting -and -not $Once) { Start-Sleep -Milliseconds 200 }
        } while ($waiting -and -not $Once -and (Get-Date) -lt $deadline)
    }
}
