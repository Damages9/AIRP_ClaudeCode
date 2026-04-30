#!/usr/bin/env python3
"""MVU Variable Checklist Generator — card-agnostic.

Reads .initvar.json (variable schema) and .var_diff.json (previous-turn audit),
outputs a compact variable-path checklist for the AI generation step.

Usage:
  python mvu_check.py <card_folder>
Output:
  JSON with: sections, untouched_sections, all_paths, checklist hints
The AI uses this to ensure every narrative-touched path has a corresponding _.set()/_.add().
"""

import json
import sys
from pathlib import Path


def collect_leaf_paths(data, prefix=""):
    """Recursively collect all leaf paths from a nested dict."""
    paths = []
    if isinstance(data, dict):
        for k, v in data.items():
            full = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                paths.extend(collect_leaf_paths(v, full))
            else:
                paths.append((full, type(v).__name__, v))
    return paths


def generate_checklist(card_folder: str) -> dict:
    card = Path(card_folder)
    initvar_path = card / ".initvar.json"
    diff_path = card / ".var_diff.json"

    if not initvar_path.exists():
        return {"error": "No .initvar.json found", "hint": "Card has no MVU variables"}

    with open(initvar_path, "r", encoding="utf-8") as f:
        initvar = json.load(f)

    diff = {}
    if diff_path.exists():
        with open(diff_path, "r", encoding="utf-8") as f:
            diff = json.load(f)

    # Collect all leaf paths by section
    sections = {}
    all_paths = []
    for section_name, section_data in initvar.items():
        leaves = collect_leaf_paths(section_data, section_name)
        sections[section_name] = {
            "path_count": len(leaves),
            "paths": [(p, t) for p, t, _ in leaves],
            "sample_values": {p: v for p, _, v in leaves if not isinstance(v, (dict, list))},
        }
        all_paths.extend([p for p, _, _ in leaves])

    # Determine which sections were touched last turn
    touched_sections = []
    untouched_sections = []
    if diff.get("sections"):
        for name, info in diff["sections"].items():
            if info.get("touched"):
                touched_sections.append(name)
            else:
                untouched_sections.append(name)
    else:
        untouched_sections = list(sections.keys())

    # Build a compact checklist for the AI
    checklist_lines = []
    for name, info in sections.items():
        flag = "[TOUCHED]" if name in touched_sections else "[UNTOUCHED]"
        sample = ", ".join(
            f"{p.split('.')[-1]}={v}"
            for p, v in list(info["sample_values"].items())[:5]
        )
        checklist_lines.append(f"  {flag} {name} ({info['path_count']} paths): {sample}")

    return {
        "card_folder": str(card_folder),
        "sections": list(sections.keys()),
        "touched_last_turn": touched_sections,
        "untouched_last_turn": untouched_sections,
        "total_paths": len(all_paths),
        "checklist": "\n".join(checklist_lines),
        "reminder": (
            "For EVERY variable path whose value changes in the narrative, write a "
            "_.set() or _.add() command. Check each section above — if the narrative "
            "touches it, you MUST have a command for it. Especially numeric fields "
            "(inventory counts, HP, money, visit counters)."
        ),
    }


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    result = generate_checklist(folder)
    print(json.dumps(result, ensure_ascii=False, indent=2))
