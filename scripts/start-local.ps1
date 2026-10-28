<# Start installed services with readiness checks; retain existing healthy services. #>
param([int]$Port=3000,[int]$BackendPort=8000,[string]$PythonPath='')
$ErrorActionPreference='Stop'
$projectDir=Split-Path -Parent $PSScriptRoot
if (-not $PythonPath) { $PythonPath=Join-Path $projectDir '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Python environment missing; install requirements or supply -PythonPath.' }
$nodePath=(Get-Command node -ErrorAction Stop).Source
if (-not (Test-Path -LiteralPath (Join-Path $projectDir 'frontend\.next\BUILD_ID'))) { throw 'Build frontend before starting: npm run build.' }
$logDir=Join-Path $projectDir 'data\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
function Test-Ready([string]$Url) {
    try { return (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { return $false }
}
function Wait-Ready([string]$Url,[System.Diagnostics.Process]$Process) {
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        if (Test-Ready $Url) { return }
        if ($Process.HasExited) { throw "Service exited; inspect logs in $logDir" }
        Start-Sleep -Milliseconds 500
    }
    throw "Service did not become ready; inspect logs in $logDir"
}
$asrPackages=Join-Path $projectDir '.asr-packages'
$oldPythonPath=$env:PYTHONPATH
try {
    if (Test-Path -LiteralPath $asrPackages) { $env:PYTHONPATH=$asrPackages+[IO.Path]::PathSeparator+$env:PYTHONPATH }
    if (-not (Test-Ready "http://127.0.0.1:$BackendPort/api/health")) {
        $apiProcess=Start-Process -FilePath $PythonPath -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$BackendPort") -WorkingDirectory (Join-Path $projectDir 'backend') -RedirectStandardOutput (Join-Path $logDir 'backend.log') -RedirectStandardError (Join-Path $logDir 'backend-error.log') -WindowStyle Hidden -PassThru
        Wait-Ready "http://127.0.0.1:$BackendPort/api/health" $apiProcess
    }
    if (-not (Test-Ready "http://127.0.0.1:$Port")) {
        $webProcess=Start-Process -FilePath $nodePath -ArgumentList @('node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',"$Port") -WorkingDirectory (Join-Path $projectDir 'frontend') -RedirectStandardOutput (Join-Path $logDir 'frontend.log') -RedirectStandardError (Join-Path $logDir 'frontend-error.log') -WindowStyle Hidden -PassThru
        Wait-Ready "http://127.0.0.1:$Port" $webProcess
    }
    if (-not (Test-Ready "http://127.0.0.1:$Port/api/health")) { throw 'Frontend API proxy failed. Rebuild with API_URL matching BackendPort.' }
    Write-Output "Ready: http://127.0.0.1:$Port"
} finally { $env:PYTHONPATH=$oldPythonPath }
