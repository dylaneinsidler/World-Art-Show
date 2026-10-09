# World Art Show on the PC: the art (index.html?desktop) on the left monitor and everything about it
# (about.html) on the right, both full screen. Run by start.ps1, from the Desktop shortcut (see install.ps1).
#   - The two screens talk to each other through a tiny web server that this script runs, which only
#     this PC can reach (http://localhost:47233). It also looks up DeviantArt pieces for the right screen
#     with the PC's DeviantArt key, and remembers the Light / Dark switch.
#   - The X in the top right corner of either screen (or Esc) closes both.
#   - The screens stay on for up to 4 hours while it's open; after that they can go dark as usual.
#   - Run it with -Preview to start only the web server (no windows), then open
#     http://localhost:47233/index.html?desktop and http://localhost:47233/about.html in any browser.

param(
    [switch]$Preview,
    [int]$Port = 47233
)

# The web server answers requests one by one, with a pause between each, in PowerShell's default
# (STA) mode; in MTA mode it's instant. launch.vbs starts it that way; if something else didn't,
# start over in MTA.
if ([Threading.Thread]::CurrentThread.GetApartmentState() -ne 'MTA') {
    $again = @('-MTA', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-WindowStyle', 'Hidden', '-File', "`"$PSCommandPath`"", '-Port', $Port)
    if ($Preview) { $again += '-Preview' }
    Start-Process powershell.exe -ArgumentList $again -WindowStyle Hidden
    return
}

$port = $Port
$keepScreensOnHours = 4

$ErrorActionPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
# Browser profiles, the DeviantArt key and the Light / Dark setting live in AppData, never in a synced
# folder like Google Drive. The art screen keeps the show's old profile, so it remembers what it has shown.
$data = Join-Path $env:LOCALAPPDATA 'WorldArtShow'
$profileDirs = @{ art = Join-Path $data 'browser-profile'; about = Join-Path $data 'profile-about' }
$themeFile = Join-Path $data 'theme.txt'
New-Item -ItemType Directory -Force $data | Out-Null

function Get-PanelProcesses {
    Get-CimInstance Win32_Process -Filter "Name='chrome.exe' OR Name='msedge.exe'" |
        Where-Object { $_.CommandLine -like '*AppData\Local\WorldArtShow\browser-profile*' -or
                       $_.CommandLine -like '*AppData\Local\WorldArtShow\profile-about*' }
}

function Close-Panels {
    Get-PanelProcesses | Where-Object { $_.CommandLine -notlike '*--type=*' } |
        ForEach-Object { taskkill.exe /F /T /PID $_.ProcessId | Out-Null }
    # Wait until the browser lets go of each profile. A window opened before then just vanishes.
    foreach ($dir in $profileDirs.Values) {
        $lock = Join-Path $dir 'lockfile'
        for ($i = 0; $i -lt 20 -and (Test-Path $lock); $i++) {
            Remove-Item $lock -Force
            if (Test-Path $lock) { Start-Sleep -Milliseconds 500 }
        }
    }
}

# Opening it again: the copy that's already running gives way to this one, and frees the web server's port.
if (-not $Preview) {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
        Where-Object { $_.CommandLine -like '*\WorldArtShow\app\*' -and $_.CommandLine -match '(start|launch)\.ps1' -and $_.ProcessId -ne $PID } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Close-Panels
}

# ---- The web server ----

$listener = $null
for ($i = 0; $i -lt 40 -and -not $listener; $i++) {
    $l = New-Object System.Net.HttpListener
    $l.Prefixes.Add("http://localhost:$port/")
    try { $l.Start(); $listener = $l } catch { $l.Close(); Start-Sleep -Milliseconds 250 }
}
if (-not $listener) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show("World Art Show couldn't start, because something else on this PC is using port $port.",
        'World Art Show') | Out-Null
    return
}

