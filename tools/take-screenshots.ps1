# Takes a fresh set of screenshots of the show's two screens side by side, for the version in the VERSION file,
# into screenshots\v<version>-<scene> (one wide picture per scene in tools\screenshots.json).
#   Run:  .\tools\take-screenshots.ps1            (or -Version 1.2 to name them yourself)
#
# The shared picture tool (from Dylan's Jiu-Jitsu & Judo), with one difference: the show's pages are web pages
# from its own small server, so this starts the preview (launch.ps1 -Preview -Port 47236) first and stops it
# after. It opens its own hidden Chrome, so it can run while the show is open. Needs Node.js and Chrome.

param([string]$Version = '')

$root = Split-Path -Parent $PSScriptRoot
if (-not $Version) { $Version = (Get-Content (Join-Path $root 'VERSION') -Raw).Trim() }
$out = Join-Path $root 'screenshots'
$env:SCREENSHOT_PREFIX = "v$Version-"   # each picture: screenshots\v<version>-<scene>
$temp = Join-Path $env:TEMP ('screenshots-' + ((Split-Path $root -Leaf) -replace '[^A-Za-z0-9]', ''))
$config = Join-Path $PSScriptRoot 'screenshots.json'
$port = 47236

function Test-Preview {
    try { Invoke-WebRequest "http://localhost:$port/index.html" -UseBasicParsing -TimeoutSec 3 | Out-Null; $true } catch { $false }
}

Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $temp, $out | Out-Null
$preview = $null
try {
    if (-not (Test-Preview)) {
        $preview = Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList @(
            '-MTA', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$(Join-Path $root 'launch.ps1')`"", '-Preview', '-Port', $port)
        for ($i = 0; $i -lt 30 -and -not (Test-Preview); $i++) { Start-Sleep -Seconds 1 }
        if (-not (Test-Preview)) { throw "The preview didn't start on port $port." }
    }
    node (Join-Path $PSScriptRoot 'screenshots.mjs') $root $out $temp $config
    if ($LASTEXITCODE) { throw 'Taking the screenshots failed (see the error above).' }
    # One picture per version, both screens, in screenshots\Both screens (for flicking through on the phone).
    python (Join-Path $PSScriptRoot "..\..\Dylan's App Tester\tools\both-screens.py") (Split-Path $PSScriptRoot)
    Write-Host "Screenshots for version $Version are in $out"
} finally {
    if ($preview) { Stop-Process -Id $preview.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
    Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
}
