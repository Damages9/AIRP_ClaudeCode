<div align="center">

# 话本RP — Claude Code 直驱模式

**Claude Code 作为 AI 叙事引擎，直驱角色扮演。**

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-编排引擎-d97706?style=for-the-badge&logo=anthropic&logoColor=white)](https://claude.ai/code)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=for-the-badge)]()

</div>

---

## 🙏 致谢与前言

### 致谢

感谢 **[梁文峰（梁圣）](https://www.deepseek.com)** 开源并大幅降价的 **DeepSeek-V4-Pro**。1M 上下文窗口、相对低廉的价格、稳定且强大的注意力机制——没有这个模型，这个项目不可能跑起来。

感谢社区 **Logan** 提出的原始 idea。我只不过在他的想法之上，试着动手做了一下。

### 关于本项目

**话本RP 不是 SillyTavern 的替代品。** SillyTavern 是一个成熟、全面的角色扮演前端，本项目无意与之竞争。这是一个**甜品级练手项目**，核心思路——**力大砖飞**：直接把模型当 RP 引擎用，靠原始能力硬推叙事。

### 维护声明

作者现实生活繁忙，**不保证按时更新**。但会定时查看 Issue 和 Pull Request，有好思路会不定期更新。欢迎提想法、报 bug、交 PR。

---

## 📖 目录

- [致谢与前言](#-致谢与前言)
- [简介](#-简介)
- [核心特性](#-核心特性)
- [快速开始](#-快速开始)
- [目录结构](#-目录结构)
- [技术栈](#-技术栈)
- [文风配置](#-文风配置)
- [数据流](#-数据流)
- [常见问题](#-常见问题)
- [参考文档](#-参考文档)

---

## 💡 简介

**话本RP** 是一个以 Claude Code 为编排引擎、Python 标准库为后端的角色扮演系统。

你不需要写 prompt — Claude Code 本身就是 RP 引擎。它读取角色卡、管理对话历史、按选定文风生成叙事，并通过 Web 前端与用户互动。

> 将 Claude Code 的代码分析和工具调用能力，转化为 AI 叙事创作的编排层。

---

## ✨ 核心特性

**角色与世界观**
- **PNG 角色卡直读** — 拖入 SillyTavern 角色卡，自动解析嵌入数据
- **世界书全量导入** — 遍历全部条目，原样保留作者设定，按类型路由到 memory/
- **多 JSON 合并** — 搭配多个世界书文件，按条目 ID 去重合并

**叙事控制**
- **文风配置** — Markdown 格式，六维度分析，前端下拉切换，AI 可自学新文风
- **灵活设置** — NSFW 档位 / 人称 / 字数控制 / 防抢话 / 背景 NPC / 夜间模式
- **强制字数门禁** — 生成后统计中文字数，不足 80% 自动重试（最多 3 次）

**智能导演**
- **MVU 变量系统** — JSONPatch 五种操作，日上限 + 阶段门禁，模板宏实时引用
- **卡结构驱动** — 自动检测阶段人设与事件库，按作者意图推进剧情
- **后台 NPC 活性** — 每轮 ≥2 个未出场角色更新，三级决策（静默/提及/进场）
- **世界书双通道** — 变量变更 + 用户输入关键词自动匹配，AI 按需检索

**交互体验**
- **重roll & 回退** — 一键重生成最后回复，或回退任意历史轮次
- **异步交付** — 回复达标后优先送前端，记忆更新后台完成
- **Token 统计** — DeepSeek 真实计数，顶栏实时显示本轮 / 累计
- **用户姓名同步** — 前端填写后全文 `{{user}}` 即时替换
- **夜间模式** — 一键切换暗色主题，偏好持久化

**工程化**
- **三大管线** — 导入 / 回合 / 清理，AI 注意力卸载
- **酒馆兼容层** — 本地 jQuery/lodash/toastr，独立正则引擎，ST API 兼容

### 🧠 跨会话记忆

卡片文件夹下的 `memory/` 目录持久化全部叙事状态，**关闭后明日接着玩**：

| 文件 | 作用 | 更新 |
|------|------|------|
| `memory/project.md` | 剧情进度、伏笔、NPC 状态、下阶段方向 | 每轮 |
| `memory/reference.md` | 世界观规则、角色设定、关键地点 | 导入时 |
| `memory/feedback.md` | 用户偏好（文风/节奏/NSFW 边界） | 偶尔 |
| `memory/user.md` | 用户角色当前状态 | 低频 |
| `memory/story_plan.md` | 长远剧情规划分析 | 每 8 轮 |

### 📖 剧情规划

每 8 轮自动加载 [STORY.md](STORY.md) 叙事理论框架，分析价值转换、布克模式定位、伏笔审计、情感波浪线等维度，写入 `memory/story_plan.md`。框架服务于故事而非约束故事。用户也可随时说「分析下故事走向」手动触发。

---

## 🚀 快速开始

> ⚠️ **重要：请使用 PowerShell 运行本项目，不要使用 cmd（命令提示符）。**
> 
> 本项目大量使用 PowerShell 命令进行进程管理、端口清理等操作。cmd 无法执行这些命令，会导致启动失败或端口占用。在文件夹地址栏输入 `powershell` 回车即可打开 PowerShell。

### 5 分钟从零开始

如果你是第一次用，按顺序走这 5 步：

**① 准备 3 样东西**

| 你需要 | 怎么获取 |
|--------|---------|
| **Python 3.x** | [python.org](https://www.python.org/) 下载安装（安装时勾选"Add Python to PATH"） |
| **DeepSeek API Key** | [platform.deepseek.com](https://platform.deepseek.com/) 注册，在 API Keys 页面创建 |
| **一张角色卡** | `.png` 格式的 SillyTavern 角色卡（可以从社区下载，也可以自己用酒馆导出） |

**② 跑配置脚本（就这一次）**

双击项目根目录的 `setup-deepseek-claude.bat`，按提示输入你的 DeepSeek API Key。脚本会自动安装 Claude Code、写入环境变量。

**③ 放卡片**

在项目根目录新建一个文件夹（随便起名，比如 `我的角色`），把角色卡 PNG 拖进去。

```
话本RP/
├── 我的角色/          ← 新建这个文件夹
│   └── 角色卡.png     ← 把卡片放进来
├── skills/            ← 这些不用管
└── CLAUDE.md
```

**④ 启动**

在 `我的角色` 文件夹内打开 **PowerShell** 终端（地址栏输入 `powershell` 回车），输入 `claude` 启动后，在对话中输入：

```
/rp
```

Claude Code 会自动完成：清理残留进程 → 启动服务器 → 解析角色卡/世界书 → 写入记忆 → 生成开场叙事。老卡会自动读取之前的聊天记录和记忆接着剧情继续。

**⑤ 打开浏览器**

访问 **http://localhost:8765**，在输入框打字，点提交。AI 会在几秒到几十秒内生成回复。

**之后怎么继续玩？** 关闭 Claude Code 后，下次在同一个文件夹重新 `claude`，输入 `/rp` 即可——系统会自动读取之前的聊天记录和记忆，接着剧情继续。换卡片就新建一个文件夹，重复步骤 ③-④。

---

### 环境配置（一键脚本）

项目根目录提供了两个配置脚本，自动完成 Node.js / Git 检查、Claude Code 安装、DeepSeek API 环境变量写入（注册表持久化）、PowerShell Profile 备份：

| 文件 | 说明 |
|------|------|
| `setup-deepseek-claude.bat` | 双击运行，自动提权启动 PowerShell 执行配置 |
| `setup-deepseek-claude.ps1` | 核心脚本，右键「使用 PowerShell 运行」也可直接启动 |

运行后按提示输入 DeepSeek API Key 即可。

<details>
<summary>📋 脚本写入的环境变量（仅供参考）</summary>

```
ANTHROPIC_BASE_URL            = https://api.deepseek.com/anthropic
ANTHROPIC_MODEL               = deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_OPUS_MODEL  = deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_SONNET_MODEL= deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_HAIKU_MODEL = deepseek-v4-flash
CLAUDE_CODE_SUBAGENT_MODEL    = deepseek-v4-flash
CLAUDE_CODE_EFFORT_LEVEL      = max
```

</details>

### 运行模式：一卡一文件夹

本项目的运行方式是：**在项目根目录下为每张角色卡（或每部小说）单独建立一个文件夹**，放入素材后，在该文件夹内启动 Claude Code。

```
{ROOT}/
├── skills/                     # 引擎代码（所有卡片共享）
├── CLAUDE.md                   # 引擎规则（所有卡片共享）
├── 我的角色/                   # 卡片文件夹（一个文件夹 = 一张卡）
│   ├── 角色卡.png              #   角色卡 PNG（可搭配世界书 .json / 小说 .txt）
│   ├── chat_log.json           #   聊天记录（自动生成）
│   └── memory/                 #   跨会话记忆（自动管理）
```

Claude Code 启动时会自动扫描**当前文件夹**下的素材：
- `.png` → 解析 SillyTavern 角色卡（tEXt/chara chunk）
- `.json` → 读取世界书
- `.txt` → 视为小说文本，提取世界观和角色

### 使用场景

除 `/rp` 一键启动外，也可用自然语言精确控制：

#### 🎭 角色卡 RP
> 「读取这张角色卡，开始 RP」

#### 🖊️ 小说炼化文风
> 「完整阅读 `小说.txt`，总结其文风，命名为 `XX风格`」

AI 自动分析遣词/句式/段落/节奏等六个维度，写入 `skills/styles/profiles/`。刷新前端即可选择。

#### 📖 进入小说世界 RP
> 「读取 `小说.txt`，我要扮演 __（主角/配角/自定义角色）__，时间点是 __。以该时间点写开场。」

自定义角色需写出身份、外貌、性格、背景等设定。

### 关闭

直接退出 Claude Code（`/quit` 或关闭终端窗口），系统会自动释放端口。无需手动 `taskkill`。

<details>
<summary>🔧 手动启动桥接服务器（通常不需要，start_server.py 已自动处理）</summary>

```powershell
python skills/start_server.py .
```

服务默认监听 `127.0.0.1:8765`，MVU 服务监听 `127.0.0.1:8766`。

</details>

---

## 📂 目录结构

```
{ROOT}/
├── setup-deepseek-claude.bat     # ⚙️ 环境一键配置（双击运行）
├── setup-deepseek-claude.ps1     # ⚙️ 环境配置核心脚本
├── CLAUDE.md                     # 🧠 系统编排核心（规则/权限/流程）
├── README.md                     # 📄 本文件
├── extract-png-card.md           # 📘 PNG chunk 角色卡解析参考
├── live-status.md                # 📙 实时状态面板参考
├── STORY.md                       # 📖 叙事理论框架（剧情规划技能）
├── .gitignore
├── .claude/                      # Claude Code 配置（纳入版本控制）
│   ├── settings.local.json       # 本地权限白名单
│   └── skills/rp.md              # /rp 自定义启动命令
└── skills/                       # 后端与前端
    ├── server.py                 # 🌐 HTTP 桥接服务器（端口 8765）
    ├── handler.py                # 🔧 回合管理（解析/追加/重建/回退/MVU变量/MVU变量校验）
    ├── import_card.py            # 📥 卡片素材解析（PNG/JSON/TXT → memory/）
    ├── import_prepare.py         # 📋 导入管线（清理→解析→会话初始化→上下文汇总）
    ├── start_server.py           # 🚀 服务器启动器（自动检查+清理+轮询就绪）
    ├── mvu_engine.py             # ⚙️ MVU 变量引擎（JSONPatch 解析/执行）
    ├── mvu_check.py              # ✅ MVU 变量交叉检查
    ├── mvu_server.js             # 🔗 MVU 变量服务（Zod schema 校验）
    ├── match_worldbook.py        # 🔍 世界书关键词匹配
    ├── write_memory.py           # 📝 剧情记忆更新
    ├── round_prepare.py          # 📥 回合预处理管线（收集上下文→写入 round_context.txt）
    ├── round_deliver.py          # 📤 回合后处理管线（质检→交付→记忆→剧情规划触发）
    └── styles/                   # 前端与运行时
        ├── index.html            # 🖥️ 主前端界面（SPA）
        ├── _st_shims.js          # 🔗 SillyTavern API 兼容层
        ├── _regex_engine.js      # 🧩 酒馆兼容正则引擎
        ├── content.html          # 📝 叙事内容模板
        ├── status.html           # 📊 实时状态面板
        ├── settings.json         # ⚙️ 当前设置
        ├── openings.json         # 🎬 开场白数据
        ├── lib/                  # 📦 本地 JS 库（jQuery/lodash/toastr）
        └── profiles/             # 🖊️ 文风配置
            ├── 北棱特调.md       #   文学化/陌生化遣词
            └── 轻松活泼.md       #   简洁明快/口语化
```

> 运行时自动生成的文件（`content.js`、`state.js`、`input.txt`、`.card_path`、`round_context.txt`、`import_context.txt`、`.pending` 等）已加入 `.gitignore`。

---

## 🛠️ 技术栈

<div align="center">

| 层 | 技术 | 说明 |
|:---:|------|------|
| 🧠 **AI 编排** | Claude Code | 读取 CLAUDE.md 规则，调用工具链执行 |
| 🌐 **后端** | Python `http.server` | 标准库，零外部依赖 |
| 🖥️ **前端** | 原生 HTML/CSS/JS | 无框架，动态 `<script>` 注入实现无闪烁更新 |
| 📦 **数据** | JSON + Markdown + JS | 聊天记录/设置用 JSON，文风用 MD，状态用 JS |
| 🃏 **角色卡** | SillyTavern PNG | `tEXt/chara` chunk → base64 → JSON |

</div>

---

## 🖊️ 文风配置

文风文件是 Markdown 格式，存放在 `skills/styles/profiles/`，包含六个标准维度：

| 维度 | 说明 |
|------|------|
| **核心特征** | 调性定位、句式倾向 |
| **句子模式** | 常用句型结构、修辞手法 |
| **词汇偏好** | 偏好用词范围、避免使用的词汇 |
| **禁用规则** | 禁止出现的表达模式 |
| **段落结构** | 段落密度、过渡方式、信息密度 |
| **节奏控制** | 叙事张弛模式、场景切换速度 |

### 📌 内置预设

| 风格 | 调性 | 适合场景 |
|------|------|----------|
| **北棱特调** | 文学化、陌生化遣词、丰富修辞 | 文学性强、氛围浓厚的叙事 |
| **轻松活泼** | 口语化、短句为主、节奏明快 | 日常、轻松、对话为主的场景 |

### 🆕 创建新文风

在对话中粘贴小说文本，或将txt文件放入项目目录中后在后台提交给ClaudeCode（或提供作者名让 AI 联网搜索），然后说：

> 「分析这段文风，命名为 XX 风格」

AI 会自动分析六个维度并写入 `profiles/`。刷新前端即可在下拉框中选择新风格。

---

## 🔄 数据流

```mermaid
graph LR
    A[浏览器输入] -->|POST 提交| B[server.py]
    B -->|写入 input.txt| C[.pending 标记]
    C -->|长轮询 wait_pending| D[Claude Code]
    D -->|round_prepare.py 收集上下文| D2[世界书索引+匹配+注入]
    D2 -->|写入 round_context.txt| D3[MVU 变量清单+路径树]
    D3 -->|AI 读上下文+生成叙事| E[生成叙事+MVU 命令]
    E -->|写入 response.txt| F[round_deliver.py 质检]
    F -->|达标| G[handler.py 交付前端]
    G -->|重建 content.js| H[前端即时刷新]
    G -->|异步后台| I[更新 memory]
    I -->|每8轮| J[剧情规划分析]
    F -->|不足80% 重试| E
```

### 说人话版：你打一个字，背后发生了什么？

```
你在浏览器输入 "你好" → 点提交
            ↓
server.py 收到，写标记文件
            ↓
Claude Code 通过长轮询立即感知，开始干活：
  ✦ round_prepare.py 收集全部上下文（输入/记忆/世界书匹配/变量路径）
  ✦ AI 读取汇总上下文，走五步思考流程
  ✦ 按你选的文风写叙事回复 + 更新变量
  ✦ round_deliver.py 质检字数→交付前端→更新记忆
            ↓
你看到 AI 的回复出现在浏览器里 ✨
```

整个过程快则几秒，慢则几十秒（取决于回复长度和复杂度）。

---

## 🆘 常见问题

### 浏览器打不开 http://localhost:8765？

1. 确认 Claude Code 正在运行（终端窗口没关）
2. 检查是否用的 `http://` 而不是 `https://`
3. 如果端口被占用：重启 Claude Code 即可——`import_prepare.py` 和 `start_server.py` 会自动清理残留进程并重新绑定端口

### 回复一直没出现？

1. 确认你真的点了"提交"按钮（输入框下面那个）
2. 等待 30-60 秒——AI 生成需要时间，尤其是长回复
3. 如果超过 2 分钟还没反应，在 Claude Code 终端看看有没有报错

### 我没有角色卡，能试用吗？

可以。随便放一张 PNG 图片（甚至一张截图）到新建文件夹里，系统会尝试解析。或者放一个 `.txt` 小说文件，AI 会从小说提取世界观和角色。没有卡也能玩——但效果不如正经角色卡好。

### 怎么换一张卡片玩？

关闭当前 Claude Code 会话（`Ctrl+C` 或直接关终端）。新建一个文件夹，放入新卡片，`cd` 进去重新 `claude`。每张卡的数据完全隔离，互不影响。

> 注意：不要同时开着多个 Claude Code 实例——它们会抢同一个 8765 端口。

### 怎么备份我的进度？

你卡片文件夹里的 `chat_log.json`（完整聊天记录）和 `memory/` 目录（剧情记忆）就是全部进度。复制整个卡片文件夹到别处即可备份。想恢复时复制回来。

### 回复质量不好怎么办？

- 换一个文风：前端顶栏下拉框切换，立即生效
- 调整 NSFW 档位：设置面板里改
- 字数太少/太多：设置面板调整 `wordCount`
- 重roll 当前回复：前端点 🔄 按钮

### Python 报错 "No module named xxx"？

本项目只用了 Python 标准库，不应该出现这个错误。如果出现了，说明你可能在错误的工作目录。确认终端当前在项目根目录（能看到 `skills/` 文件夹）。

---

## 📚 参考文档

| 文件 | 内容 |
|------|------|
| [`CLAUDE.md`](CLAUDE.md) | 系统编排规则、权限预授权、硬性门禁、文风分析指令 |
| [`STORY.md`](STORY.md) | 叙事理论框架——布克/麦基/坎贝尔/救猫咪/皮尔逊蒸馏 |
| [`extract-png-card.md`](extract-png-card.md) | SillyTavern PNG 角色卡 chunk 解析方法 |
| [`live-status.md`](live-status.md) | 实时状态面板的 HTML/JS 设计说明 |

---

## 📖 术语表

| 术语 | 全称 | 一句话解释 |
|------|------|-----------|
| **RP** | Role-Playing | 角色扮演——你扮演一个角色，AI 扮演其他角色和世界 |
| **NSFW** | Not Safe For Work | 成人内容。本项目支持三个档位：舒缓 / 直白 / 关闭 |
| **NPC** | Non-Player Character | 非玩家角色——AI 控制的配角、路人、反派 |
| **MVU** | MagVarUpdate | 酒馆的变量更新系统，用 JSONPatch 格式管理角色数值变化 |
| **JSONPatch** | — | 一种描述 JSON 数据修改的标准格式（replace/add/remove 等操作） |
| **PNG chunk** | — | PNG 图片里隐藏的数据块。SillyTavern 角色卡把角色设定藏在 `tEXt/chara` 块里 |
| **memory/** | — | 卡片文件夹下的记忆目录。存剧情进度、世界观、用户偏好，关了明天还能接着玩 |
| **重roll** | Re-roll | 删除 AI 最后一轮回复，用同样的用户输入重新生成一次 |

---

<div align="center">

**⚡ 将 Claude Code 的分析能力，转化为 AI 叙事的创作力 ⚡**

</div>