$state = @{}      # what the two screens share (the piece on screen, a button pressed, Light / Dark): name -> JSON text
$version = 0      # goes up with every change, so each screen knows when there's something new
$waiting = New-Object System.Collections.ArrayList   # screens waiting to hear about the next change
$savedTheme = (Get-Content -LiteralPath $themeFile -ErrorAction SilentlyContinue | Select-Object -First 1)
$state['theme'] = if ($savedTheme -eq 'light') { '"light"' } else { '"dark"' }
# Digital art (DeviantArt's picks) on or off, from the right screen's switch: off until turned on. Kept in
# digital.txt, so every copy of the show (this app, the Morning and Night Screens, the tester) agrees.
$digitalFile = Join-Path $data 'digital.txt'
$state['digital'] = if ((Get-Content -LiteralPath $digitalFile -ErrorAction SilentlyContinue | Select-Object -First 1) -eq 'true') { 'true' } else { 'false' }
# Pieces you never want to see again (the "Don't show again" button on the right screen), one address per
# line in hidden.txt, shared by every copy of the show.
$hiddenFile = Join-Path $data 'hidden.txt'
function Get-HiddenJson {
    $pages = @(Get-Content -LiteralPath $hiddenFile -ErrorAction SilentlyContinue | Where-Object { $_ -match '^https?://' })
    '[' + (($pages | ForEach-Object { ConvertTo-Json ([string]$_) }) -join ',') + ']'
}
$state['hidden'] = Get-HiddenJson

$types = @{
    '.html' = 'text/html; charset=utf-8'; '.js' = 'text/javascript; charset=utf-8'; '.css' = 'text/css; charset=utf-8'
    '.json' = 'application/json; charset=utf-8'; '.png' = 'image/png'; '.ico' = 'image/x-icon'
}

function Send($ctx, [byte[]]$bytes, $type, [int]$code = 200) {
    try {
        $ctx.Response.StatusCode = $code
        $ctx.Response.ContentType = $type
        $ctx.Response.Headers['Cache-Control'] = 'no-store'
        $ctx.Response.ContentLength64 = $bytes.Length
        $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
        $ctx.Response.Close()
    } catch { try { $ctx.Response.Abort() } catch {} }
}
function Send-Text($ctx, [string]$text, $type = 'application/json; charset=utf-8', [int]$code = 200) {
    Send $ctx ([Text.Encoding]::UTF8.GetBytes($text)) $type $code
}
function Read-Body($req) {
    $reader = New-Object IO.StreamReader($req.InputStream, [Text.Encoding]::UTF8)
    try { $reader.ReadToEnd() } finally { $reader.Close() }
}
function Get-StateJson {
    $parts = foreach ($k in $state.Keys) { '"' + $k + '":' + $state[$k] }
    '{"v":' + $script:version + ',"state":{' + ($parts -join ',') + '}}'
}
function Send-ToWaiting {
    $json = Get-StateJson
    foreach ($w in $waiting) { Send-Text $w.Ctx $json }
    $waiting.Clear()
}

# ---- DeviantArt: the artist's own words about a piece, and their profile ----
# The browser can't ask DeviantArt itself (it needs the key, which stays on this PC), so the right screen
# asks here. The piece's page gives its id; the DeviantArt API gives its description, and the artist's
# profile (real name, country, specialty, bio). Answers are kept for as long as the show is open.

$userAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36'
$daToken = $null
$daTokenUntil = Get-Date
$daAnswers = @{}

function Get-Web($url, $headers = @{}) {
    $wc = New-Object Net.WebClient
    $wc.Encoding = [Text.Encoding]::UTF8
    $wc.Headers['User-Agent'] = $userAgent
    foreach ($k in $headers.Keys) { $wc.Headers[$k] = $headers[$k] }
    try { $wc.DownloadString($url) } finally { $wc.Dispose() }
}

function Get-DeviantArtToken {
    if ($script:daToken -and (Get-Date) -lt $script:daTokenUntil) { return $script:daToken }
    $key = @{}
    Get-Content -LiteralPath (Join-Path $data 'deviantart-key.txt') -ErrorAction Stop |
        Where-Object { $_ -match '^\s*(\w+)\s*=\s*(.+?)\s*$' } | ForEach-Object { $key[$Matches[1]] = $Matches[2] }
    if (-not $key.client_id -or $key.client_id -like '*paste*') { throw 'no DeviantArt key on this PC' }
    $wc = New-Object Net.WebClient
    try {
        $form = New-Object Collections.Specialized.NameValueCollection
        $form.Add('grant_type', 'client_credentials'); $form.Add('client_id', $key.client_id); $form.Add('client_secret', $key.client_secret)
        $answer = [Text.Encoding]::UTF8.GetString($wc.UploadValues('https://www.deviantart.com/oauth2/token', $form)) | ConvertFrom-Json
    } finally { $wc.Dispose() }
    $script:daToken = $answer.access_token
    $script:daTokenUntil = (Get-Date).AddMinutes(50)
    $script:daToken
}

