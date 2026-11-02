$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    & $projectPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Could not install requirements. Check the connection and retry.' }
}
Write-Host 'Student Success: http://127.0.0.1:8000'
Write-Host 'Keep this window open. Press Ctrl+C to stop.'
& $projectPython -m uvicorn api:app --host 127.0.0.1 --port 8000
