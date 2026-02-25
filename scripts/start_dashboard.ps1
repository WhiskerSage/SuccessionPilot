param(
  [string]$BindHost = "127.0.0.1",
  [int]$Port = 8787,
  [ValidateSet("auto", "fastapi", "legacy")]
  [string]$Engine = "auto"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $ProjectRoot

$VenvPython = ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
  & $VenvPython -m auto_successor.dashboard --host $BindHost --port $Port --engine $Engine
  exit $LASTEXITCODE
}

python -m auto_successor.dashboard --host $BindHost --port $Port --engine $Engine
