# Start only the isolated AI preview. The normal 8070 service is not touched.
$ErrorActionPreference = 'Stop'
$aiRepoPath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$aiServerPath = 'C:\Program Files\Odoo 19.0e.20260805\server'
$aiPythonPath = 'C:\Program Files\Odoo 19.0e.20260805\python\python.exe'
if (Get-NetTCPConnection -LocalPort 8072 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 8072 is already in use; inspect it before starting another server.'
}
$aiArguments = @(
    ('"' + $aiServerPath + '\odoo-bin"'),
    '-c', ('"' + $aiServerPath + '\odoo.conf"'),
    ('--addons-path="' + $aiServerPath + '\odoo\addons,' + $aiRepoPath + '\custom_addons"'),
    '--db_host=127.0.0.1', '--db_port=15432', '--db_user=ai_test', '--db_password=ai_local_isolated_test',
    '-d', 'b2b_ai_test_20260918', '--db-filter=^b2b_ai_test_20260918$',
    ('--data-dir="' + $aiRepoPath + '\output\ai-data"'),
    '--http-port=8072', '--http-interface=127.0.0.1', '--max-cron-threads=1',
    ('--logfile="' + $aiRepoPath + '\output\ai-preview.log"')
)
$aiPreviewProcess = Start-Process -FilePath $aiPythonPath -ArgumentList $aiArguments -WorkingDirectory $aiRepoPath -WindowStyle Hidden -PassThru
Write-Output ('Isolated AI preview started on http://localhost:8072/ai-assistant; PID ' + $aiPreviewProcess.Id)
