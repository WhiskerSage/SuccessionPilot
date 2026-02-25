param(
  [int]$Timeout = 180,
  [string]$BrowserPath = ""
)

$ErrorActionPreference = "Stop"

try {
  [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
  $OutputEncoding = [Console]::OutputEncoding
  chcp 65001 > $null
} catch {}

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $ProjectRoot

$CliPath = "vendor/xhs-mcp/dist/xhs-mcp.js"
if (-not (Test-Path $CliPath)) {
  throw "Missing $CliPath"
}

if (-not $BrowserPath) {
  $BrowserPath = ("" + $env:CHROME_PATH).Trim()
}
if (-not $BrowserPath) {
  $candidates = @(
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
  )
  $BrowserPath = ($candidates | Where-Object { Test-Path $_ } | Select-Object -First 1)
}

if ($BrowserPath) {
  $env:PUPPETEER_EXECUTABLE_PATH = $BrowserPath
  $env:PUPPETEER_SKIP_DOWNLOAD = "true"
} else {
  Write-Warning "No local Chrome/Edge found. xhs-mcp may require Chromium install."
}

try {
  node $CliPath login --timeout $Timeout
  exit $LASTEXITCODE
} finally {
  Remove-Item Env:PUPPETEER_EXECUTABLE_PATH -ErrorAction SilentlyContinue
  Remove-Item Env:PUPPETEER_SKIP_DOWNLOAD -ErrorAction SilentlyContinue
}
