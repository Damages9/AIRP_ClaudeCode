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

    # ── 2. Token Collection (checkpoint-based delta) ──
    import token_stats

    transcript_path = token_stats.locate_transcript()
    cp = token_stats.load_checkpoint(card_folder) if transcript_path else {}
    byte_offset = cp.get("last_byte_offset", 0)

    # Compute startup cost on first round (previous_checkpoint signals new session)
    startup_delta = None
    if cp.get("previous_checkpoint"):
        startup_delta = token_stats.compute_startup_cost(card_folder)
        # Reload checkpoint — compute_startup_cost wrote startup_cost into it
        cp = token_stats.load_checkpoint(card_folder)
        byte_offset = cp.get("last_byte_offset", 0)

    # Read all usage since last checkpoint
    usage_entries = token_stats.read_usage_since(transcript_path, byte_offset) if transcript_path else []
    delta = token_stats.compute_delta(usage_entries)
    cumulative = cp.get("cumulative", {"input_tokens": 0, "output_tokens": 0})

    # Retrieve startup cost from checkpoint (set by handler.py --opening or compute_startup_cost)
    startup_cost = cp.get("startup_cost")
    st_in = startup_cost.get("input_tokens", 0) if startup_cost else 0
    st_out = startup_cost.get("output_tokens", 0) if startup_cost else 0

    token_data = {
        "in": delta["input_tokens"],
        "out": delta["output_tokens"],
        "total": delta["input_tokens"] + delta["output_tokens"],
        "cache_read": delta["cache_read"],
        "cache_hit_pct": delta["cache_hit_pct"],
        "startup_in": st_in,
        "startup_out": st_out,
        "startup_total": st_in + st_out,
        "cumulative_in": cumulative.get("input_tokens", 0) + delta["input_tokens"],
        "cumulative_out": cumulative.get("output_tokens", 0) + delta["output_tokens"],
        "cumulative_total": (cumulative.get("input_tokens", 0) + cumulative.get("output_tokens", 0) +
                             delta["input_tokens"] + delta["output_tokens"]),
    }

    # ── 3. Quality Gate ──
    ratio = chinese_count / word_count_target if word_count_target > 0 else 1.0

    if chinese_count < threshold:
        # Word count failed — signal retry (do NOT save checkpoint)
        print(json.dumps({
            "action": "retry",
            "word_count": {"current": chinese_count, "target": word_count_target, "threshold": threshold, "ratio": round(ratio, 2)},
            "tokens": token_data,
            "hint": f"当前 {chinese_count} 字，目标 {word_count_target} 字（最低 {threshold} 字）。请扩充感官细节、NPC 微反应、环境变化。禁止灌水重复。"
        }, ensure_ascii=False))
        sys.exit(0)

    # Append token block to response.txt BEFORE handler reads it.
    # Always append (even with delta=0) so cumulative/startup stats are visible.
    if "<tokens>" not in response_text:
        token_block = token_stats.format_token_block(delta, cumulative, startup_cost=startup_cost)
        with open(response_path, "a", encoding="utf-8") as f:
            f.write("\n" + token_block)

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

    # Save checkpoint only after successful delivery
    token_stats.save_checkpoint(card_folder, delta=delta, label="round")

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
