param(
  [string]$BrowserPath = "",
  [string]$Account = "default",
  [string]$AccountCookiesDir = "~/.xhs-mcp/accounts"
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

$ActiveCookiesFile = Join-Path $HOME ".xhs-mcp/cookies.json"
$AccountName = ("" + $Account).Trim()
if (-not $AccountName) {
  $AccountName = "default"
}

function Resolve-SelectedCookiesFile {
  param(
    [string]$Name,
    [string]$Dir,
    [string]$ActivePath
  )
  if ($Name -eq "default") {
    return $ActivePath
  }
  $expanded = [Environment]::ExpandEnvironmentVariables($Dir)
  if ($expanded.StartsWith("~")) {
    $expanded = Join-Path $HOME $expanded.Substring(1).TrimStart("/","\\")
  }
  if ($Name.ToLower().EndsWith(".json")) {
    return Join-Path $expanded $Name
  }
  return Join-Path $expanded ($Name + ".json")
}

$SelectedCookiesFile = Resolve-SelectedCookiesFile -Name $AccountName -Dir $AccountCookiesDir -ActivePath $ActiveCookiesFile
if ($AccountName -ne "default") {
  try {
    if (Test-Path $SelectedCookiesFile) {
      New-Item -ItemType Directory -Force -Path (Split-Path $ActiveCookiesFile -Parent) | Out-Null
      Copy-Item -Path $SelectedCookiesFile -Destination $ActiveCookiesFile -Force
    }
  } catch {
    Write-Warning "sync selected cookies to active failed: $($_.Exception.Message)"
  }
}

try {
  node $CliPath status --compact
  exit $LASTEXITCODE
} finally {
  Remove-Item Env:PUPPETEER_EXECUTABLE_PATH -ErrorAction SilentlyContinue
  Remove-Item Env:PUPPETEER_SKIP_DOWNLOAD -ErrorAction SilentlyContinue
}
