<div align="center">

# 🍶 酒馆 RP — Claude Code 直驱模式

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

**酒馆 RP 不是 SillyTavern 的替代品。**

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

**酒馆 RP** 是一个以 Claude Code 为编排引擎、Python 标准库为后端的角色扮演系统。

你不需要写 prompt — Claude Code 本身就是 RP 引擎。它读取角色卡、管理对话历史、按选定文风生成叙事，并通过 Web 前端与用户互动。

> 将 Claude Code 的代码分析和工具调用能力，转化为 AI 叙事创作的编排层。

---

## ✨ 核心特性

<table>
<tr>
<td width="50%">

### 🎭 角色卡直读
拖入 SillyTavern PNG 角色卡，自动解析 `tEXt/chara` chunk → 提取角色设定、开场白、世界观。

### 🖊️ 文风配置系统
Markdown 格式风格文件，前端下拉框动态切换。内置 **2 套预设风格**，支持通过对话分析小说/作者文风自动生成新配置。

### ⚙️ 灵活设置面板
NSFW 档位（舒缓/直白/关闭） · 人称切换 · 字数控制（100–3000） · 防抢话开关 · 背景 NPC 开关

</td>
<td width="50%">

### 🔄 重roll 与回退
一键重roll 最后一轮 AI 回复，或回退到任意历史轮次重新输入。

### 🎬 多开场白切换
支持多套开场白，每套独立配置行动选项。切换时保留原有聊天记录。

### 👤 用户姓名替换
前端填写角色名后，正文中所有 `{{user}}` 占位符自动替换。

### 📊 角色状态栏
每轮末尾输出详细状态：时间/地点/好感度/服装/身体状态/内心想法。

</td>
</tr>
</table>

---

## 🚀 快速开始

### 前置要求

| 依赖 | 说明 |
|------|------|
| **Python 3.x** | 仅用标准库（`http.server`），无需 pip install |
| **Claude Code** | AI 编排引擎，读取 `CLAUDE.md` 执行规则 |
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
│   └── chat_log.json           #   聊天记录（自动生成）
├── 某小说/                     # 示例：小说 B 的文件夹
│   ├── 某小说.txt              #   小说全文
│   └── chat_log.json           #   聊天记录（自动生成）
└── 另一张卡/                   # 示例：卡片 C 的文件夹
    ├── 角色.png                #   角色卡 PNG
    └── chat_log.json           #   聊天记录（自动生成）
```

Claude Code 启动时会自动扫描**当前文件夹**下的素材：
- `.png` → 解析 SillyTavern 角色卡（tEXt/chara chunk）
- `.json` → 读取世界书
- `.txt` → 视为小说文本，提取世界观和角色

### 三步启动

```bash
# 1. 在项目根目录下新建一个文件夹，放入角色卡/小说
mkdir 我的角色
# 将角色卡.png、世界书.json、小说.txt 等素材放入该文件夹

# 2. 进入该文件夹，启动 Claude Code
cd 我的角色
claude                             # 自动执行 CLAUDE.md 启动流程

# 3. 打开浏览器
# 访问 http://localhost:8765 → 输入框打字 → 点提交
```

> Claude Code 启动后会自动完成：清理残留进程 → 启动桥接服务器 → 扫描当前文件夹素材 → 初始化状态 → 生成开场叙事。你只需要打开浏览器。

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
├── CLAUDE.md                     # 🧠 系统编排核心（规则/权限/流程）
├── README.md                     # 📄 本文件
├── extract-png-card.md           # 📘 PNG chunk 角色卡解析参考
├── live-status.md                # 📙 实时状态面板参考
├── .gitignore
├── .claude/                      # Claude Code 配置（纳入版本控制）
│   └── settings.local.json       # 本地权限白名单
└── skills/                       # 后端与前端
    ├── server.py                 # 🌐 HTTP 桥接服务器（端口 8765）
    ├── handler.py                # 🔧 回合管理（解析/追加/重建/回退）
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

在对话中粘贴小说文本（或提供作者名让 AI 联网搜索），然后说：

> 「分析这段文风，命名为 XX 风格」

AI 会自动分析六个维度并写入 `profiles/`。刷新前端即可在下拉框中选择新风格。

---

## 🔄 数据流

```mermaid
graph LR
    A[🖥️ 浏览器输入] -->|POST /api/submit| B[server.py]
    B -->|写入 input.txt| C[.pending 标记]
    C -->|Cron 检测| D[Claude Code]
    D -->|读取 settings + 文风 + 历史| E[生成叙事]
    E -->|写入 response.txt| F[handler.py]
    F -->|追加 chat_log| G[重建 content.js]
    G -->|/api/done| H[🖥️ 前端刷新]
```

---

## 📚 参考文档

| 文件 | 内容 |
|------|------|
| [`CLAUDE.md`](CLAUDE.md) | 系统编排规则、权限预授权、硬性门禁、文风分析指令 |
| [`extract-png-card.md`](extract-png-card.md) | SillyTavern PNG 角色卡 chunk 解析方法 |
| [`live-status.md`](live-status.md) | 实时状态面板的 HTML/JS 设计说明 |

---

<div align="center">

**⚡ 将 Claude Code 的分析能力，转化为 AI 叙事的创作力 ⚡**

</div>
