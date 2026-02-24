param(
  [string]$Host = "127.0.0.1",
  [int]$Port = 8787
)

$ErrorActionPreference = "Stop"
python -m auto_successor.dashboard --host $Host --port $Port
