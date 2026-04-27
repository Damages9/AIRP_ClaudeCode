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
import struct
import sys
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
        chunk_type = data[pos : pos + 4].decode("ascii", errors="ignore")
        pos += 4
        chunk_data = data[pos : pos + length]
        pos += length + 4  # skip CRC
        if chunk_type == "tEXt":
            null_idx = chunk_data.find(b"\x00")
            if null_idx >= 0:
                keyword = chunk_data[:null_idx].decode("latin-1", errors="ignore")
                if keyword in ("chara", "ccv3"):
                    text = chunk_data[null_idx + 1 :].decode("latin-1", errors="ignore")
                    try:
                        decoded = base64.b64decode(text)
                        return json.loads(decoded)
                    except Exception:
                        continue
    return None


def extract_openings(card_data: dict) -> list[dict]:
    """从卡片数据生成 openings.json 条目列表。"""
    openings = []
    first_mes = card_data.get("first_mes", "") or card_data.get("data", {}).get("first_mes", "")

    if first_mes:
        openings.append({
            "id": 0,
            "label": first_mes[:20] if len(first_mes) > 20 else first_mes,
            "content": f"<p>{first_mes}</p>",
            "options": []
        })

    # alternate_greetings 可能在顶层或 data 子对象中
    alt_greetings = card_data.get("alternate_greetings", []) or card_data.get("data", {}).get("alternate_greetings", [])
    for i, greeting in enumerate(alt_greetings):
        openings.append({
            "id": i + 1,
            "label": greeting[:20] if len(greeting) > 20 else greeting,
            "content": f"<p>{greeting}</p>",
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

    # 8. 输出 JSON 摘要
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
