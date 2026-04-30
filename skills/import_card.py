#!/usr/bin/env python3
"""角色卡/世界书导入器 —— 一次调用完成全部素材解析。

用法:
  python import_card.py <卡片文件夹路径> <ROOT路径>

自动检测文件夹内的 .png / .json / .txt 素材，完成:
  1. PNG chunk 解析 (chara → base64 decode → JSON)
  2. 提取角色卡元数据写入 .card_data.json
  3. 生成 openings.json (开局选项列表)
  4. 初始化 memory/ 目录 (世界书条目路由到 reference.md / user.md)
  5. 输出 JSON 摘要到 stdout 供 Claude Code 消费
"""

import json
import os
import re
import struct
import sys
import subprocess
import base64
from pathlib import Path


def parse_png_chunks(filepath: str) -> dict | None:
    """解析 PNG 文件中的 chara 数据 chunk。"""
    with open(filepath, "rb") as f:
        data = f.read()
    pos = 8  # skip PNG signature
    while pos < len(data):
        if pos + 8 > len(data):
            break
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        pos += 4
        chunk_type = data[pos : pos + 4].decode("ascii", errors="replace")
        pos += 4
        chunk_data = data[pos : pos + length]
        pos += length + 4  # skip CRC
        if chunk_type == "tEXt":
            null_idx = chunk_data.find(b"\x00")
            if null_idx >= 0:
                keyword = chunk_data[:null_idx].decode("latin-1", errors="replace")
                if keyword in ("chara", "ccv3"):
                    text = chunk_data[null_idx + 1 :].decode("latin-1", errors="replace")
                    try:
                        decoded = base64.b64decode(text)
                        return json.loads(decoded)
                    except Exception:
                        continue
    return None


def _parse_js_regex(find: str) -> dict:
    """Parse a JS regex literal like /pattern/flags into {"find": str, "flags": str}.

    Returns the raw pattern and flags suitable for new RegExp(find, flags).
    """
    find = find.strip()
    if find.startswith("/"):
        last_slash = find.rfind("/")
        if last_slash > 0:
            pattern = find[1:last_slash]
            flags = find[last_slash + 1:]
            return {"find": pattern, "flags": flags}
    return {"find": find, "flags": ""}


def _extract_all_regex(card_data: dict, card_dir: str) -> dict | None:
    """Extract ALL regex_scripts from the card and save to .regex_scripts.json.

    Also writes .beautify_template.html from the beautify-panel regex (#3).

    Returns info dict with counts and beautify template path (if any).
    """
    import re as _re

    rs_list = (
        card_data.get("data", {})
        .get("extensions", {})
        .get("regex_scripts", [])
    )
    if not isinstance(rs_list, list) or not rs_list:
        return None

    all_regex = []
    beautify_info = None

    for rs in rs_list:
        name = rs.get("scriptName", "")
        find_raw = rs.get("findRegex", "")
        replace = rs.get("replaceString", "")
        markdown_only = rs.get("markdownOnly", False)
        disabled = rs.get("disabled", False)

        if disabled:
            continue

        parsed = _parse_js_regex(find_raw)
        entry = {
            "name": name,
            "find": parsed["find"],
            "flags": parsed["flags"],
            "replace": replace,
            "markdownOnly": markdown_only,
        }
        all_regex.append(entry)

        # Beautify panel: replaces <StatusPlaceHolderImpl/> with full HTML
        if ("StatusPlaceHolder" in find_raw and replace.strip().startswith("```html")):
            html = replace.strip()
            if html.startswith("```html"):
                html = html[7:]
            if html.endswith("```"):
                html = html[:-3]
            html = html.strip()
            if html:
                tpl_path = os.path.join(card_dir, ".beautify_template.html")
                with open(tpl_path, "w", encoding="utf-8") as f:
                    f.write(html)
                beautify_info = {
                    "template_path": tpl_path,
                    "template_size": len(html),
                    "script_name": name,
                }

    # Save all regex scripts
    regex_path = os.path.join(card_dir, ".regex_scripts.json")
    with open(regex_path, "w", encoding="utf-8") as f:
        json.dump(all_regex, f, ensure_ascii=False, indent=2)

    result = {"regex_count": len(all_regex), "regex_path": regex_path}
    if beautify_info:
        result["beautify"] = beautify_info
    return result


def _mes_to_html(text: str) -> str:
    """将 first_mes / alternate_greeting 文本转为 HTML 段落。
    按 \\r\\n\\r\\n 或 \\n\\n 分段，每段用 <p> 包裹。
    自动剥离 MVU 变量块——这些是作者给 MVU 系统的变量数据，不应显示在前端。"""
    import re
    # Strip MVU blocks before paragraph splitting.
    # Card authors may use malformed nesting, so strip each tag type independently.
    text = re.sub(r"<UpdateVariable>[\s\S]*?</UpdateVariable>", "", text)
    text = re.sub(r"<initvar>[\s\S]*?</initvar>", "", text)
    # Keep <StatusPlaceHolderImpl/> — handler.py replaces it with the
    # card author's full beautify panel template from regex_scripts.
    # Also strip any remaining orphaned open/close tags
    text = re.sub(r"</?(?:UpdateVariable|initvar)\s*/?>", "", text)
    paragraphs = re.split(r"\r?\n\s*\r?\n", text.strip())
    return "\n".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())


