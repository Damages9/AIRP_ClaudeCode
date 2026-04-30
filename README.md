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
<tr>
<td width="50%">

### 📊 MVU 变量系统
支持卡作者原生的 `<UpdateVariable>` + `<JSONPatch>` 格式。五种操作（replace/delta/insert/remove/move），日上限自动检查，阶段提升门禁。正文中 `{{getvar::路径}}` 模板宏实时引用变量当前值。

### 🎯 卡结构驱动编排
自动检测角色卡的**阶段人设**与**动态事件库**（中英文通用）。按 MVU 变量中的当前阶段号检索对应人设，按事件编号驱动剧情触发。无结构卡自动回退自由 RP 模式。

</td>
<td width="50%">

### 👥 后台 NPC 活性
每轮强制更新 ≥2 个未出场 NPC 的行动与内心想法。**三级决策**：静默推进 / 背景提及 / 主动进场。**四种交叉**：人际 / 地点 / 时间 / 危机驱动。世界在玩家视线之外持续运转。

### 📦 多 JSON 世界书合并
PNG 角色卡可搭配**多个 JSON 文件**（全局世界书、文风指导、玩法道具补充）。自动扫描全部 JSON，按条目 ID 去重合并。支持完整卡片格式和纯世界书格式。

</td>
</tr>
</table>

### 🧠 跨会话记忆系统

五种记忆文件 + 两种索引存在卡片文件夹下的 `memory/` 目录中，**关闭 Claude Code 明日再开也能接着剧情继续玩**：

| 文件 | 作用 | 更新频率 |
|------|------|---------|
| `memory/project.md` | 剧情进度、未落地伏笔、NPC 状态、下阶段方向 | 每轮自动 |
| `memory/reference.md` | 世界观规则、角色卡核心设定、关键地点 | 几乎不变 |
| `memory/feedback.md` | 用户偏好（文风/节奏/NSFW 边界）、踩过的坑 | 偶尔追加 |
| `memory/user.md` | 用户角色当前状态（外貌/衣着/关系变化） | 低频更新 |
| `memory/story_plan.md` | 长远剧情规划——布克模式/节拍定位/伏笔清单/下阶段方向 | 每 8 轮 |
| `memory/.worldbook_index.json` | 世界书条目关键词索引，AI 按需 Grep 检索 | 启动时生成 |
| `memory/.card_structure.json` | 卡叙事结构（阶段人设/事件库映射） | 启动时检测 |

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

### 🎬 智能导演系统

除了 AI 自由发挥，系统内置了一套**卡作者原意的导演逻辑**，确保变量、人设、事件按卡作者的设计运行。

#### MVU 变量追踪

完整支持卡作者在角色卡中定义的 `<UpdateVariable>` + `<JSONPatch>` 变量更新标准。replace / delta / insert / remove / move 五种操作，数值日上限自动检查（每角色每日 delta ≤ 5），阶段提升仅在实际触发突破事件时允许。正文中可用 `{{getvar::路径}}` 和 `{{formatvar::路径}}` 模板宏实时引用变量当前值。

#### 卡结构驱动的角色编排

自动扫描 `memory/reference.md` 的 section 标题，检测**阶段化人设**（阶段1-5 / Stage 1-5 / 第X章）和**动态事件库**，生成 `.card_structure.json`。每轮按 MVU 变量中的当前阶段号 Grep 检索对应人设（≤2 角色/轮），按 `待执行事件编号` 驱动剧情触发（铺垫→触发→清理）。无结构卡自动回退自由 RP。

#### 后台 NPC 活性

每轮强制对 ≥2 个未出场角色更新 `角色行动` 和 `内心想法`——即使只是"继续做同一件事"也要推进。**三级决策输出**：

| 级别 | 描述 | 示例 |
|------|------|------|
| 静默推进 | 更新变量，不在叙事中展示 | 柳如烟继续翻看调查报告 |
| 背景提及 | 1-2 句环境细节穿插 | 微信消息、新闻标题、路人对话 |
| 主动进场 | 直接打断当前场景 | 来电、敲门、街角偶遇 |

**四种轨迹交叉**驱动进场判断：人际交叉 / 地点交叉 / 时间交叉 / 危机驱动。轮转优先级按"上次更新距今最久"排序，确保没有角色被遗忘。

#### 多世界书合并

PNG 角色卡可搭配**任意多个 JSON 文件**放入卡片目录——全局世界书、文风指导、色情玩法补充、道具库……系统自动扫描全部 JSON（`data.character_book.entries` 或纯 `entries` 格式），按条目 ID 去重合并。主卡 JSON 不会被重复计算。

#### 世界书按需检索

`reference.md` 不进入对话上下文（保护 prompt cache），改用 `.worldbook_index.json` 轻量索引常驻。当叙事触及索引中的话题时，AI 用 Grep 按 section 标题按需检索完整条目正文。每轮最多检索 2-3 个条目——不堆砌、不遗漏。

---

## 🚀 快速开始

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

> 你会看到：PowerShell 窗口跑一堆安装日志，最后显示"配置完成"。

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

在 `我的角色` 文件夹内打开终端（在该文件夹的地址栏输入 `cmd` 回车），输入：

```bash
claude
```

Claude Code 启动后，在对话中输入 `/rp`（推荐），或者用自然语言告诉它你的素材：

```
/rp
```

或者用自然语言：
- 「分析这张角色卡，我要在上面进行 RP」
- 「读取 `世界书.json`，和角色卡一起导入」
- 「读取 `小说.txt`，我要进入这个世界观」