function Get-DeviantArt($page) {
    if ($daAnswers.ContainsKey($page)) { return $daAnswers[$page] }
    try {
        if ($page -notmatch '^https://www\.deviantart\.com/') { throw 'not a DeviantArt page' }
        $html = Get-Web $page
        if ($html -notmatch 'deviationUuid\\+"\s*:\s*\\+"([0-9A-Fa-f-]{36})') { throw 'no id on the page' }
        $uuid = $Matches[1]
        $auth = @{ Authorization = 'Bearer ' + (Get-DeviantArtToken) }
        $api = 'https://www.deviantart.com/api/v1/oauth2'
        $m = (Get-Web "$api/deviation/metadata?deviationids[]=$uuid&ext_submission=true&ext_stats=true" $auth | ConvertFrom-Json).metadata[0]
        $p = Get-Web "$api/user/profile/$([Uri]::EscapeDataString($m.author.username))" $auth | ConvertFrom-Json
        $json = [ordered]@{
            description = $m.description
            tags        = @($m.tags | ForEach-Object { $_.tag_name })
            created     = $m.submission.creation_time
            resolution  = $m.submission.resolution
            views       = $m.stats.views
            favourites  = $m.stats.favourites
            artist      = [ordered]@{
                username = $m.author.username; usericon = $p.user.usericon; realName = $p.real_name
                tagline = $p.tagline; country = $p.country; website = $p.website; bio = $p.bio
                level = $p.artist_level; specialty = $p.artist_specialty; profileUrl = $p.profile_url
            }
        } | ConvertTo-Json -Depth 5 -Compress
        $daAnswers[$page] = $json
        $json
    } catch {
        '{"error":' + (ConvertTo-Json ([string]$_.Exception.Message)) + '}'
    }
}

function Invoke-Request($ctx) {
    $req = $ctx.Request
    $path = $req.Url.AbsolutePath

    # /api/state: a screen posts a change (?key=now, command or theme), or asks for the state, waiting up
    # to 20 seconds for a change if it already has the latest (?v=its version).
    if ($path -eq '/api/state') {
        if ($req.HttpMethod -eq 'POST') {
            $key = $req.QueryString['key']
            $body = Read-Body $req
            if ($key -eq 'hide' -and $body) {
                # One more piece never to show: add it to hidden.txt, and tell both screens.
                $page = ($body | ConvertFrom-Json)
                if ($page -match '^https?://') { Add-Content -LiteralPath $hiddenFile $page }
                $state['hidden'] = Get-HiddenJson
                $script:version++
                Send-ToWaiting
            }
            elseif ($key -match '^[a-z]+$' -and $body) {
                $state[$key] = $body
                $script:version++
                Send-ToWaiting
                if ($key -eq 'theme') { Set-Content -LiteralPath $themeFile ($body.Trim('"')) }
                if ($key -eq 'digital') { Set-Content -LiteralPath $digitalFile ($body.Trim()) }
            }
            Send-Text $ctx ('{"v":' + $script:version + '}')
        } else {
            $since = 0
            [void][int]::TryParse($req.QueryString['v'], [ref]$since)
            if ($since -ne $script:version) { Send-Text $ctx (Get-StateJson) }
            else { [void]$waiting.Add(@{ Ctx = $ctx; Until = (Get-Date).AddSeconds(20) }) }
        }
        return
    }

    if ($path -eq '/api/deviantart') {
        Send-Text $ctx (Get-DeviantArt $req.QueryString['page'])
        return
    }

    # Everything else: the show's own files.
    $rel = [Uri]::UnescapeDataString($path).TrimStart('/')
    if ($rel -eq '') { $rel = 'about.html' }
    $ext = [IO.Path]::GetExtension($rel).ToLower()
    $file = Join-Path $here $rel
    if ($rel -notmatch '\.\.' -and $types.ContainsKey($ext) -and (Test-Path -LiteralPath $file -PathType Leaf)) {
        Send $ctx ([IO.File]::ReadAllBytes($file)) $types[$ext]
    } else {
        Send-Text $ctx 'Not found' 'text/plain' 404
    }
}

# ---- The two windows ----

