param(
  [string]$ConfigPath = "config/config.yaml",
  [switch]$SkipVendorInstall
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $ProjectRoot

function Assert-Command([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Command not found: $Name"
  }
}

Assert-Command "python"
Assert-Command "node"

if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
  python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dashboard]"

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
  Copy-Item ".env.example" ".env"
}

if (-not (Test-Path $ConfigPath) -and (Test-Path "config/config.example.yaml")) {
  Copy-Item "config/config.example.yaml" $ConfigPath
}

$resumePath = "config/resume.txt"
if (-not (Test-Path $resumePath)) {
  New-Item -Path $resumePath -ItemType File -Force | Out-Null
}

$xhsRoot = "vendor/xhs-mcp"
$xhsCli = "vendor/xhs-mcp/dist/xhs-mcp.js"

if ((Test-Path "$xhsRoot/package.json") -and (-not $SkipVendorInstall)) {
  if (-not (Test-Path "$xhsRoot/node_modules/puppeteer")) {
    Push-Location $xhsRoot
    try {
      $env:PUPPETEER_SKIP_DOWNLOAD = "true"
      $env:PUPPETEER_SKIP_CHROMIUM_DOWNLOAD = "true"
      npm install --no-fund --no-audit --cache ".npm-cache"
      if ($LASTEXITCODE -ne 0) {
        throw "npm install failed in $xhsRoot with exit code $LASTEXITCODE"
      }
      if (-not (Test-Path "node_modules/puppeteer")) {
        throw "npm install finished but node_modules/puppeteer is missing in $xhsRoot"
      }
    } finally {
      Remove-Item Env:PUPPETEER_SKIP_DOWNLOAD -ErrorAction SilentlyContinue
      Remove-Item Env:PUPPETEER_SKIP_CHROMIUM_DOWNLOAD -ErrorAction SilentlyContinue
      Pop-Location
    }
  }
}

if (-not (Test-Path $xhsCli)) {
  Write-Warning "Missing $xhsCli. Put xhs-mcp under vendor/xhs-mcp first."
}

$chromeCandidates = @(
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
)
$foundBrowser = $chromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $foundBrowser) {
  Write-Warning "Chrome/Edge not found in common locations. Set xhs.browser_path manually in config."
}

Write-Host ""
Write-Host "Bootstrap done."
Write-Host "Next:"
Write-Host "1) Edit .env"
Write-Host "   (optional) Fill config/resume.txt with your resume text"
Write-Host "2) Login: powershell -ExecutionPolicy Bypass -File scripts/xhs_login.ps1 -Timeout 180"
Write-Host "3) Verify: powershell -ExecutionPolicy Bypass -File scripts/xhs_status.ps1"
Write-Host "4) Run once: .\.venv\Scripts\python.exe -m auto_successor.main --config $ConfigPath --run-once"
Write-Host "5) Daemon: powershell -ExecutionPolicy Bypass -File scripts/start_auto.ps1 -ConfigPath $ConfigPath"
