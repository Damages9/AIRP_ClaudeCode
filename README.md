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

**话本RP 不是 SillyTavern 的替代品。**

SillyTavern 是一个成熟、全面、久经考验的角色扮演前端，本项目无意也无力与之竞争。这是一个**甜品级练手项目**，核心思路只有一个——**力大砖飞**：

> 直接甩给 DeepSeek-V4-Pro + Claude Code，让模型自己看着办。

不用精细的 prompt engineering、不用复杂的 pipeline、不用层层过滤——就把 Claude Code 当成 RP 引擎本身，靠模型的原始能力硬推叙事。

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
- [参考文档](#-参考文档)

---

## 💡 简介

**话本RP** 是一个以 Claude Code 为编排引擎、Python 标准库为后端的角色扮演系统。

你不需要写 prompt — Claude Code 本身就是 RP 引擎。它读取角色卡、管理对话历史、按选定文风生成叙事，并通过 Web 前端与用户互动。

> 将 Claude Code 的代码分析和工具调用能力，转化为 AI 叙事创作的编排层。

---

## ✨ 核心特性

<table>
<tr>
<td width="50%">

### 🎭 角色卡直读
拖入 SillyTavern PNG 角色卡，自动解析 `tEXt/chara` chunk → 提取角色设定、开场白、世界观。

### 📖 世界书全量导入
自动遍历角色卡内嵌 `character_book` 的**全部条目**，按类型路由到对应 memory 文件（user.md / reference.md），**原样完整保留作者设定，禁止摘要压缩**。蓝绿灯条目统一写入永久记忆——保持 prompt cache 结构稳定，避免动态注入导致的缓存未命中。

### 🖊️ 文风配置系统
Markdown 格式风格文件，前端下拉框动态切换。内置 **2 套预设风格**，支持通过对话分析小说/作者文风自动生成新配置。

### ⚙️ 灵活设置面板
NSFW 档位（舒缓/直白/关闭） · 人称切换 · 字数控制（100–6000） · 防抢话开关 · 背景 NPC 开关 · **夜间模式切换**

</td>
<td width="50%">

### 🔄 重roll 与回退
一键重roll 最后一轮 AI 回复，或回退到任意历史轮次重新输入。

### 🎬 开场白自动导入
切换卡片时自动从角色卡 `first_mes` 提取开场白正文和行动选项，写入 `openings.json`。不再残留旧卡的开场白数据。

### 🌙 夜间模式
顶栏一键切换暗色主题。CSS 变量驱动的完整配色覆写（深蓝灰底 + 暖白文字），localStorage 持久化偏好，刷新不丢失。

### 📏 强制字数门禁
生成回复后自动统计 `<content>` 中文字数。未达 `wordCount × 80%` 自动重生成（最多 3 次），括号强调字数要求，达标后才交付前端。前端顶栏实时显示字数（绿/橙/红三色）。

### 👤 用户姓名实时同步
前端填写角色名后，右侧状态栏、NPC 列表、正文中所有 `{{user}}` 占位符**即时同步替换**，无需刷新。

### ⚡ 异步交付
回复生成完毕、字数达标后**优先执行 handler.py 交付前端**（3 秒轮询即可看到文字），剧情记忆更新和故事规划分析在后台异步完成，用户无需等待。

### 📊 Token 用量统计
每轮生成后从 Claude Code session transcript 读取 **DeepSeek 真实 token 计数**（非估算），存入 chat_log.json 和 state.js。前端顶栏实时显示**本轮 / 累计** Token 消耗，按卡片独立累计。

</td>
</tr>
</table>

### 🧠 跨会话记忆系统

五种记忆文件存在卡片文件夹下的 `memory/` 目录中，**关闭 Claude Code 明日再开也能接着剧情继续玩**：

| 文件 | 作用 | 更新频率 |
|------|------|---------|
| `memory/project.md` | 剧情进度、未落地伏笔、NPC 状态、下阶段方向 | 每轮自动 |
| `memory/reference.md` | 世界观规则、角色卡核心设定、关键地点 | 几乎不变 |
| `memory/feedback.md` | 用户偏好（文风/节奏/NSFW 边界）、踩过的坑 | 偶尔追加 |
| `memory/user.md` | 用户角色当前状态（外貌/衣着/关系变化） | 低频更新 |
| `memory/story_plan.md` | 长远剧情规划——布克模式/节拍定位/伏笔清单/下阶段方向 | 每 8 轮 |

启动时自动读取全部记忆文件重建叙事上下文，每轮生成后自动更新剧情记忆。

### 📖 剧情规划系统

每隔 8 轮自动加载叙事学理论框架（[STORY.md](STORY.md)），对当前剧情进行长远规划分析：

| 分析维度 | 来源 | 说明 |
|---------|------|------|
| **价值转换检查** | 麦基《故事》 | 每轮是否有有效情感变化？NSFW/氛围场景豁免 |
| **基本情节定位** | 布克 7 种基本情节 | 识别故事模式，日常向/纯 NSFW 填"自由模式" |
| **节拍进度参考** | 救猫咪 15 节拍 | 松散参考，不做强制百分比映射 |
| **角色原型追踪** | 皮尔逊 12 原型 | 追踪每个 NPC 的弧线进展 |
| **伏笔审计** | — | 已埋未收的线索清单，计划回收轮次 |
| **情感波浪线** | — | 张力曲线检查，防止过久单一情绪 |
| **信息不对称** | — | 悬念配置检查与切换建议 |

分析结果写入 `memory/story_plan.md`，框架**服务于故事而非约束故事**。用户也可随时说「分析下故事走向」手动触发。

---

## 🚀 快速开始

### 环境配置（一键脚本）

项目根目录提供了两个配置脚本，自动完成 Node.js / Git 检查、Claude Code 安装、DeepSeek API 环境变量写入（注册表持久化）、PowerShell Profile 备份：

| 文件 | 说明 |
|------|------|
| `setup-deepseek-claude.bat` | 双击运行，自动提权启动 PowerShell 执行配置 |
| `setup-deepseek-claude.ps1` | 核心脚本，右键「使用 PowerShell 运行」也可直接启动 |

运行后按提示输入 DeepSeek API Key 即可。脚本会自动写入以下环境变量（持久化到用户注册表，重启后仍有效）：

```
ANTHROPIC_BASE_URL            = https://api.deepseek.com/anthropic
ANTHROPIC_MODEL               = deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_OPUS_MODEL  = deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_SONNET_MODEL= deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_HAIKU_MODEL = deepseek-v4-flash
CLAUDE_CODE_SUBAGENT_MODEL    = deepseek-v4-flash
CLAUDE_CODE_EFFORT_LEVEL      = max
```

### 前置要求

| 依赖 | 说明 |
|------|------|
| **Python 3.x** | 仅用标准库（`http.server`），无需 pip install |
| **Claude Code** | AI 编排引擎，读取 `CLAUDE.md` 执行规则（由上述脚本自动安装） |
| **现代浏览器** | 访问 `http://localhost:8765` |

### 运行模式：一卡一文件夹

本项目的运行方式是：**在项目根目录下为每张角色卡（或每部小说）单独建立一个文件夹**，放入素材后，在该文件夹内启动 Claude Code。

```
{ROOT}/
├── skills/                     # 引擎代码（所有卡片共享）
├── CLAUDE.md                   # 引擎规则（所有卡片共享）
├── 我的角色/                   # 示例：卡片 A 的文件夹
│   ├── 角色卡.png              #   角色卡 PNG（含嵌入 JSON）
│   ├── 世界书.json             #   世界书（可选）
│   ├── chat_log.json           #   聊天记录（自动生成）
│   └── memory/                 #   跨会话记忆（自动管理）
│       ├── project.md          #     剧情进度
│       ├── reference.md        #     世界观参考
│       ├── feedback.md         #     用户偏好
│       └── user.md             #     用户角色状态
├── 某小说/                     # 示例：小说 B 的文件夹
│   ├── 某小说.txt              #   小说全文
│   ├── chat_log.json           #   聊天记录（自动生成）
│   └── memory/                 #   （同上）
└── 另一张卡/                   # 示例：卡片 C 的文件夹
    ├── 角色.png                #   角色卡 PNG
    ├── chat_log.json           #   聊天记录（自动生成）
    └── memory/                 #   （同上）
```

Claude Code 启动时会自动扫描**当前文件夹**下的素材：
- `.png` → 解析 SillyTavern 角色卡（tEXt/chara chunk）
- `.json` → 读取世界书
- `.txt` → 视为小说文本，提取世界观和角色

### 三步启动

```bash
# 0. 首次使用：运行环境配置脚本（仅需一次）
#    双击 setup-deepseek-claude.bat → 输入 DeepSeek API Key → 完成

# 1. 在项目根目录下新建一个文件夹，放入角色卡/小说
mkdir 我的角色
# 将角色卡.png、世界书.json、小说.txt 等素材放入该文件夹

# 2. 进入该文件夹，启动 Claude Code
cd 我的角色
claude                             # 自动执行 CLAUDE.md 启动流程

# 3. 打开浏览器
# 访问 http://localhost:8765 → 输入框打字 → 点提交
```

> Claude Code 启动后会自动完成：清理残留进程 → 启动桥接服务器 → 扫描当前文件夹素材 → 加载/初始化记忆 → 初始化状态 → 生成开场叙事。你只需要打开浏览器。如果是回老卡，会自动读取 memory/ 下的记忆文件恢复剧情上下文。

### 使用场景

启动 Claude Code 后，在对话中直接输入以下提示词即可：

#### 🎭 角色卡 RP

将角色卡 PNG 放入文件夹，启动 Claude Code 后输入：

> 「在该目录下有一张角色卡 `xxx.png`，分析这张角色卡，我要在这张卡的基础上进行 airp。」

Claude Code 会自动解析 PNG 内嵌的角色设定、开场白和世界书条目，写入记忆文件，并生成开局叙事。

#### 🖊️ 小说炼化文风

将小说 TXT 放入文件夹，启动 Claude Code 后输入：

> 「在该目录下有一部小说 `xxx.txt`，完整阅读此小说全部内容，并总结其文风，命名为 `XXX风格`。」

AI 会自动分析小说的遣词、句式、段落、节奏等六个维度，生成文风配置文件到 `skills/styles/profiles/`。刷新前端即可在下拉框中选择新风格。

#### 📖 进入小说世界 RP

将小说 TXT 放入文件夹，启动 Claude Code 后输入：

> 「在该目录下有一部小说 `xxx.txt`，我要在这张卡的基础上进行 airp。我要扮演的角色是 __（主角/配角/自定义角色）__，同时我想进入的时间点是 __。请完整阅读此小说全部内容，并以我选择的时间点进行开场白描写，以供我进行 airp。」

如果选择自定义角色，需要尽量详细地写出你的设定（身份、外貌、性格、背景、与主线人物的关系等）。AI 会提取小说中的世界观、人物关系和关键剧情节点，以你指定的时间点和角色视角生成开场。

### 切换卡片

关闭当前 Claude Code 会话，`cd` 到另一个卡片文件夹，重新启动即可。引擎代码（`skills/`）是所有卡片共享的，无需复制。

### 关闭

直接退出 Claude Code。下次启动时自动清理残留 Python 进程。

<details>
<summary>🔧 手动启动桥接服务器（可选，通常不需要）</summary>

```bash
python {ROOT}/skills/server.py &
```

服务器默认监听 `127.0.0.1:8765`。

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
│   └── settings.local.json       # 本地权限白名单
└── skills/                       # 后端与前端
    ├── server.py                 # 🌐 HTTP 桥接服务器（端口 8765）
    ├── handler.py                # 🔧 回合管理（解析/追加/重建/回退）
    ├── token_collector.py        # 📊 Token 采集（从 session transcript 读真实 DeepSeek 计数）
    ├── poll.py                   # 📡 输入轮询（备用）
    └── styles/                   # 前端与运行时
        ├── index.html            # 🖥️ 主前端界面（SPA）
        ├── content.html          # 📝 叙事内容模板
        ├── status.html           # 📊 实时状态面板
        ├── settings.json         # ⚙️ 当前设置
        ├── openings.json         # 🎬 开场白数据
        └── profiles/             # 🖊️ 文风配置
            ├── 北棱特调.md       #   文学化/陌生化遣词
            └── 轻松活泼.md       #   简洁明快/口语化
```

> 运行时自动生成的文件（`content.js`、`state.js`、`input.txt`、`.card_path` 等）已加入 `.gitignore`。

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
    C -->|Cron 检测| D[Claude Code]
    D -->|读取配置+历史+memory| E[生成叙事]
    E -->|写入 response.txt| F[字数门禁检查]
    F -->|达标| G[Token 采集]
    G -->|读 transcript JSONL| G2[附加真实 token 计数]
    G2 -->|写入 tokens 标签| H[handler.py]
    F -->|<80% 重试| E
    H -->|重建 content.js| I[前端即时刷新]
    H -->|异步后台| J[更新 memory/]
    J -->|每8轮| K[剧情规划分析]
```

---

## 📚 参考文档

| 文件 | 内容 |
|------|------|
| [`CLAUDE.md`](CLAUDE.md) | 系统编排规则、权限预授权、硬性门禁、文风分析指令 |
| [`STORY.md`](STORY.md) | 叙事理论框架——布克/麦基/坎贝尔/救猫咪/皮尔逊蒸馏 |
| [`extract-png-card.md`](extract-png-card.md) | SillyTavern PNG 角色卡 chunk 解析方法 |
| [`live-status.md`](live-status.md) | 实时状态面板的 HTML/JS 设计说明 |

---

<div align="center">

**⚡ 将 Claude Code 的分析能力，转化为 AI 叙事的创作力 ⚡**

</div>
