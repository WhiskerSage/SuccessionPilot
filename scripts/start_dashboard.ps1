param(
  [string]$BindHost = "127.0.0.1",
  [int]$Port = 8787
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $ProjectRoot

$VenvPython = ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
  & $VenvPython -m auto_successor.dashboard --host $BindHost --port $Port
  exit $LASTEXITCODE
}

python -m auto_successor.dashboard --host $BindHost --port $Port
