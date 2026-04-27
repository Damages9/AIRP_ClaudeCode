# ============================================================
#  DeepSeek API 一键配置 Claude Code 脚本
#  用法：右键此文件 -> "使用 PowerShell 运行"
#  或者：在终端输入  .\setup-deepseek-claude.ps1
# ============================================================

$host.UI.RawUI.WindowTitle = "DeepSeek Claude Code 一键配置"

# 彩色输出函数
function Write-Step($msg) { Write-Host "`n[>] $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "  ✓  $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  !  $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  ✗  $msg" -ForegroundColor Red }
function Write-Banner($msg) {
    $line = "=" * 60
    Write-Host "`n$line" -ForegroundColor Magenta
    Write-Host "  $msg" -ForegroundColor Magenta
    Write-Host "$line" -ForegroundColor Magenta
}

# ============================================================
# Step 1: 欢迎界面
# ============================================================
Clear-Host
Write-Banner "DeepSeek API + Claude Code 一键配置工具"
Write-Host ""
Write-Host "  本脚本将为你自动完成：" -ForegroundColor White
Write-Host "    1. 检查并自动安装 Node.js / Git（缺失时自动下载静默安装）"
Write-Host "    2. 安装/更新 Claude Code"
Write-Host "    3. 配置 DeepSeek API 环境变量（持久化）"
Write-Host "    4. 验证配置是否成功"
Write-Host ""
Write-Host "  温馨提示：只需要准备好你的 DeepSeek API Key 即可" -ForegroundColor DarkGray
Write-Host "  获取地址：https://platform.deepseek.com/api_keys" -ForegroundColor DarkGray
Write-Host ""

# ============================================================
# 辅助函数：刷新当前会话的 PATH（识别新安装的软件）
# ============================================================
function Update-SessionPath {
    foreach ($scope in @("Machine", "User")) {
        $envPath = [Environment]::GetEnvironmentVariable("Path", $scope)
        if ($envPath) {
            foreach ($entry in $envPath -split ";") {
                $trimmed = $entry.Trim()
                if ($trimmed -and (Test-Path $trimmed)) {
                    $existing = [Environment]::GetEnvironmentVariable("Path", "Process") -split ";"
                    if ($trimmed -notin $existing) {
                        [Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "Process") + ";$trimmed", "Process")
                    }
                }
            }
        }
    }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Process")
}

