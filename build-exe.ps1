param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

& $Python -m pip install -e ".[test,exe]"
if ($LASTEXITCODE -ne 0) { throw "依赖安装失败" }

& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "单元测试失败" }

& $Python -m PyInstaller --clean --noconfirm archery-mcp.spec
if ($LASTEXITCODE -ne 0) { throw "EXE 构建失败" }

& $Python scripts/smoke_test_exe.py dist/archery-mcp.exe
if ($LASTEXITCODE -ne 0) { throw "EXE MCP 冒烟测试失败" }

Write-Host "构建完成：$ProjectRoot\dist\archery-mcp.exe"
