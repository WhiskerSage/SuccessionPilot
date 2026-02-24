param(
  [int]$Timeout = 180
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $ProjectRoot

$CliPath = "vendor/xhs-mcp/dist/xhs-mcp.js"
if (-not (Test-Path $CliPath)) {
  throw "Missing $CliPath"
}

node $CliPath login --timeout $Timeout