def extract_openings(card_data: dict) -> list[dict]:
    """从卡片数据生成 openings.json 条目列表。"""
    openings = []
    first_mes = card_data.get("first_mes", "") or card_data.get("data", {}).get("first_mes", "")

    if first_mes:
        openings.append({
            "id": 0,
            "label": first_mes[:20] if len(first_mes) > 20 else first_mes,
            "content": _mes_to_html(first_mes),
            "options": []
        })

    # alternate_greetings 可能在顶层或 data 子对象中
    alt_greetings = card_data.get("alternate_greetings", []) or card_data.get("data", {}).get("alternate_greetings", [])
    for i, greeting in enumerate(alt_greetings):
        openings.append({
            "id": i + 1,
            "label": greeting[:20] if len(greeting) > 20 else greeting,
            "content": _mes_to_html(greeting),
            "options": []
        })

    return openings


def get_card_name(card_data: dict) -> str:
    """提取角色卡名称。"""
    return card_data.get("data", {}).get("name", "") or card_data.get("name", "")


def get_world_name(card_data: dict) -> str:
    """提取世界观名称。"""
    extensions = card_data.get("data", {}).get("extensions", {})
    return extensions.get("world", "") or "未知世界"


def init_memory_entries(entries: list[dict], memory_dir: str) -> dict:
    """将世界书条目路由写入 reference.md 和 user.md。返回写入统计。"""
    os.makedirs(memory_dir, exist_ok=True)

    reference_parts = []
    user_parts = []
    ref_count = 0
    user_count = 0

    for e in entries:
        comment = e.get("comment", "")
        content = e.get("content", "")
        if not content.strip():
            continue
        if "{{user}}" in comment:
            user_parts.append(f"## {comment}\n\n{content}\n\n")
            user_count += 1
        else:
            reference_parts.append(f"## {comment}\n\n{content}\n\n")
            ref_count += 1

    if reference_parts:
        ref_path = os.path.join(memory_dir, "reference.md")
        header = "---\nname: 世界观与设定参考\ndescription: 世界书条目——规则、NPC设计、世界观、叙述规范\ntype: reference\n---\n\n"
        with open(ref_path, "w", encoding="utf-8") as f:
            f.write(header + "".join(reference_parts))

    if user_parts:
        user_path = os.path.join(memory_dir, "user.md")
        header = "---\nname: 用户角色\ndescription: 用户角色设计与设定\ntype: user\n---\n\n"
        with open(user_path, "w", encoding="utf-8") as f:
            f.write(header + "".join(user_parts))

    return {"reference_entries": ref_count, "user_entries": user_count}


def extract_beautify_data(entries: list[dict]) -> dict:
    """从世界书条目中提取 [beautify] 标记的美化数据（立绘 URL、CSS 等）。
    支持与 extract_initvar_data 相同的格式（JSON/YAML/裸文本）。
    """
    import re

    result = {}
    for e in entries:
        comment = e.get("comment", "")
        content = e.get("content", "")
        if not content.strip():
            continue
        if "[beautify]" not in comment.lower():
            continue

        # 尝试从代码块中提取
        code_match = re.search(r"```(?:yaml|json|yml)?\s*([\s\S]*?)```", content)
        if code_match:
            raw = code_match.group(1).strip()
        else:
            raw = content.strip()

        parsed = None
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass

        if parsed is None:
            try:
                import yaml
                parsed = yaml.safe_load(raw)
            except Exception:
                pass

        if isinstance(parsed, dict):
            _deep_merge(result, parsed)

    return result


def _extract_phone_data(card_data: dict) -> dict:
    """Extract phone_data (avatars, backgrounds, fonts, music, user profile)
    from tavern_helper.variables.phone_data in card data.

    This is the card author's phone-theme beautify configuration,
    stored inside tavern_helper scripts, NOT in worldbook [beautify] entries.
    """
    try:
        phone_data = (
            card_data.get("data", {})
            .get("extensions", {})
            .get("tavern_helper", {})
            .get("variables", {})
            .get("phone_data", {})
        )
        if isinstance(phone_data, dict) and phone_data:
            # phone_data has: user, characters, randomAvatars, backgrounds,
            # music, map, groups, fonts
            result = {"phone_data": phone_data}
            # Also extract user avatar as top-level for easy access
            user = phone_data.get("user", {})
            if user:
                if user.get("avatar"):
                    result["user_avatar"] = user["avatar"]
                if user.get("name"):
                    result["user_name"] = user["name"]
                if user.get("font"):
                    result["panel_font"] = user["font"]
                if user.get("phoneBg"):
                    result["panel_bg"] = user["phoneBg"]
            # Pass fonts list for CSS font loading
            fonts = phone_data.get("fonts", [])
            if fonts:
                result["fonts"] = fonts
            return result
    except Exception:
        pass
    return {}


