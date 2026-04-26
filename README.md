# 酒馆 RP — Claude Code 直驱模式

Claude Code 作为 AI 叙事引擎的角色扮演系统。Python 桥接服务器 + Web 前端 + 文风配置管理，支持 SillyTavern 格式角色卡。

## 核心特性

- **角色卡支持**：直接读取 SillyTavern PNG 格式角色卡（tEXt/chara chunk → base64 decode → JSON），自动提取角色设定、开场白等
- **文风配置系统**：Markdown 格式风格配置文件，前端下拉框动态切换，AI 严格按配置的遣词/句式/禁用项执行。内置 4 套风格，可通过对话分析小说/作者文风自动生成新配置
- **灵活设置**：NSFW 档位（舒缓/直白/关闭）、人称切换（第一/第二/第三人称）、字数控制（100-3000）、防抢话开关、背景 NPC 开关
- **重roll 与回退**：前端按钮一键重roll 最后一轮或回退到指定轮次
- **开场白切换**：多开场白支持，每套开场白独立配置行动选项
- **用户姓名替换**：前端填入角色名后自动替换正文中所有 `{{user}}` 占位符
- **状态栏**：每轮自动输出角色状态（位置/时间/好感度/服装/身体状态/内心想法）

## 快速开始

### 环境要求

- Python 3.x（仅用标准库，无需额外依赖）
- Claude Code（作为 AI 编排引擎）
- 现代浏览器（前端访问 `http://localhost:8765`）

### 启动步骤

1. **进入卡片文件夹**：在 Claude Code 中 `cd` 到角色卡所在目录（如 `D:\ds4\绿毛\`）
2. **启动 Claude Code**：Claude Code 读取 `CLAUDE.md` 后会自动执行：
   - 清理残留 Python 进程（释放 8765 端口）
   - 启动桥接服务器 `skills/server.py`（端口 8765）
   - 写入卡片路径到 `skills/styles/.card_path`
   - 注册每分钟 Cron 轮询检查用户输入
   - 扫描角色卡素材（PNG/JSON/TXT）
   - 初始化状态文件和聊天记录
   - 生成叙事开场
3. **打开前端**：浏览器访问 `http://localhost:8765`
4. **开始 RP**：在输入框打字，点提交。Claude Code 每分钟自动检查输入并生成叙事回复

### 关闭

直接关闭 Claude Code 即可。下次启动时 Step 0 会自动清理残留进程。

## 目录结构

```
D:\ds4\
├── CLAUDE.md                  # 系统编排核心（规则/权限/流程）
├── README.md                  # 本文件
├── extract-png-card.md        # PNG chunk 角色卡解析参考
├── live-status.md             # 实时状态面板参考
├── .gitignore
├── .claude/                   # Claude Code 配置
│   └── settings.local.json    # 本地权限白名单
├── skills/                    # 后端与前端
│   ├── server.py              # HTTP 桥接服务器（端口 8765）
│   ├── handler.py             # 回合管理（解析/追加/重建/回退）
│   ├── poll.py                # 输入轮询（备用）
│   └── styles/                # 前端与运行时文件
│       ├── index.html         # 主前端界面（SPA）
│       ├── content.html       # 叙事内容模板
│       ├── content.js         # 叙事内容数据（handler.py 自动重建）
│       ├── state.js           # 场景状态（handler.py 自动更新）
│       ├── status.html        # 实时状态面板
│       ├── settings.json      # 当前设置（文风/NSFW/人称/字数）
│       ├── openings.json      # 开场白数据
│       ├── .card_path         # 当前卡片文件夹路径（运行时）
│       ├── input.txt          # 用户输入缓冲区（运行时）
│       └── profiles/          # 文风配置文件
│           ├── 北棱特调.md    # 文学化/陌生化遣词风格
│           ├── 轻松活泼.md    # 简洁明快/口语化风格
│           ├── 轻松后宫流.md  # 校园后宫轻小说风格
│           └── 母猪世界书风格.md  # 词汇库驱动感官饱和风格
└── 绿毛/                      # 当前活跃角色卡（示例）
    ├── 1.png                  # 角色卡 PNG（含嵌入 JSON）
    ├── 母猪世界书.json        # 世界书（27 条 NSFW 规则）
    └── chat_log.json          # 聊天记录
```

## 技术栈

| 层 | 技术 |
|---|---|
| AI 编排 | Claude Code（读取 CLAUDE.md 规则，调用工具执行） |
| 后端 | Python `http.server`（标准库，无框架依赖） |
| 前端 | 原生 HTML/CSS/JS（无框架，动态 script 标签注入实现无闪烁内容更新） |
| 数据格式 | JSON（聊天记录/设置/开场白）+ Markdown（文风配置）+ JavaScript（运行时状态） |
| 角色卡 | SillyTavern PNG 格式（tEXt/chara chunk → base64 → JSON） |

## 文风配置

文风配置文件位于 `skills/styles/profiles/`，Markdown 格式，包含六个标准维度：

- **核心特征**：调性、句式
- **句子模式**：常用句型结构
- **词汇偏好**：偏好用词和避免用词
- **禁用规则**：禁止的表达模式
- **段落结构**：段落密度和组织方式
- **节奏控制**：叙事节奏的张弛模式

### 创建新文风

在对话中发送小说文本（或提供作者名让 AI 联网搜索），然后说「分析这段文风，命名为 XX 风格」。AI 会自动分析六个维度并生成配置到 `profiles/` 下，刷新前端即可在下拉框中选择。

## 数据流

```
用户输入（浏览器）
    → POST /api/submit
    → server.py 写入 input.txt + 创建 .pending
    → Cron/min 检查到 pending
    → Claude Code 读取 input.txt + settings.json + profiles/{style}.md + chat_log.json
    → Claude Code 生成叙事 → 写入 response.txt
    → handler.py 解析 response.txt → 追加 chat_log.json → 重建 content.js → 更新 state.js → /api/done
    → 前端轮询 content.js 变化 → 自动刷新显示
```
