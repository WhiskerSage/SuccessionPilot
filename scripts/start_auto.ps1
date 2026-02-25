param(
  [string]$ConfigPath = "config/config.yaml"
)

$ErrorActionPreference = "Stop"

try {
  [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
  [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
  $OutputEncoding = [Console]::OutputEncoding
  chcp 65001 > $null
} catch {}

$env:PYTHONIOENCODING = "utf-8"

if (-not (Test-Path $ConfigPath) -and (Test-Path "config/config.example.yaml")) {
  Copy-Item "config/config.example.yaml" $ConfigPath
}

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
  Copy-Item ".env.example" ".env"
}

if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
  python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
pip install -e .
succession-pilot --config $ConfigPath --daemon