def extract_initvar_data(entries: list[dict]) -> dict:
    """从世界书条目中提取 [initvar] 标记的变量定义，合并为 stat_data。

    支持两种内容格式：
    1. <initvar>...</initvar> XML 块（内容为 YAML/JSON）
    2. 直接的 YAML/JSON 代码块（以 ``` 包裹或裸 JSON）
    """
    import re

    result = {}
    for e in entries:
        comment = e.get("comment", "")
        content = e.get("content", "")
        if not content.strip():
            continue
        if "[initvar]" not in comment.lower():
            continue

        # 尝试从 <initvar> 块中提取
        initvar_match = re.search(
            r"<initvar>([\s\S]*?)</initvar>", content, re.IGNORECASE
        )
        if initvar_match:
            raw = initvar_match.group(1).strip()
        else:
            # 尝试从 ``` 代码块中提取
            code_match = re.search(r"```(?:yaml|json|yml)?\s*([\s\S]*?)```", content)
            if code_match:
                raw = code_match.group(1).strip()
            else:
                raw = content.strip()

        parsed = None
        # 尝试 JSON
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass

        # 尝试 YAML（可选依赖）
        if parsed is None:
            try:
                import yaml
                parsed = yaml.safe_load(raw)
            except Exception:
                pass

        if isinstance(parsed, dict):
            # 深度合并
            _deep_merge(result, parsed)

    return result


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并两个 dict，override 优先。"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _set_nested_path(root: dict, path: str, value):
    """Set a value at a dot-separated path, creating intermediate dicts as needed."""
    parts = path.split(".")
    cur = root
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def extract_initvar_from_beautify_template(card_dir: str) -> dict:
    """Fallback #3: Extract variable paths from BEAUTIFY_HTML macros.

    Parses {{format_message_variable::stat_data.XXX}} and
    {{getvar::stat_data.XXX}} macros from .beautify_template.html,
    building a minimal .initvar.json tree with empty string defaults.
    """
    beautify_path = os.path.join(card_dir, ".beautify_template.html")
    if not os.path.isfile(beautify_path):
        return {}

    try:
        with open(beautify_path, "r", encoding="utf-8") as f:
            html = f.read()
    except Exception:
        return {}

    # Match both macro styles:
    #   {{format_message_variable::stat_data.XXX}}
    #   {{getvar::stat_data.XXX}}
    # Also handle array index suffixes like [0]
    macros = set()
    for pattern in [
        r"\{\{format_message_variable::stat_data\.([\w.]+)",
        r"\{\{getvar::stat_data\.([\w.]+)",
    ]:
        for m in re.findall(pattern, html):
            # Strip trailing array index like .[0] or just [0]
            m = re.sub(r"\[?\d*\]?\.?", ".", m).rstrip(".")
            if m:
                macros.add(m)

    if not macros:
        return {}

    result = {}
    for path in sorted(macros):
        _set_nested_path(result, path, "")

    return result


def extract_initvar_from_worldbook_structured(entries: list[dict]) -> dict:
    """Fallback #4: Extract variable structure from worldbook entries
    that contain structured key-value data (common in Chinese cultivation cards).

    Scans each entry's content for lines matching:
        key: value
        - key: value
    Groups entries by their comment (title) prefix to infer character/section
    hierarchy, then builds a nested initvar tree.
    """
    if not entries:
        return {}

    # First pass: find entries with structured key-value content
    kv_entries = []
    for e in entries:
        content = e.get("content", "")
        comment = e.get("comment", "")
        if not content.strip():
            continue

        # Count key-value lines (Chinese/English keys with colon separator)
        lines = content.strip().split("\n")
        kv_count = 0
        parsed = {}
        for line in lines:
            line = line.strip()
            # Skip markdown headers, empty lines, code blocks
            if not line or line.startswith("#") or line.startswith("```"):
                continue
            # Match: key: value  (key can be Chinese, English, or mixed)
            m = re.match(r"^[-*]?\s*([\w一-鿿＀-￯]+)\s*[:：]\s*(.+)$", line)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip()
                # Skip lines that are full sentences (too long to be variable values)
                if len(val) > 80:
                    continue
                parsed[key] = val
                kv_count += 1

        if kv_count >= 3:  # At least 3 key-value pairs to qualify
            kv_entries.append({
                "comment": comment,
                "kv": parsed,
                "count": kv_count,
            })

    if not kv_entries:
        return {}

    # Second pass: group by inferred character/category from comment
    # Common patterns: "角色名-类别", "类别-子类", or just "类别"
    result = {}
    for ke in kv_entries:
        comment = ke["comment"]
        # Try to extract character name and category from comment
        # e.g. "苏轻韵-衣物" → char="苏轻韵", cat="衣物"
        # e.g. "林墨瞳-修为" → char="林墨瞳", cat="修为"
        parts = re.split(r"[-—・·]", comment, maxsplit=1)
        if len(parts) == 2:
            char = parts[0].strip()
            cat = parts[1].strip()
            if char not in result:
                result[char] = {}
            result[char][cat] = ke["kv"]
        else:
            # Standalone category — put at top level
            cat = comment.strip()
            if cat not in result:
                result[cat] = {}
            result[cat].update(ke["kv"])

    return result