> 你会看到：Claude Code 开始干活——清理残留进程 → 启动桥接服务器 → 启动输入监听 → 解析角色卡/世界书/小说 → 写入记忆文件 → 生成开场叙事。屏幕上会出现开场的场景描述。老卡会自动读取之前的聊天记录和记忆，接着剧情继续。

**⑤ 打开浏览器**

访问 **http://localhost:8765**，在输入框打字，点提交。AI 会在几秒到几十秒内生成回复。

> 你会看到：页面顶栏显示角色名/状态，中间是叙事内容，下面是输入框。打完字提交后，等待片刻，AI 回复会自动出现在页面上。

**之后怎么继续玩？** 关闭 Claude Code 后，下次在同一个文件夹重新 `claude`，输入 `/rp` 即可——系统会自动读取之前的聊天记录和记忆，接着剧情继续。换卡片就新建一个文件夹，重复步骤 ③-④。

---

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
claude                             # 启动 Claude Code
# 在对话中输入 /rp 启动 RP 流程（或用自然语言描述素材）
# Claude Code 会自动完成：清理残留进程 → 启动服务器+Monitor → 扫描素材 → 导入记忆 → 初始化状态 → 生成开场叙事

# 3. 打开浏览器
# 访问 http://localhost:8765 → 输入框打字 → 点提交
```

> Claude Code 启动后**不会自动触发 RP 流程**——你需要输入 `/rp` 或自然语言指令（如「分析这张角色卡」）。这样做是为了让你有机会指定哪些文件是角色卡、哪些是世界书、哪些是小说。`/rp` 会自动扫描当前目录下的所有素材并判断新卡/老卡。

### 使用场景

除 `/rp` 自动处理外，也可手动输入以下提示词：

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
│   ├── settings.local.json       # 本地权限白名单
│   └── skills/rp.md              # /rp 自定义启动命令
└── skills/                       # 后端与前端
    ├── server.py                 # 🌐 HTTP 桥接服务器（端口 8765）
    ├── handler.py                # 🔧 回合管理（解析/追加/重建/回退）
    ├── import_card.py            # 📥 一键导入（PNG/JSON/TXT → memory/）
    ├── mvu_engine.py             # ⚙️ MVU 变量引擎（JSONPatch 解析/执行）
    ├── mvu_check.py              # ✅ MVU 变量交叉检查
    ├── mvu_server.js             # 🔗 MVU 变量服务（Zod schema 校验）
    ├── match_worldbook.py        # 🔍 世界书关键词匹配
    ├── write_memory.py           # 📝 剧情记忆异步更新
    ├── post_quality_check.py     # 📏 字数门禁 + Token 采集
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
    C -->|Monitor 实时监听| D[Claude Code]
    D -->|读取配置, 历史, memory| D2[世界书索引匹配]
    D2 -->|Grep 检索条目| D3[MVU 变量交叉检查]
    D3 -->|注入规则+卡结构+后台NPC| E[生成叙事]
    E -->|MVU JSONPatch 命令| E2[变量更新]
    E2 -->|写入 response.txt| F[字数门禁检查]
    F -->|达标| G[Token 采集]
    G -->|读 transcript JSONL| G2[附加真实 token 计数]
    G2 -->|写入 tokens 标签| H[handler.py]
    F -->|不足80% 重试| E
    H -->|MVU 命令执行| H2[变量持久化]
    H2 -->|重建 content.js| I[前端即时刷新]
    H2 -->|异步后台| J[更新 memory]
    J -->|每8轮| K[剧情规划分析]
```

### 说人话版：你打一个字，背后发生了什么？

不用看懂上面那张图。用大白话说，从你点"提交"到看到 AI 回复，整个过程是这样的：

```
你在浏览器输入 "你好" → 点提交
                ↓
server.py 收到你的话，写到一个标记文件里
                ↓
Monitor（后台监听器）在 2 秒内发现标记文件 → 通知 Claude Code "有人说话了！"
                ↓
Claude Code 拿到你的输入，开始干活：
  ✦ 看看现在几点、在哪、谁在场
  ✦ 翻翻最近几轮聊了什么
  ✦ 检查有没有世界书条目跟当前场景相关
  ✦ 想想每个 NPC 该怎么反应
  ✦ 按你选的文风写叙事回复
  ✦ 检查字数够不够（不够就重写）
  ✦ 更新变量（时间推进、NPC 状态变化等）
                ↓
把写好的回复交给 handler.py
                ↓
handler.py 把回复组装成网页能显示的格式 → 前端自动刷新
                ↓
你看到 AI 的回复出现在浏览器里 ✨
```

整个过程快则几秒，慢则几十秒（取决于回复长度和复杂度）。

---

## 🆘 常见问题

### 浏览器打不开 http://localhost:8765？

1. 确认 Claude Code 正在运行（终端窗口没关）
2. 检查是否用的 `http://` 而不是 `https://`
3. 如果端口被占用：在终端运行 `netstat -ano | findstr :8765`，找到占用进程后 `taskkill /PID 进程号 /F`

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
| **Zod** | — | TypeScript 生态的 schema 校验库。卡作者用它定义变量结构 |
| **memory/** | — | 卡片文件夹下的记忆目录。存剧情进度、世界观、用户偏好，关了明天还能接着玩 |
| **Monitor** | — | 后台监听器。不眠不休地盯着有没有新用户输入，有就立刻通知 AI 引擎 |
| **重roll** | Re-roll | 删除 AI 最后一轮回复，用同样的用户输入重新生成一次 |

---

<div align="center">

**⚡ 将 Claude Code 的分析能力，转化为 AI 叙事的创作力 ⚡**

</div>
