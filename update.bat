@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   话本RP — 项目更新
echo ========================================
echo.

:: Ensure we're in the script directory
cd /d "%~dp0"

:: Check if git repo
if not exist ".git" (
    echo [错误] 当前目录不是 git 仓库，无法更新。
    pause
    exit /b 1
)

:: Configure autostash (one-time setup)
echo [配置] 启用自动暂存 (autostash)...
git config pull.rebase true
git config rebase.autoStash true

echo [检查] 当前分支:
git rev-parse --abbrev-ref HEAD
echo.

:: Check for local changes
set HAS_CHANGES=0
git status --porcelain | findstr /r "." >nul 2>&1
if %errorlevel% equ 0 set HAS_CHANGES=1

if %HAS_CHANGES% equ 1 (
    echo [信息] 检测到本地修改:
    git status --porcelain
) else (
    echo [信息] 工作区干净，无本地修改。
)

echo.
echo [更新] 正在拉取最新代码...

:: Try git pull with autostash
git pull 2>&1
set PULL_RESULT=%errorlevel%

if %PULL_RESULT% equ 0 (
    echo.
    echo ========================================
    echo   更新完成！
    echo ========================================
) else (
    echo.
    echo [警告] autostash 方式失败，尝试手动暂存...
    git stash push -m "update.bat auto-stash before pull" >nul 2>&1
    git pull 2>&1
    if !errorlevel! equ 0 (
        echo [信息] 拉取成功，恢复本地修改...
        git stash pop >nul 2>&1
        if !errorlevel! equ 0 (
            echo   更新完成！
        ) else (
            echo [警告] 恢复本地修改时出现冲突，请手动处理。
            echo   你的修改在 stash 中，用 'git stash list' 查看。
        )
    ) else (
        echo [错误] 拉取失败，请检查网络连接。
        echo   你的修改在 stash 中，用 'git stash list' 查看。
    )
)

echo.
pause
