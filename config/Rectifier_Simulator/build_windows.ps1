param(
    [ValidateSet("Debug", "Release")]
    [string]$Mode = "Debug"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    throw ".venv가 없습니다. 먼저 python -m venv .venv 를 실행하세요."
}

$python = ".\.venv\Scripts\python.exe"
$name = if ($Mode -eq "Debug") {
    "RectifierSimulatorDebug"
} else {
    "RectifierSimulator"
}
$windowOption = if ($Mode -eq "Debug") {
    "--console"
} else {
    "--windowed"
}

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    $windowOption `
    --name $name `
    --add-data "config;config" `
    --add-data "models;models" `
    --collect-all pymodbus `
    --collect-all sklearn `
    main.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 빌드에 실패했습니다."
}

Write-Host "빌드 완료: dist\$name\$name.exe"
