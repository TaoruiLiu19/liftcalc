# liftcalc 启动器：设置 PYTHONPATH 与虚拟环境后转交参数
param([Parameter(ValueFromRemainingArguments = $true)] $Rest)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Error "未找到虚拟环境：$py（先运行 python -m venv .venv --system-site-packages）"
    exit 5
}

$env:PYTHONPATH = Join-Path $root "src"
& $py -m liftcalc.cli.main @Rest
exit $LASTEXITCODE