def build_worldbook_index(entries: list[dict], memory_dir: str) -> dict:
    """从世界书条目生成 .worldbook_index.json —— 供 AI 按需检索。

    索引中的每条记录包含：
    - keyword: 主触发词（取自 keys[0]）
    - title: 条目标题（comment）
    - one_liner: Description 第一句话的摘要（30-80 字）
    - section: reference.md 中 Grep 定位用的 Markdown 标题
    """
    import re

    index = []
    for e in entries:
        content = e.get("content", "")
        if not content.strip():
            continue

        comment = e.get("comment", "")
        keys = e.get("keys", [])
        keyword = keys[0] if keys else comment

        # 提取 Description 段的第一句话作为一句话摘要
        one_liner = ""
        desc_match = re.search(r"Description:\s*(.*?)(?:\.|。|\n|Effect:|Dynamic:|Application:)",
                               content, re.DOTALL)
        if desc_match:
            desc_text = desc_match.group(1).strip()
            # 截断到 80 字以内
            if len(desc_text) > 80:
                desc_text = desc_text[:80] + "…"
            one_liner = desc_text
        else:
            # 无 Description 段：取正文前 60 个非标签字符
            clean = re.sub(r"<[^>]*>", "", content).strip()
            first_line = clean.split("\n")[0] if clean else ""
            one_liner = first_line[:60] if len(first_line) > 60 else first_line

        index.append({
            "keyword": keyword,
            "title": comment,
            "one_liner": one_liner,
            "section": f"## {comment}"
        })

    if index:
        index_path = os.path.join(memory_dir, ".worldbook_index.json")
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    return {"index_entries": len(index)}


