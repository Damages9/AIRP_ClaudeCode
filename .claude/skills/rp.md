---
name: rp
description: 标准化启动话本RP流程（新卡开局 / 老卡续玩）
---

在当前目录下启动话本RP流程。

## 第一步：扫描当前目录

查找素材文件（PNG角色卡、JSON世界书、TXT小说）：
- Glob 搜索 `*.png`, `*.json`, `*.txt`
- 同时检查 `chat_log.json` 和 `memory/` 是否存在

## 第二步：根据扫描结果执行

### 情况 A — 有素材，无 chat_log.json（新卡开局）

按 CLAUDE.md「自动启动流程」步骤 0-8 完整执行：

0. 清理残留 Python 进程，确认端口 8765 空闲
1. 启动桥接服务器 `python skills/server.py &`
2. 写入卡片路径到 `skills/styles/.card_path`
3. 注册 Cron 轮询（每分钟检查 `/api/pending`）
4. 执行一键导入：`python skills/import_card.py "<卡片文件夹>" "<ROOT>"`
5. 加载/初始化 memory/ 目录下所有记忆文件
6. 初始化 `state.js`、`content.js`、`chat_log.json`
7. 告知用户：「前端已就绪，打开 http://localhost:8765」「在输入框打字，点提交即可」
8. 若 `response.txt` 已有开场内容（import_card.py 预填）→ 执行 `python skills/handler.py "<卡片文件夹>" --opening` 交付前端，并向用户描述当前开场场景
   若 `response.txt` 为空（卡片无 first_mes）→ 自行生成叙事开场，写入 response.txt，然后执行 handler.py --opening

### 情况 B — 有 chat_log.json + memory/（老卡续玩）

加载 chat_log 和 memory/ 下所有记忆文件（除 reference.md 外）重建完整叙事上下文。
告知用户当前剧情进度（从 project.md 摘要 + 最近 3 轮对话概括），然后继续当前 Cron 轮询模式。

### 情况 C — 无任何素材文件

告知用户：
> 当前目录下没有找到角色卡或小说文件。
> 请放入 PNG 角色卡、JSON 世界书 或 TXT 小说文件后重新执行 `/rp`。
