# 话本RP — 一键更新脚本
# 双击运行或右键 "使用 PowerShell 运行"
# 自动处理本地修改，安全拉取最新代码

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  话本RP — 项目更新" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 确保在项目根目录
Set-Location $PSScriptRoot

# 检查是否为 git 仓库
if (-not (Test-Path ".git")) {
    Write-Host "[错误] 当前目录不是 git 仓库，无法更新。" -ForegroundColor Red
    Write-Host "按任意键退出..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# 一次性配置 autostash（之后 git pull 会自动 stash/pop）
Write-Host "[配置] 启用自动暂存 (autostash)..." -ForegroundColor Gray
git config pull.rebase true
git config rebase.autoStash true

Write-Host "[检查] 当前分支: " -NoNewline
$branch = git rev-parse --abbrev-ref HEAD
Write-Host $branch -ForegroundColor Yellow

# 检查本地是否有未提交的修改
$hasChanges = $false
$statusOutput = git status --porcelain 2>&1
if ($statusOutput) {
    $hasChanges = $true
    Write-Host "[信息] 检测到本地修改:" -ForegroundColor Gray
    $statusOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
} else {
    Write-Host "[信息] 工作区干净，无本地修改。" -ForegroundColor Gray
}

Write-Host ""
Write-Host "[更新] 正在拉取最新代码..." -ForegroundColor Green

# 执行 git pull
$pullOutput = git pull 2>&1
$pullExitCode = $LASTEXITCODE

if ($pullExitCode -eq 0) {
    Write-Host $pullOutput -ForegroundColor Green
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  更新完成！" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
} else {
    Write-Host $pullOutput -ForegroundColor Red
    Write-Host ""
    Write-Host "[警告] 拉取时出现问题。" -ForegroundColor Yellow
    Write-Host ""

    # 常见问题诊断
    if ($pullOutput -match "Please commit your changes or stash them") {
        Write-Host "→ 仍有文件冲突，正在尝试手动暂存..." -ForegroundColor Yellow
        git stash push -m "update.ps1 auto-stash before pull" 2>&1 | Out-Null
        $stashResult = git pull 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "→ 拉取成功，恢复本地修改..." -ForegroundColor Green
            git stash pop 2>&1 | Out-Null
            Write-Host "  更新完成！" -ForegroundColor Green
        } else {
            Write-Host "→ 拉取失败。请检查网络连接或手动处理。" -ForegroundColor Red
            Write-Host "  你的修改已暂存在 stash 中，可用 'git stash list' 查看。" -ForegroundColor Yellow
        }
    } elseif ($pullOutput -match "CONFLICT") {
        Write-Host "→ 出现合并冲突。你的修改已暂存，请手动解决冲突后提交。" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "按任意键退出..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
