param(
    [string]$Image = "archery-mcp:local",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

docker build --tag $Image .
if ($LASTEXITCODE -ne 0) { throw "Docker 镜像构建失败" }

& $Python scripts/smoke_test_docker.py $Image
if ($LASTEXITCODE -ne 0) { throw "Docker MCP 冒烟测试失败" }

Write-Host "构建完成：$Image"