def analyze_card_structure(memory_dir: str) -> dict:
    """扫描 reference.md 的 ## 标题，检测卡片的叙事结构。

    返回 .card_structure.json 内容：
    - has_stages: 是否检测到阶段化人设
    - has_events: 是否检测到动态事件库
    - characters: { 角色名 → { base_profile, stages: { N: { profile, events } } } }

    检测策略 —— 不硬编码命名约定，用特征正则匹配：
    - 阶段检测：标题含序数词（阶段/Stage/Phase/Chapter/Act + 数字 或 第一二三四五章）
    - 事件检测：标题含事件标记（事件/Event/Scenario/动态/触发/剧情）
    - 角色分组：同一前缀的多个 section 自动聚类
    """
    ref_path = os.path.join(memory_dir, "reference.md")
    if not os.path.exists(ref_path):
        return {"has_stages": False, "has_events": False, "characters": {}}

    # ── 提取所有 ## 标题及其行号 ──
    sections = []
    with open(ref_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^## (.+)$", line)
            if m:
                sections.append(m.group(1).strip())

    if not sections:
        return {"has_stages": False, "has_events": False, "characters": {}}

    # ── 正则模式（中英文通用） ──
    # 阶段序号: 阶段1 / Stage 1 / Phase 1 / Chapter 1 / Act 1 / 第一章 / 第一节
    STAGE_PATTERN = re.compile(
        r"(?:阶段|Stage|Phase|Chapter|Act|第[一二三四五六七八九十\d]+(?:章|节|幕))\s*(\d+)",
        re.IGNORECASE
    )
    # 阶段序号 (中文大写数字): 第一章 → 1
    CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    STAGE_PATTERN_CN = re.compile(r"第([一二三四五六七八九十]+)(?:章|节|幕)")

    # 事件标记
    EVENT_PATTERN = re.compile(
        r"(?:动态)?事件(?:库|列表|目[录録])?|Event|Scenario|Trigger|动态|剧情事件",
        re.IGNORECASE
    )

    # 末端数字兜底（阶段-苏轻韵1 → 提取末尾1）
    STAGE_TRAILING_NUM = re.compile(r"(\d+)$")

    # 人设/档案/Profile 标记 — 含 角色-{name}-{type} 和 语料-{name} 格式
    PROFILE_PATTERN = re.compile(
        r"(?:人设|档案|Profile|角色[介紹介]|[Cc]haracter[ _]?[Ss]heet|角色-|语料-|画像|原点)",
        re.IGNORECASE
    )

    # ── 提取阶段序号 ──
    def extract_stage_num(title: str) -> int | None:
        m = STAGE_PATTERN.search(title)
        if m:
            return int(m.group(1))
        m = STAGE_PATTERN_CN.search(title)
        if m:
            num = 0
            for ch in m.group(1):
                num = num * 10 + CN_NUM.get(ch, 0)
            return num if num > 0 else None
        # Fallback: trailing number (e.g. 阶段-苏轻韵1 → 1, 林墨瞳5 → 5)
        # Only if the title starts with a stage-like prefix
        if re.match(r"^(?:阶段|Stage|Phase|Chapter)", title, re.IGNORECASE):
            m = STAGE_TRAILING_NUM.search(title)
            if m:
                return int(m.group(1))
        return None

    # ── 按角色名聚类 ──
    # 策略：找所有人设/档案 section 作为"角色锚点"，
    # 然后将其他 section 按名称前缀匹配到对应角色。
    character_anchors = {}  # role_name → base_profile_section_title

    # Helper: extract character name from section title
    def extract_role_name(title: str) -> str | None:
        """Extract a character name from a section title.
        Handles patterns like:
          - 角色-苏轻韵-原点  → 苏轻韵
          - 角色-樱咲琉华-画像 → 樱咲琉华
          - 语料-净月临光     → 净月临光
          - 阶段-林墨瞳1      → 林墨瞳
          - 格蕾丝·莉莉-人设  → 格蕾丝·莉莉
        """
        # Pattern 1: 角色-{name}-{type} or 语料-{name} or 阶段-{name}N
        m = re.match(r"^(?:角色|语料|阶段|实例)-(.+?)(?:[-−](?:原点|画像|\d+.*)|[\d]*)$", title)
        if m:
            return m.group(1).strip()
        # Pattern 2: {name}-人设 / {name}-档案 / {name} profile
        m = re.match(r"^(.+?)[-_](?:人设|档案|[Pp]rofile|画像|原点)$", title)
        if m:
            return m.group(1).strip()
        return None

    for s in sections:
        if PROFILE_PATTERN.search(s):
            # Try structured extraction first
            role_name = extract_role_name(s)
            if role_name and len(role_name) >= 2:
                character_anchors[role_name] = s
            else:
                # Fallback: strip profile markers
                role_name = PROFILE_PATTERN.sub("", s).strip()
                role_name = re.sub(r"^[/_\-：:·•]", "", role_name).strip()
                role_name = re.sub(r"[-_](?:原点|画像)$", "", role_name).strip()
                if role_name and len(role_name) >= 2:
                    character_anchors[role_name] = s

    # 若未检测到任何人设 section，尝试从所有 section 中提取角色名
    if not character_anchors:
        # Try extract_role_name on all sections
        for s in sections:
            role_name = extract_role_name(s)
            if role_name and len(role_name) >= 2 and role_name not in character_anchors:
                character_anchors[role_name] = s
        # Still nothing? Fall back to prefix clustering
        if not character_anchors:
            prefix_groups = {}
            for s in sections:
                clean = s.strip()
                parts = re.split(r"[-_的之·•]", clean)
                if parts:
                    prefix = parts[0].strip()
                    if len(prefix) >= 2:
                        if prefix not in prefix_groups:
                            prefix_groups[prefix] = []
                        prefix_groups[prefix].append(s)
            for prefix, secs in prefix_groups.items():
                if len(secs) >= 2:
                    character_anchors[prefix] = secs[0]

    # ── 构建角色结构 ──
    characters = {}
    global_has_stages = False
    global_has_events = False

    for role_name, base_section in character_anchors.items():
        char_entry = {"base_profile": f"## {base_section}", "stages": {}}

        # 找属于该角色的所有相关 section
        # 策略：role_name 可能含 ·/-/空格 等分隔符（如"格蕾丝·莉莉"），
        # 但阶段 section 可能只用前半段（如"格蕾丝_阶段1"）。
        # 因此同时尝试完整名和按 ·/-/_/空格 拆分后的各片段。
        name_parts = re.split(r"[·•\-_ 　]+", role_name)
        related = []
        for s in sections:
            if s == base_section:
                continue
            # 完整名匹配
            if role_name in s:
                related.append(s)
                continue
            # 片段匹配：所有非短片段（≥2字符）都在 section 中出现
            significant_parts = [p for p in name_parts if len(p) >= 2]
            if significant_parts and all(p in s for p in significant_parts):
                related.append(s)
                continue
            # 前缀匹配：section 以 role_name 的前 N 个字符开头
            for prefix_len in range(len(role_name), 1, -1):
                prefix = role_name[:prefix_len]
                if s.startswith(prefix):
                    related.append(s)
                    break

        # 在这些相关 section 中检测阶段
        stage_sections = {}  # stage_num → {"profile": title, "events": title}
        for s in related:
            num = extract_stage_num(s)
            if num is not None:
                if num not in stage_sections:
                    stage_sections[num] = {"profile": None, "events": None}
                if EVENT_PATTERN.search(s):
                    stage_sections[num]["events"] = f"## {s}"
                    global_has_events = True
                else:
                    stage_sections[num]["profile"] = f"## {s}"

        # 只保留同时有序号和至少一种内容的阶段
        for num, data in sorted(stage_sections.items()):
            if data["profile"] or data["events"]:
                char_entry["stages"][str(num)] = {
                    "profile": data["profile"],
                    "events": data["events"],
                }
                global_has_stages = True

        # 即使没有阶段，也保留角色条目（标记为仅有基础人设）
        characters[role_name] = char_entry

    return {
        "has_stages": global_has_stages,
        "has_events": global_has_events,
        "characters": characters,
    }


def create_memory_index(memory_dir: str, card_name: str, world_name: str) -> None:
    """创建/更新 MEMORY.md 索引。"""
    memory_files = {}
    for fname in os.listdir(memory_dir):
        if fname.endswith(".md") and fname != "MEMORY.md":
            fpath = os.path.join(memory_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    first_line = ""
                    for line in f:
                        if line.startswith("description:"):
                            first_line = line.split(":", 1)[1].strip()
                            break
                memory_files[fname] = first_line or "待补充"
            except Exception:
                memory_files[fname] = "待补充"

    lines = ["# 记忆索引\n\n"]
    for fname in ["project.md", "reference.md", "feedback.md", "user.md", "story_plan.md"]:
        if fname in memory_files:
            desc = memory_files[fname]
            lines.append(f"- [{fname}](memory/{fname}) — {desc}\n")

    index_path = os.path.join(memory_dir, "MEMORY.md")
    with open(index_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def run_card_scripts(card_dir: str, root_dir: str) -> dict | None:
    """Call Node.js runner to execute card's tavern_helper scripts.
    Returns structured JSON with initvar/schema/injections, or None on failure.
    """
    runner_path = os.path.join(root_dir, "skills", "run_card_scripts.js")
    if not os.path.isfile(runner_path):
        return None
    try:
        result = subprocess.run(
            ["node", runner_path, card_dir],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
            cwd=os.path.join(root_dir, "skills"),
        )
        if result.returncode == 0 and result.stdout and result.stdout.strip():
            data = json.loads(result.stdout)
            if data.get("_no_scripts") or data.get("_parse_failed"):
                return None
            return data
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        pass
    return None


def _merge_json_worldbooks(card_data, json_files, card_dir, skip_file=None):
    """合并所有 JSON 文件中的 character_book.entries 到 card_data。
    支持完整卡片格式 (data.character_book.entries) 和纯世界书格式 (entries)。
    按 entry.id 去重。返回 (合并的额外文件数, 合并的额外条目数)。"""
    card_data.setdefault("data", {}).setdefault("character_book", {}).setdefault("entries", [])
    existing = card_data["data"]["character_book"]["entries"]
    existing_ids = {e.get("id") for e in existing if isinstance(e, dict) and e.get("id")}

    file_count = 0
    entry_count = 0
    for jf in json_files:
        if jf == skip_file:
            continue
        jpath = os.path.join(card_dir, jf)
        try:
            with open(jpath, "r", encoding="utf-8") as f:
                jdata = json.load(f)
        except Exception:
            continue

        entries = jdata.get("data", {}).get("character_book", {}).get("entries", [])
        if not isinstance(entries, list) or not entries:
            entries = jdata.get("entries", [])
        if not isinstance(entries, list) or not entries:
            continue

        added = 0
        for entry in entries:
            eid = entry.get("id") if isinstance(entry, dict) else None
            if eid and eid in existing_ids:
                continue
            existing.append(entry)
            if eid:
                existing_ids.add(eid)
            added += 1

        if added > 0:
            file_count += 1
            entry_count += added

    return file_count, entry_count


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "用法: import_card.py <卡片文件夹> <ROOT路径>"}, ensure_ascii=False))
        sys.exit(1)

    card_dir = sys.argv[1]
    root_dir = sys.argv[2]
    styles_dir = os.path.join(root_dir, "skills", "styles")
    os.makedirs(styles_dir, exist_ok=True)

    result = {
        "status": "ok",
        "card_dir": card_dir,
        "card_name": "",
        "world_name": "",
        "source_type": "",
        "openings_count": 0,
        "memory": {},
        "worldbook_entries_total": 0,
    }

    # 1. 扫描素材（跳过隐藏文件）
    files = os.listdir(card_dir) if os.path.isdir(card_dir) else []
    files = [f for f in files if not f.startswith(".")]
    png_files = [f for f in files if f.lower().endswith(".png")]
    json_files = [f for f in files if f.lower().endswith(".json")]
    txt_files = [f for f in files if f.lower().endswith(".txt")]

    card_data = None
    primary_json_file = None

    # 2. PNG 优先解析
    for png_file in png_files:
        png_path = os.path.join(card_dir, png_file)
        card_data = parse_png_chunks(png_path)
        if card_data:
            result["source_type"] = "png"
            result["source_file"] = png_file
            break

    # 3. JSON 备选
    if card_data is None and json_files:
        for jf in json_files:
            jpath = os.path.join(card_dir, jf)
            try:
                with open(jpath, "r", encoding="utf-8") as f:
                    card_data = json.load(f)
                result["source_type"] = "json"
                result["source_file"] = jf
                primary_json_file = jf
                break
            except Exception:
                continue

    # 4. TXT 备选
    if card_data is None and txt_files:
        # TXT 文件不是结构化数据，读取文本内容
        txt_content = ""
        for tf in txt_files:
            tpath = os.path.join(card_dir, tf)
            try:
                with open(tpath, "r", encoding="utf-8") as f:
                    txt_content += f.read() + "\n"
            except Exception:
                pass
        if txt_content.strip():
            card_data = {"first_mes": txt_content.strip(), "name": txt_files[0].replace(".txt", "")}
            result["source_type"] = "txt"
            result["source_file"] = txt_files[0]

    # 4.5 合并所有 JSON 中的世界书条目（全局世界书 / 文风指导 / 玩法补充）
    if card_data is not None and json_files:
        extra_files, extra_entries = _merge_json_worldbooks(card_data, json_files, card_dir, primary_json_file)
        if extra_files > 0:
            result["merged_worldbooks"] = {"files": extra_files, "entries": extra_entries}

    if card_data is None:
        result["status"] = "no_card_found"
        result["files_scanned"] = {"png": len(png_files), "json": len(json_files), "txt": len(txt_files)}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

    # 5. 提取元数据
    result["card_name"] = get_card_name(card_data)
    result["world_name"] = get_world_name(card_data)

    # 保存完整卡片数据到 card_dir
    card_data_path = os.path.join(card_dir, ".card_data.json")
    with open(card_data_path, "w", encoding="utf-8") as f:
        json.dump(card_data, f, ensure_ascii=False, indent=2)

    # 6. 生成 openings.json
    openings = extract_openings(card_data)
    result["openings_count"] = len(openings)
    openings_path = os.path.join(styles_dir, "openings.json")
    with open(openings_path, "w", encoding="utf-8") as f:
        json.dump(openings, f, ensure_ascii=False, indent=2)

    # 7. 处理世界书条目 → memory/
    entries = card_data.get("data", {}).get("character_book", {}).get("entries", [])
    if isinstance(entries, list) and entries:
        result["worldbook_entries_total"] = len(entries)
        memory_dir = os.path.join(card_dir, "memory")
        mem_stats = init_memory_entries(entries, memory_dir)
        result["memory"] = mem_stats

        # 生成世界书索引（供 AI 按需 Grep 检索，不进入对话上下文）
        index_stats = build_worldbook_index(entries, memory_dir)
        result["worldbook_index"] = index_stats

        # 检测卡片叙事结构（阶段人设/动态事件库）
        structure = analyze_card_structure(memory_dir)
        struct_path = os.path.join(memory_dir, ".card_structure.json")
        with open(struct_path, "w", encoding="utf-8") as f:
            json.dump(structure, f, ensure_ascii=False, indent=2)
        result["card_structure"] = structure

        # 7.1 初始化其他 memory 文件（若不存在）
        project_path = os.path.join(memory_dir, "project.md")
        if not os.path.exists(project_path):
            with open(project_path, "w", encoding="utf-8") as f:
                f.write("---\nname: 剧情进度\ndescription: 待初始化\ntype: project\n---\n\n# 剧情进度\n\n待开局后填入。\n")

        feedback_path = os.path.join(memory_dir, "feedback.md")
        if not os.path.exists(feedback_path):
            with open(feedback_path, "w", encoding="utf-8") as f:
                f.write("---\nname: 用户偏好\ndescription: 文风/节奏/边界偏好\ntype: feedback\n---\n\n# 用户偏好\n\nNSFW 档位: 舒缓\n")

        story_plan_path = os.path.join(memory_dir, "story_plan.md")
        if not os.path.exists(story_plan_path):
            with open(story_plan_path, "w", encoding="utf-8") as f:
                f.write("---\nname: 剧情规划\ndescription: 待首次规划\ntype: project\nnext_plan_at: 第8轮\n---\n\n# 剧情规划\n\n待触发。\n")

        create_memory_index(memory_dir, result["card_name"], result["world_name"])

        # 7.1.5 Extract ALL regex_scripts FIRST (writes .beautify_template.html)
        #     Must run before initvar fallback #3 which reads beautify template macros.
        regex_info = _extract_all_regex(card_data, card_dir)
        if regex_info:
            result["regex_scripts"] = regex_info

        # 7.2 MVU: 优先使用 Node.js runner 执行卡片的 tavern_helper 脚本
        #    跑 runner → 写入 .initvar.json + .initvar_schema.json + .injection_rules.json
        #    失败或无 tavern_helper → 回退到世界书 [initvar] 条目（兼容旧卡）
        runner_data = run_card_scripts(card_dir, root_dir)
        if runner_data:
            # Write .initvar.json (variable template from Zod schema)
            if runner_data.get("initvar"):
                initvar_path = os.path.join(card_dir, ".initvar.json")
                with open(initvar_path, "w", encoding="utf-8") as f:
                    json.dump(runner_data["initvar"], f, ensure_ascii=False, indent=2)
                result["initvar_keys"] = list(runner_data["initvar"].keys())
                result["initvar_source"] = "tavern_helper (Zod schema via Node.js)"
            # Write .initvar_schema.json (type metadata + constraints + enums)
            if runner_data.get("schema"):
                schema_path = os.path.join(card_dir, ".initvar_schema.json")
                with open(schema_path, "w", encoding="utf-8") as f:
                    json.dump(runner_data["schema"], f, ensure_ascii=False, indent=2)
                result["schema_fields"] = len(runner_data["schema"].get("fields", {}))
                result["schema_constraints"] = len(runner_data["schema"].get("constraints", []))
            # Write .injection_rules.json (kink keyword injection config)
            if runner_data.get("injections"):
                inj_path = os.path.join(card_dir, ".injection_rules.json")
                with open(inj_path, "w", encoding="utf-8") as f:
                    json.dump(runner_data["injections"], f, ensure_ascii=False, indent=2)
                result["injection_rules"] = len(runner_data["injections"])
            # Write .initvar_scope.json (variable scope metadata)
            if runner_data.get("scope"):
                scope_path = os.path.join(card_dir, ".initvar_scope.json")
                with open(scope_path, "w", encoding="utf-8") as f:
                    json.dump(runner_data["scope"], f, ensure_ascii=False, indent=2)
                result["scope"] = runner_data["scope"]
        else:
            # Fallback #2: extract [initvar] from worldbook entries
            initvar_data = extract_initvar_data(entries)
            if initvar_data:
                initvar_path = os.path.join(card_dir, ".initvar.json")
                with open(initvar_path, "w", encoding="utf-8") as f:
                    json.dump(initvar_data, f, ensure_ascii=False, indent=2)
                result["initvar_keys"] = list(initvar_data.keys())
                result["initvar_source"] = "worldbook [initvar] (fallback #2)"

        # Fallback #3: extract from beautify template {{format_message_variable}} macros
        if not result.get("initvar_keys"):
            beautify_initvar = extract_initvar_from_beautify_template(card_dir)
            if beautify_initvar:
                initvar_path = os.path.join(card_dir, ".initvar.json")
                with open(initvar_path, "w", encoding="utf-8") as f:
                    json.dump(beautify_initvar, f, ensure_ascii=False, indent=2)
                result["initvar_keys"] = list(beautify_initvar.keys())
                result["initvar_source"] = "beautify template macros (fallback #3)"

        # Fallback #4: extract structured key-value from worldbook entries
        # (common in Chinese cultivation cards without explicit [initvar] tags)
        if not result.get("initvar_keys"):
            wb_initvar = extract_initvar_from_worldbook_structured(entries)
            if wb_initvar:
                initvar_path = os.path.join(card_dir, ".initvar.json")
                with open(initvar_path, "w", encoding="utf-8") as f:
                    json.dump(wb_initvar, f, ensure_ascii=False, indent=2)
                result["initvar_keys"] = list(wb_initvar.keys())
                result["initvar_source"] = "worldbook structured KV (fallback #4)"

        # 7.3 Beautify: 提取 [beautify] 美化数据 → .beautify.json
        beautify_data = extract_beautify_data(entries)

        # 7.3.1 Also extract phone_data from tavern_helper (phone theme UI)
        phone_data = _extract_phone_data(card_data)
        if phone_data:
            _deep_merge(beautify_data, phone_data)

        if beautify_data:
            beautify_path = os.path.join(card_dir, ".beautify.json")
            with open(beautify_path, "w", encoding="utf-8") as f:
                json.dump(beautify_data, f, ensure_ascii=False, indent=2)
            result["beautify_keys"] = list(beautify_data.keys())

        # 7.3.2 (regex_scripts already extracted above, before initvar chain)

    # 8. 预填 response.txt（卡片 first_mes），避免 AI 在开局时重写
    if openings:
        opening = openings[0]
        content_html = opening["content"]
        summary_text = opening["label"][:60] if opening["label"] else ""
        resp_txt = f"<content>\n{content_html}\n</content>\n<summary>{summary_text}</summary>\n<options>\n</options>\n"
        resp_path = os.path.join(styles_dir, "response.txt")
        with open(resp_path, "w", encoding="utf-8") as f:
            f.write(resp_txt)
        result["response_txt_written"] = True

    # 创建 .session_init，标记会话已初始化（跳过 selector 重定向）
    session_path = os.path.join(styles_dir, ".session_init")
    Path(session_path).touch()
    result["session_init"] = True

    # 9. 输出 JSON 摘要
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
