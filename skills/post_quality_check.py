#!/usr/bin/env python3
"""Post-generation quality check: token collection + word count gate.

Merges token_collector.py and CLAUDE.md step 6.5 word count check into one call.

Usage:
  python post_quality_check.py <ROOT>
Output:
  - Appends <tokens> block to response.txt (from session transcript)
  - Prints word count check result
  - Exit code 0 if word count >= threshold * 0.8, exit code 1 otherwise
"""

import json
import os
import re
import sys


def _collect_tokens(root: str) -> dict:
    """Read DeepSeek token usage from Claude Code session transcript."""
    lock_path = os.path.join(root, ".claude", "scheduled_tasks.lock")
    if not os.path.exists(lock_path):
        print("WARNING: no scheduled_tasks.lock, skipping token collection")
        return {}

    try:
        with open(lock_path, "r") as f:
            sid = json.load(f)["sessionId"]
    except Exception:
        print("WARNING: cannot read session ID from lock file")
        return {}

    slug = root.replace(":", "-").replace(chr(92), "-").replace("/", "-")
    transcript = os.path.join(
        os.environ["USERPROFILE"], ".claude", "projects", slug, f"{sid}.jsonl"
    )

    if not os.path.exists(transcript):
        print(f"WARNING: transcript not found: {transcript}")
        return {}

    with open(transcript, "r", encoding="utf-8") as f:
        lines = f.readlines()

    usage = None
    for line in reversed(lines):
        try:
            entry = json.loads(line.strip() or "{}")
        except json.JSONDecodeError:
            continue
        if entry.get("type") == "assistant":
            u = entry.get("message", {}).get("usage", {})
            if u.get("input_tokens") or u.get("output_tokens"):
                usage = u
                break

    if not usage:
        print("WARNING: no usage data in transcript")
        return {}

    return {
        "in": usage.get("input_tokens", 0),
        "out": usage.get("output_tokens", 0),
        "total": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
    }


def _check_word_count(root: str) -> tuple[int, int]:
    """Count Chinese chars in <content> tag. Returns (count, threshold)."""
    resp_path = os.path.join(root, "skills", "styles", "response.txt")
    settings_path = os.path.join(root, "skills", "styles", "settings.json")

    with open(resp_path, "r", encoding="utf-8") as f:
        txt = f.read()

    m = re.search(r"<content>(.*?)</content>", txt, re.DOTALL)
    if m:
        content_text = re.sub(r"<[^>]*>", "", m.group(1))
    else:
        content_text = ""

    count = len(re.findall(r"[一-鿿㐀-䶿]", content_text))

    threshold = 600
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
            threshold = settings.get("wordCount", 600)

    return count, threshold


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )

    # 1. Token collection
    tokens = _collect_tokens(root)

    # 2. Word count check
    word_count, threshold = _check_word_count(root)

    # 3. Append tokens block to response.txt
    resp_path = os.path.join(root, "skills", "styles", "response.txt")
    if tokens:
        tokens_block = (
            f"\n<tokens>\nin: {tokens['in']}\nout: {tokens['out']}"
            f"\ntotal: {tokens['total']}\n</tokens>\n"
        )
        with open(resp_path, "a", encoding="utf-8") as wf:
            wf.write(tokens_block)
        print(f"Token: in={tokens['in']} out={tokens['out']} total={tokens['total']}")
    else:
        print("Token: (skipped)")

    # 4. Word count gate
    passed = word_count >= threshold * 0.8
    print(f"字数: {word_count}/{threshold} {'OK' if passed else 'FAIL (< 80%)'}")
    sys.exit(0 if passed else 1)
