#!/usr/bin/env python3
"""
round_deliver.py — 回合后处理管线。

处理 AI 已写入 response.txt 之后的所有机械步骤：
质检 → handler 交付 → 记忆更新 → 故事规划检查。

用法:
  python round_deliver.py <card_folder> <ROOT>
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def count_chinese(text):
    """Count Chinese characters in text, stripping HTML."""
    clean = re.sub(r"<[^>]+>", "", text)
    count = 0
    for ch in clean:
        cp = ord(ch)
        if 0x4e00 <= cp <= 0x9fff or 0x3400 <= cp <= 0x4dbf or 0x20000 <= cp <= 0x2a6df:
            count += 1
    return count


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "error": "Usage: round_deliver.py <card_folder> <ROOT>"}))
        sys.exit(1)

    card_folder = sys.argv[1]
    root = sys.argv[2]
    styles_dir = Path(root) / "skills" / "styles"
    response_path = styles_dir / "response.txt"

    if not response_path.exists():
        print(json.dumps({"ok": False, "error": "response.txt not found"}))
        sys.exit(1)

    response_text = read_file(response_path)
    if not response_text:
        print(json.dumps({"ok": False, "error": "response.txt is empty"}))
        sys.exit(1)

    # ── 1. Word Count Check ──
    settings = read_json(styles_dir / "settings.json") or {}
    word_count_target = settings.get("wordCount", 2000)
    threshold = int(word_count_target * 0.8)

    content_match = re.search(r"<content>(.*?)</content>", response_text, re.DOTALL)
    content_text = content_match.group(1) if content_match else response_text
    chinese_count = count_chinese(content_text)

    # ── 2. Token Collection ──
    tokens_found = False
    token_data = {"in": 0, "out": 0, "total": 0}
    # Try to read tokens from transcript (best-effort)
    try:
        # Look for the most recent assistant message with usage data in session transcript
        home = os.environ.get("USERPROFILE", os.environ.get("HOME", ""))
        if home:
            sessions_dir = Path(home) / ".claude" / "projects"
            if sessions_dir.exists():
                # Find latest session dir
                dirs = sorted(sessions_dir.glob("*-*"), key=os.path.getmtime, reverse=True)
                for d in dirs[:3]:
                    for jl in sorted(d.glob("*.jsonl"), key=os.path.getmtime, reverse=True):
                        try:
                            lines = jl.read_text(encoding="utf-8").strip().split("\n")
                            for line in reversed(lines[-20:]):
                                entry = json.loads(line)
                                if entry.get("role") == "assistant" and "usage" in entry:
                                    usage = entry["usage"]
                                    token_data = {
                                        "in": usage.get("input_tokens", 0),
                                        "out": usage.get("output_tokens", 0),
                                        "total": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                                    }
                                    tokens_found = True
                                    break
                            if tokens_found:
                                break
                        except Exception:
                            continue
                    if tokens_found:
                        break
    except Exception:
        pass

    # Append tokens to response.txt
    if tokens_found:
        # Check if tokens block already exists
        if "<tokens>" not in response_text:
            with open(response_path, "a", encoding="utf-8") as f:
                f.write(f"\n<tokens>\nin: {token_data['in']}\nout: {token_data['out']}\ntotal: {token_data['total']}\n</tokens>\n")

    # ── 3. Quality Gate ──
    ratio = chinese_count / word_count_target if word_count_target > 0 else 1.0

    if chinese_count < threshold:
        # Word count failed — signal retry
        print(json.dumps({
            "action": "retry",
            "word_count": {"current": chinese_count, "target": word_count_target, "threshold": threshold, "ratio": round(ratio, 2)},
            "tokens": token_data,
            "hint": f"当前 {chinese_count} 字，目标 {word_count_target} 字（最低 {threshold} 字）。请扩充感官细节、NPC 微反应、环境变化。禁止灌水重复。"
        }, ensure_ascii=False))
        sys.exit(0)

    # ── 4. Deliver to Frontend ──
    handler_ok = False
    try:
        result = subprocess.run(
            [sys.executable, str(Path(root) / "skills" / "handler.py"), card_folder],
            capture_output=True, text=True, timeout=30
        )
        handler_ok = result.returncode == 0
        handler_output = result.stdout.strip()
    except Exception as e:
        handler_output = str(e)

    if not handler_ok:
        print(json.dumps({
            "ok": False,
            "error": "handler.py failed",
            "detail": handler_output[:500]
        }, ensure_ascii=False))
        sys.exit(1)

    # ── 5. Memory Update ──
    memory_ok = False
    try:
        result = subprocess.run(
            [sys.executable, str(Path(root) / "skills" / "write_memory.py"), card_folder],
            capture_output=True, text=True, timeout=15
        )
        memory_ok = result.returncode == 0
    except Exception:
        pass

    # ── 6. Story Planning Check ──
    state_js = read_file(styles_dir / "state.js")
    generated_count = 0
    if state_js:
        m = re.search(r"generatedCount:\s*(\d+)", state_js)
        if m:
            generated_count = int(m.group(1))

    plan_interval = 8  # default
    story_plan_due = generated_count > 0 and generated_count % plan_interval == 0

    # ── 7. Summary ──
    summary_text = ""
    summary_match = re.search(r"<summary>(.*?)</summary>", response_text, re.DOTALL)
    if summary_match:
        summary_text = re.sub(r"<[^>]+>", "", summary_match.group(1)).strip()[:200]

    print(json.dumps({
        "action": "done",
        "generatedCount": generated_count,
        "story_plan_due": story_plan_due,
        "word_count": {"current": chinese_count, "target": word_count_target, "ratio": round(ratio, 2)},
        "tokens": token_data,
        "memory_updated": memory_ok,
        "summary": summary_text
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