# ============================================================
# 辅助函数：检测 winget 是否可用
# ============================================================
function Test-Winget {
    try {
        $null = Get-Command winget -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

# ============================================================
# 辅助函数：安装 Node.js
# ============================================================
function Install-NodeJS {
    Write-Host "  正在自动安装 Node.js（LTS 版本）..." -ForegroundColor Yellow

    if (Test-Winget) {
        Write-Host "  使用 winget 安装..." -ForegroundColor DarkGray
        winget install OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            # Refresh PATH so node/npm become available
            Update-SessionPath
            try {
                $v = node --version 2>&1
                Write-OK "Node.js 安装成功: $v"
                return $true
            } catch {
                Write-Warn "winget 安装完成但 node 不可用，尝试刷新环境..."
                refreshenv 2>$null
                Update-SessionPath
                try {
                    $v = node --version 2>&1
                    Write-OK "Node.js 安装成功: $v"
                    return $true
                } catch {
                    Write-Warn "当前会话可能无法识别 node，重启终端后生效"
                    Write-Host "  安装程序已运行，请重新运行此脚本" -ForegroundColor Yellow
                    Read-Host "  按回车退出"
                    exit 1
                }
            }
        }
    }

    # winget 不可用，直接下载 MSI
    Write-Warn "winget 不可用，正在通过浏览器下载 Node.js..."
    $url = "https://nodejs.org/dist/v20.19.0/node-v20.19.0-x64.msi"
    $installer = "$env:TEMP\nodejs-installer.msi"

    Write-Host "  下载中: $url" -ForegroundColor DarkGray
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    } catch {
        Write-Err "下载 Node.js 失败: $_"
        Write-Host "  请手动安装 Node.js: https://nodejs.org/zh-cn/download/" -ForegroundColor Yellow
        Read-Host "  按回车退出"
        exit 1
    }

    Write-Host "  正在静默安装 Node.js..." -ForegroundColor DarkGray
    Start-Process msiexec.exe -ArgumentList "/i `"$installer`" /quiet /norestart" -Wait
    Remove-Item $installer -Force -ErrorAction SilentlyContinue
    Update-SessionPath

    try {
        $v = node --version 2>&1
        Write-OK "Node.js 安装成功: $v"
        return $true
    } catch {
        Write-Warn "Node.js 安装完成但当前会话未识别"
        Write-Host "  请重新运行此脚本继续配置" -ForegroundColor Yellow
        Read-Host "  按回车退出"
        exit 1
    }
}

# ============================================================
# 辅助函数：安装 Git
# ============================================================
function Install-Git {
    Write-Host "  正在自动安装 Git for Windows..." -ForegroundColor Yellow

    if (Test-Winget) {
        Write-Host "  使用 winget 安装..." -ForegroundColor DarkGray
        winget install Git.Git --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Update-SessionPath
            try {
                $v = git --version 2>&1
                Write-OK "Git 安装成功: $v"
                return $true
            } catch {
                refreshenv 2>$null
                Update-SessionPath
                try {
                    $v = git --version 2>&1
                    Write-OK "Git 安装成功: $v"
                    return $true
                } catch {
                    Write-Warn "当前会话无法识别 git，重启终端后生效"
                    Write-Host "  安装程序已运行，请重新运行此脚本" -ForegroundColor Yellow
                    Read-Host "  按回车退出"
                    exit 1
                }
            }
        }
    }

    # winget 不可用，直接下载 EXE
    Write-Warn "winget 不可用，正在下载 Git for Windows..."
    $url = "https://github.com/git-for-windows/git/releases/download/v2.49.0.windows.1/Git-2.49.0-64-bit.exe"
    $installer = "$env:TEMP\git-installer.exe"

    Write-Host "  下载中..." -ForegroundColor DarkGray
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing
    } catch {
        Write-Err "下载 Git 失败: $_"
        Write-Host "  请手动安装 Git: https://git-scm.com/download/win" -ForegroundColor Yellow
        Read-Host "  按回车退出"
        exit 1
    }

    Write-Host "  正在静默安装 Git..." -ForegroundColor DarkGray
    Start-Process $installer -ArgumentList "/VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS" -Wait
    Remove-Item $installer -Force -ErrorAction SilentlyContinue
    Update-SessionPath

    try {
        $v = git --version 2>&1
        Write-OK "Git 安装成功: $v"
        return $true
    } catch {
        Write-Warn "Git 安装完成但当前会话未识别"
        Write-Host "  请重新运行此脚本继续配置" -ForegroundColor Yellow
        Read-Host "  按回车退出"
        exit 1
    }
}

# ============================================================
# Step 2: 检查 Node.js 和 Git（缺失则自动安装）
# ============================================================
Write-Step "正在检查运行环境..."

# --- Node.js ---
$nodeInstalled = $false
try {
    $nodeVer = node --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Node.js 已安装: $nodeVer"
        $nodeInstalled = $true
    }
} catch {}

if (-not $nodeInstalled) {
    Write-Warn "未检测到 Node.js"
    Install-NodeJS
}

# --- Git ---
$gitInstalled = $false
try {
    $gitVer = git --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Git 已安装: $gitVer"
        $gitInstalled = $true
    }
} catch {}

if (-not $gitInstalled) {
    Write-Warn "未检测到 Git"
    Install-Git
}

# ============================================================
# Step 3: 检查/安装 Claude Code
# ============================================================
Write-Step "正在检查 Claude Code..."

$needInstall = $false
try {
    $claudeVer = claude --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Claude Code 已安装: $claudeVer"
        Write-Host "  是否需要更新到最新版本？(Y/N)" -ForegroundColor Yellow
        $choice = Read-Host "  (直接回车跳过)"
        if ($choice -eq "Y" -or $choice -eq "y") {
            $needInstall = $true
        }
    } else {
        $needInstall = $true
    }
} catch {
    $needInstall = $true
}

if ($needInstall) {
    Write-Host "  正在安装/更新 Claude Code（全局安装，可能需要几分钟）..." -ForegroundColor Yellow
    $env:CI = "true"
    $env:npm_config_yes = "true"
    npm install -g @anthropic-ai/claude-code 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $claudeVer = claude --version 2>&1
        Write-OK "Claude Code 安装成功: $claudeVer"
    } else {
        Write-Err "Claude Code 安装失败，请检查网络连接后重试"
        Write-Host "  手动安装命令：npm install -g @anthropic-ai/claude-code" -ForegroundColor Yellow
        Write-Host "按任意键退出..." -ForegroundColor Red
        $null = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        exit 1
    }
}

# ============================================================
# Step 4: 获取 API Key
# ============================================================
Write-Step "正在配置 DeepSeek API..."

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════╗" -ForegroundColor DarkCyan
Write-Host "  ║  请输入你的 DeepSeek API Key                ║" -ForegroundColor DarkCyan
Write-Host "  ║  格式：sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx  ║" -ForegroundColor DarkCyan
Write-Host "  ║  获取地址：platform.deepseek.com/api_keys   ║" -ForegroundColor DarkCyan
Write-Host "  ╚══════════════════════════════════════════════╝" -ForegroundColor DarkCyan
Write-Host ""

$apiKey = ""
while ($apiKey.Trim() -eq "") {
    $input = Read-Host "  API Key"
    $apiKey = $input.Trim()
    if ($apiKey -eq "") {
        Write-Warn "API Key 不能为空！"
    }
}

# 简单验证格式
if (-not $apiKey.StartsWith("sk-")) {
    Write-Warn "API Key 看起来格式不太对（应该以 sk- 开头）"
    Write-Host "  你确定要继续吗？(Y/N)" -ForegroundColor Yellow
    $confirm = Read-Host "  "
    if ($confirm -ne "Y" -and $confirm -ne "y") {
        Write-Host "  已取消。按任意键退出..." -ForegroundColor Red
        $null = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        exit 0
    }
}

$apiKeyMasked = $apiKey.Substring(0, [Math]::Min(12, $apiKey.Length)) + "****"

# ============================================================
# Step 5: 设置持久化环境变量（写入 Windows 注册表）
# ============================================================
Write-Step "正在写入持久化环境变量（注册表）..."

$envVars = @{
    "ANTHROPIC_BASE_URL"               = "https://api.deepseek.com/anthropic"
    "ANTHROPIC_AUTH_TOKEN"             = $apiKey
    "ANTHROPIC_MODEL"                  = "deepseek-v4-pro[1m]"
    "ANTHROPIC_DEFAULT_OPUS_MODEL"     = "deepseek-v4-pro[1m]"
    "ANTHROPIC_DEFAULT_SONNET_MODEL"   = "deepseek-v4-pro[1m]"
    "ANTHROPIC_DEFAULT_HAIKU_MODEL"    = "deepseek-v4-flash"
    "CLAUDE_CODE_SUBAGENT_MODEL"       = "deepseek-v4-flash"
    "CLAUDE_CODE_EFFORT_LEVEL"         = "max"
}

$allSet = $true
foreach ($var in $envVars.Keys) {
    try {
        $displayValue = if ($var -eq "ANTHROPIC_AUTH_TOKEN") { $apiKeyMasked } else { $envVars[$var] }
        [Environment]::SetEnvironmentVariable($var, $envVars[$var], "User")
        Write-OK "$var = $displayValue"
    } catch {
        Write-Err "写入 $var 失败: $_"
        $allSet = $false
    }
}

if (-not $allSet) {
    Write-Err "部分环境变量写入失败，请尝试以管理员身份运行此脚本"
    Write-Host "按任意键退出..." -ForegroundColor Red
    $null = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# 同时加载到当前会话
foreach ($var in $envVars.Keys) {
    Set-Item -Path "env:$var" -Value $envVars[$var] -ErrorAction SilentlyContinue
}

# ============================================================
# Step 6: 创建 PowerShell Profile（备用自动加载）
# ============================================================
Write-Step "正在创建 PowerShell Profile（备用加载）..."

try {
    $profileDir = Split-Path $PROFILE -Parent
    if (!(Test-Path $profileDir)) {
        New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
    }

    $profileContent = @"
# ============================================================
#  DeepSeek API Claude Code 配置（自动生成，请勿手动修改）
#  Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
# ============================================================

`$env:ANTHROPIC_BASE_URL            = "https://api.deepseek.com/anthropic"
`$env:ANTHROPIC_AUTH_TOKEN          = "$apiKey"
`$env:ANTHROPIC_MODEL               = "deepseek-v4-pro"
`$env:ANTHROPIC_DEFAULT_OPUS_MODEL  = "deepseek-v4-pro"
`$env:ANTHROPIC_DEFAULT_SONNET_MODEL = "deepseek-v4-pro"
`$env:ANTHROPIC_DEFAULT_HAIKU_MODEL = "deepseek-v4-flash"
`$env:CLAUDE_CODE_SUBAGENT_MODEL    = "deepseek-v4-flash"
`$env:CLAUDE_CODE_EFFORT_LEVEL      = "max"
"@

    Set-Content -Path $PROFILE -Value $profileContent -Encoding UTF8 -Force
    Write-OK "Profile 已创建: $PROFILE"

} catch {
    Write-Warn "Profile 创建失败: $_"
    Write-Host "  这不影响使用，环境变量已通过注册表持久化" -ForegroundColor Yellow
}

# ============================================================
# Step 7: 验证配置
# ============================================================
Write-Step "正在验证配置..."

$errors = @()

# 验证环境变量
$checkVars = @("ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "CLAUDE_CODE_EFFORT_LEVEL")
foreach ($var in $checkVars) {
    $val = [Environment]::GetEnvironmentVariable($var, "User")
    if ($val) {
        Write-OK "$var = $val"
    } else {
        Write-Err "$var 未正确设置"
        $errors += $var
    }
}

# 验证 API Key
$tokenVal = [Environment]::GetEnvironmentVariable("ANTHROPIC_AUTH_TOKEN", "User")
if ($tokenVal) {
    Write-OK "API Key 已配置: $apiKeyMasked"
} else {
    Write-Err "API Key 未正确设置"
    $errors += "ANTHROPIC_AUTH_TOKEN"
}

# 验证 Claude Code 可用
try {
    $claudeVer = claude --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-OK "Claude Code 可用: $claudeVer"
    } else {
        Write-Err "Claude Code 命令异常"
        $errors += "claude"
    }
} catch {
    Write-Err "Claude Code 命令异常: $_"
    $errors += "claude"
}

# ============================================================
# Step 8: 完成
# ============================================================
Write-Host ""
if ($errors.Count -eq 0) {
    Write-Banner "🎉 配置全部成功！"
    Write-Host ""
    Write-Host "  使用方法：" -ForegroundColor White
    Write-Host "    1. 打开一个新的终端窗口" -ForegroundColor White
    Write-Host "    2. 进入你的项目目录： cd D:\你的项目" -ForegroundColor White
    Write-Host "    3. 运行： claude" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  关键信息：" -ForegroundColor DarkGray
    Write-Host "    主模型:     deepseek-v4-pro" -ForegroundColor DarkGray
    Write-Host "    子代理模型: deepseek-v4-flash" -ForegroundColor DarkGray
    Write-Host "    请求难度:   max" -ForegroundColor DarkGray
    Write-Host "    API 地址:   https://api.deepseek.com/anthropic" -ForegroundColor DarkGray
    Write-Host "    API Key:    $apiKeyMasked" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  (╯°□°)╯ 如果出问题，重新运行这个脚本即可修复" -ForegroundColor Magenta
} else {
    Write-Banner "⚠  配置部分失败"
    Write-Host ""
    Write-Host "  以下项目出现问题：$($errors -join ', ')" -ForegroundColor Red
    Write-Host "  请重新运行此脚本，或手动检查" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "按任意键退出..." -ForegroundColor Gray
$null = $host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
