param(
  [string]$ConfigPath = "config/config.yaml"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
  python -m venv .venv
}

. .\.venv\Scripts\Activate.ps1
pip install -e .
succession-pilot --config $ConfigPath --daemon
