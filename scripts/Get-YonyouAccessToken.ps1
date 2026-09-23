[CmdletBinding()]
param(
    [switch]$ForceRefresh,
    [switch]$PrintToken,
    [switch]$JsonToken,
    [switch]$Configure,
    [switch]$CredentialsStdin,
    [switch]$Status,
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
if (-not $PythonPath) {
    $bundledPython = 'C:\Program Files\Odoo 19.0e.20260805\python\python.exe'
    if (Test-Path -LiteralPath $bundledPython) {
        $PythonPath = $bundledPython
    } else {
        $PythonPath = (Get-Command python.exe -ErrorAction Stop).Source
    }
}
$tokenArguments = @((Join-Path $PSScriptRoot 'yonyou_token.py'))
if ($ForceRefresh) { $tokenArguments += '--force-refresh' }
if ($PrintToken) { $tokenArguments += '--print-token' }
if ($JsonToken) { $tokenArguments += '--json-token' }
if ($Configure) { $tokenArguments += '--configure' }
if ($CredentialsStdin) { $tokenArguments += '--credentials-stdin' }
if ($Status) { $tokenArguments += '--status' }
& $PythonPath @tokenArguments
if ($LASTEXITCODE -ne 0) {
    throw 'Yonyou authentication failed. See the credential-free error above.'
}