$panels = @()
if (-not $Preview) {
    $browser = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $browser) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show('World Art Show needs Google Chrome or Microsoft Edge.', 'World Art Show') | Out-Null
        $listener.Stop(); return
    }

    function Open-Panel($name, $page, $screen) {
        $profileDir = $profileDirs[$name]
        # Skip Chrome's "restore pages?" prompt after a forced close.
        $prefs = Join-Path $profileDir 'Default\Preferences'
        if (Test-Path $prefs) {
            $text = [IO.File]::ReadAllText($prefs) -replace '"exit_type":"Crashed"', '"exit_type":"Normal"'
            [IO.File]::WriteAllText($prefs, $text, (New-Object Text.UTF8Encoding $false))
        }
        # Aim at the middle of the monitor; kiosk mode then fills that monitor.
        $x = $screen.Bounds.X + [int]($screen.Bounds.Width / 2) - 200
        $y = $screen.Bounds.Y + [int]($screen.Bounds.Height / 2) - 150
        Start-Process $browser -PassThru -ArgumentList @(
            "--user-data-dir=`"$profileDir`"",
            '--no-first-run', '--no-default-browser-check', '--hide-crash-restore-bubble', '--disable-features=Translate',
            '--autoplay-policy=no-user-gesture-required',
            "--app=http://localhost:$port/$page", "--window-position=$x,$y", '--window-size=400,300', '--kiosk'
        )
    }

    Add-Type -AssemblyName System.Windows.Forms
    $screens = [System.Windows.Forms.Screen]::AllScreens | Sort-Object { $_.Bounds.X }
    # With one monitor, the art opens last, so it's on top.
    $panels = if ($screens.Count -gt 1) { @((Open-Panel 'art' 'index.html?desktop' $screens[0]), (Open-Panel 'about' 'about.html' $screens[-1])) }
              else { @((Open-Panel 'about' 'about.html' $screens[0]), (Open-Panel 'art' 'index.html?desktop' $screens[0])) }

    Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WorldArtShowNative {
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, int dx, int dy, uint data, UIntPtr extra);
    [DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint flags);
}
"@
    # Turn the screens on (a one-pixel mouse nudge counts as activity) and keep them on.
    [WorldArtShowNative]::mouse_event(1, 1, 0, 0, [UIntPtr]::Zero)
    [WorldArtShowNative]::mouse_event(1, -1, 0, 0, [UIntPtr]::Zero)
    [WorldArtShowNative]::SetThreadExecutionState([uint32]2147483651) | Out-Null  # CONTINUOUS | SYSTEM | DISPLAY
}

# ---- Serve until a window closes ----

$next = $listener.GetContextAsync()
$keepOnUntil = (Get-Date).AddHours($keepScreensOnHours)
$keepingAwake = -not $Preview
$hadWindow = @{}
$lastCheck = Get-Date
while ($true) {
    # Answer the next request as soon as it arrives; otherwise look around every 25 ms.
    $got = $false
    try { $got = $next.Wait(25) } catch { $next = $listener.GetContextAsync() }
    if ($got) {
        $ctx = $next.Result
        $next = $listener.GetContextAsync()
        try { Invoke-Request $ctx } catch { try { $ctx.Response.Abort() } catch {} }
        continue
    }

    if ($waiting.Count) {
        $now = Get-Date
        foreach ($w in @($waiting | Where-Object { $_.Until -lt $now })) {
            Send-Text $w.Ctx (Get-StateJson)
            [void]$waiting.Remove($w)
        }
    }

    if ($Preview -or ((Get-Date) - $lastCheck).TotalMilliseconds -lt 500) { continue }
    $lastCheck = Get-Date

    # Closing either window closes the other one with it. Watch the windows, not the processes:
    # Chrome keeps running for a few seconds after its window closes.
    $oneClosed = $false
    foreach ($p in $panels) {
        $p.Refresh()
        if ($p.HasExited) { $oneClosed = $true }
        elseif ($p.MainWindowHandle -ne [IntPtr]::Zero) { $hadWindow[$p.Id] = $true }
        # No window: closed, unless it's still starting up.
        elseif ($hadWindow[$p.Id] -or ((Get-Date) - $p.StartTime).TotalSeconds -gt 20) { $oneClosed = $true }
    }
    if ($oneClosed) { Close-Panels; break }

    if ($keepingAwake -and (Get-Date) -ge $keepOnUntil) {
        [WorldArtShowNative]::SetThreadExecutionState([uint32]2147483648) | Out-Null  # let the screens sleep again
        $keepingAwake = $false
    }
}

$listener.Stop()
$listener.Close()
