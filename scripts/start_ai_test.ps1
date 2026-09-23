# Start only the isolated AI preview. The normal 8070 service is not touched.
$ErrorActionPreference = 'Stop'
$aiRepoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$aiPythonPath = 'C:\Program Files\Odoo 19.0e.20260805\python\python.exe'
$aiDockerPath = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
& $aiDockerPath start partner-hub-ai-test-20260918
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop first, then retry.' }
$aiSupervisorPath = Join-Path $PSScriptRoot 'supervise_ai_test.py'
$aiPreviewProcess = Start-Process -FilePath $aiPythonPath -ArgumentList ('"' + $aiSupervisorPath + '"') -WorkingDirectory $aiRepoPath -WindowStyle Hidden -PassThru
Write-Output ('8072 supervisor requested; PID ' + $aiPreviewProcess.Id + '. Duplicate launches safely exit. Logs: output/ai-supervisor.log')
