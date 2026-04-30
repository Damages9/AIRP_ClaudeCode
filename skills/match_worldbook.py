#!/usr/bin/env python3
"""Match changed variables against worldbook index → return top-3 relevant entries.

Replaces CLAUDE.md step 2.5 AI-driven worldbook matching with deterministic logic.

Usage:
  python match_worldbook.py <card_folder>
Output:
  JSON array [{keyword, title, section, one_liner, score, reason}]
  Top 3 entries sorted by relevance score. Empty array if no matches.
"""

import json
import sys
import re
from pathlib import Path


def load_json(path):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
    return None


def extract_topics_from_diff(diff: dict, initvar: dict) -> list[str]:
    """Extract search topics from changed variable paths and values."""
    topics = []

    changed = diff.get("changed", {})
    for path, change in changed.items():
        # Add path segments as topics
        segments = [s for s in path.split(".") if s and not s.startswith("_")]
        for seg in segments:
            if seg not in topics and len(seg) >= 2:
                topics.append(seg)

        # If new value is a string, extract meaningful words
        new_val = change.get("new")
        if isinstance(new_val, str) and len(new_val) < 200:
            # Split on punctuation for CJK text
            words = re.split(r"[，,、。；;：:！!？?\s]+", new_val)
            for w in words:
                w = w.strip()
                if len(w) >= 2 and w not in topics:
                    topics.append(w)

    # Also add section names from initvar
    if initvar:
        for section_name in initvar:
            if section_name not in topics:
                topics.append(section_name)

    return topics


def score_match(keyword: str, topics: list[str]) -> tuple[int, str]:
    """Score a worldbook keyword against topic list. Returns (score, reason)."""
    best_score = 0
    best_reason = ""

    for topic in topics:
        if not topic:
            continue

        # Exact match
        if keyword == topic:
            if best_score < 10:
                best_score = 10
                best_reason = f"exact match: {topic}"

        # Keyword is substring of topic
        elif keyword in topic:
            s = 7
            if s > best_score:
                best_score = s
                best_reason = f"keyword in topic: {topic}"

        # Topic is substring of keyword
        elif topic in keyword:
            s = 6
            if s > best_score:
                best_score = s
                best_reason = f"topic in keyword: {topic}"

        # Partial character overlap (for CJK)
        elif len(keyword) >= 2 and len(topic) >= 2:
            overlap = sum(1 for c in keyword if c in topic)
            if overlap >= 2:
                s = 3 + overlap
                if s > best_score:
                    best_score = s
                    best_reason = f"char overlap({overlap}): {topic}"

    return best_score, best_reason


def match_worldbook(card_folder: str) -> list[dict]:
    card = Path(card_folder)

    diff_path = card / ".var_diff.json"
    index_path = card / "memory" / ".worldbook_index.json"
    initvar_path = card / ".initvar.json"

    diff = load_json(diff_path) or {}
    worldbook = load_json(index_path) or []
    initvar = load_json(initvar_path) or {}

    if not worldbook:
        return []

    topics = extract_topics_from_diff(diff, initvar)

    # Skip noise entries — these are always present but rarely need matching
    skip_keywords = {"[initvar]变量初始化勿开", "[mvu_update]变量更新规则",
                     "[mvu_update]变量输出格式", "[mvu_update]变量输出格式强调",
                     "变量列表"}

    results = []
    for entry in worldbook:
        kw = entry.get("keyword", "")
        if kw in skip_keywords:
            continue
        score, reason = score_match(kw, topics)
        if score > 0:
            results.append({
                "keyword": kw,
                "title": entry.get("title", kw),
                "section": entry.get("section", f"## {kw}"),
                "one_liner": entry.get("one_liner", ""),
                "score": score,
                "reason": reason,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:3]


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    matches = match_worldbook(folder)
    print(json.dumps(matches, ensure_ascii=False, indent=2))
