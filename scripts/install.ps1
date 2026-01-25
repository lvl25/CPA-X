$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $ScriptDir "..")

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCmd) {
    python scripts/auto_install.py --no-install-service --start
    exit $LASTEXITCODE
}

$pyCmd = Get-Command py -ErrorAction SilentlyContinue
if ($pyCmd) {
    py -3 scripts/auto_install.py --no-install-service --start
    exit $LASTEXITCODE
}

Write-Error "未找到 Python（python/py）。请先安装 Python 3.11+。"
exit 1
