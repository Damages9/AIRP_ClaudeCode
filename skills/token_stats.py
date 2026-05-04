#!/usr/bin/env python3
"""
token_stats.py — Token statistics with checkpoint-based delta tracking.

Reads Claude Code session transcript JSONL files to compute per-round
and cumulative token usage, including cache hit rates.

Key features:
- Delta-based: tracks byte_offset in transcript, computes increment since
  last checkpoint (not just the last API call)
- Cross-session: detects new session → preserves cumulative/rounds history,
  resets offset to 0 for new transcript
- Cache hit rate: extracts cache_read_input_tokens from usage data

Used by: round_deliver.py (per-round stats), import_prepare.py (init checkpoint),
         handler.py (startup_end checkpoint)
"""

import json
import os
import sys
from pathlib import Path


def _project_slug():
    """Derive project slug from current working directory.
    Mirrors Claude Code's convention: D:\\ds4\\test → D--ds4-test."""
    cwd = os.getcwd()
    # Drive letter prefix: D:\ → D--
    slug = cwd.replace(':\\', '--', 1).replace(':/', '--', 1)
    # Remaining path separators → -
    slug = slug.replace('\\', '-').replace('/', '-')
    return slug


def _sessions_dir():
    """Return the ~/.claude/projects/<slug>/ directory."""
    home = os.environ.get("USERPROFILE", os.environ.get("HOME", ""))
    if not home:
        return None
    return Path(home) / ".claude" / "projects" / _project_slug()


def locate_transcript():
    """Find the current session's JSONL transcript file.

    Scans ~/.claude/projects/<slug>/ for the most recently modified
    .jsonl file. Returns Path, or None if not found.
    """
    sessions_dir = _sessions_dir()
    if not sessions_dir or not sessions_dir.exists():
        return None

    jsonl_files = list(sessions_dir.glob("*.jsonl"))
    if not jsonl_files:
        return None

    jsonl_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return jsonl_files[0]


def read_usage_since(transcript_path, byte_offset=0):
    """Read transcript JSONL from byte_offset onward, return all usage entries.

    Each entry: {input_tokens, output_tokens, cache_read_input_tokens,
                  cache_creation_input_tokens}

    Returns list of dicts (empty if no new data).
    """
    path = Path(transcript_path)
    if not path.exists():
        return []

    try:
        size = path.stat().st_size
        if size <= byte_offset:
            return []

        with open(path, "r", encoding="utf-8") as f:
            f.seek(byte_offset)
            raw = f.read()
    except Exception:
        return []

    entries = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Current Claude Code format: {type: "assistant", message: {usage: {...}}}
        if entry.get("type") != "assistant":
            continue

        usage = entry.get("message", {}).get("usage")
        if not usage:
            # Older format: {role: "assistant", usage: {...}}
            usage = entry.get("usage")
        if not usage:
            continue

        entries.append({
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
        })

    return entries


def compute_delta(entries):
    """Aggregate a list of usage entries into a single delta dict.

    Returns {input_tokens, output_tokens, cache_read, cache_creation, request_count,
             cache_hit_pct}
    cache_hit_pct = cache_read / total_input * 100 (0 if no input).
    """
    if not entries:
        return {
            "input_tokens": 0, "output_tokens": 0,
            "cache_read": 0, "cache_creation": 0,
            "request_count": 0, "cache_hit_pct": 0.0,
        }

    total_in = sum(e["input_tokens"] for e in entries)
    total_out = sum(e["output_tokens"] for e in entries)
    cache_read = sum(e["cache_read_input_tokens"] for e in entries)
    cache_creation = sum(e["cache_creation_input_tokens"] for e in entries)

    cache_hit_pct = round(cache_read / (total_in + cache_read) * 100, 1) if (total_in + cache_read) > 0 else 0.0

    return {
        "input_tokens": total_in,
        "output_tokens": total_out,
        "cache_read": cache_read,
        "cache_creation": cache_creation,
        "request_count": len(entries),
        "cache_hit_pct": cache_hit_pct,
    }


def load_checkpoint(card_folder):
    """Load .token_checkpoint.json, handling cross-session transcript changes.

    If the transcript path has changed (new Claude Code session), preserves
    cumulative totals and round history, resets byte_offset to 0 for the
    new transcript file.

    Returns dict with keys: transcript_path, byte_offset, cumulative, rounds,
    startup_cost, previous_checkpoint. Returns empty dict if no checkpoint exists.
    """
    cp_path = Path(card_folder) / ".token_checkpoint.json"
    if not cp_path.exists():
        return {}

    try:
        cp = json.loads(cp_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return {}

    current_transcript = locate_transcript()
    if not current_transcript:
        return cp

    old_path = cp.get("transcript_path", "")
    new_path = str(current_transcript.resolve())

    if old_path != new_path:
        # New session: preserve cumulative/rounds/startup_cost, reset offset
        cp["transcript_path"] = new_path
        cp["last_byte_offset"] = 0
        # Store the old checkpoint data so we can compute startup delta
        if not cp.get("startup_cost"):
            cp["previous_checkpoint"] = {
                "cumulative": cp.get("cumulative", {}),
                "last_byte_offset": 0,
            }
        else:
            cp["previous_checkpoint"] = {
                "cumulative": cp.get("cumulative", {}),
            }
        _write_checkpoint(card_folder, cp)

    return cp


def save_checkpoint(card_folder, delta=None, label=None):
    """Update .token_checkpoint.json with a new round/frame entry.

    Args:
        card_folder: path to card directory
        delta: dict from compute_delta() — this round's token usage
        label: "startup" or "round" — labels the entry in rounds[]
    """
    cp = load_checkpoint(card_folder)

    transcript = locate_transcript()
    if not transcript:
        return

    # Current transcript size = new byte_offset
    try:
        new_offset = transcript.stat().st_size
    except Exception:
        new_offset = 0

    # Initialize if new
    if not cp:
        cp = {
            "transcript_path": str(transcript.resolve()),
            "last_byte_offset": 0,
            "cumulative": {
                "input_tokens": 0, "output_tokens": 0,
                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
                "total_requests": 0,
            },
            "rounds": [],
        }

    # If label is "startup_end", compute the startup delta from last checkpoint
    if label == "startup_end" and not cp.get("startup_cost"):
        prev_offset = cp.get("last_byte_offset", 0)
        startup_entries = read_usage_since(cp["transcript_path"], prev_offset)
        startup_delta = compute_delta(startup_entries)
        if startup_delta["request_count"] > 0:
            cp["startup_cost"] = {
                "input_tokens": startup_delta["input_tokens"],
                "output_tokens": startup_delta["output_tokens"],
                "cache_read": startup_delta["cache_read"],
                "cache_hit_pct": startup_delta["cache_hit_pct"],
            }
            # Startup cost IS part of cumulative
            cum = cp["cumulative"]
            cum["input_tokens"] += startup_delta["input_tokens"]
            cum["output_tokens"] += startup_delta["output_tokens"]
            cum["cache_read_input_tokens"] += startup_delta["cache_read"]
            cum["cache_creation_input_tokens"] += startup_delta["cache_creation"]
            cum["total_requests"] += startup_delta["request_count"]

    # If delta provided, update cumulative and append round entry
    if delta and delta.get("request_count", 0) > 0:
        cum = cp["cumulative"]
        cum["input_tokens"] += delta["input_tokens"]
        cum["output_tokens"] += delta["output_tokens"]
        cum["cache_read_input_tokens"] += delta["cache_read"]
        cum["cache_creation_input_tokens"] += delta["cache_creation"]
        cum["total_requests"] += delta["request_count"]

        next_idx = len(cp["rounds"]) + 1
        cp["rounds"].append({
            "index": next_idx,
            "label": label or "round",
            "input": delta["input_tokens"],
            "output": delta["output_tokens"],
            "cache_read": delta["cache_read"],
            "cache_hit_pct": delta["cache_hit_pct"],
        })

    # Only advance byte_offset when we consumed actual new transcript data.
    # Otherwise (delta=0) the checkpoint stays where it is so the next
    # round_prepare / round_deliver can capture the accumulated usage.
    # startup_end is a special case: it has a real startup_delta computed
    # internally (stored in startup_cost), so the offset must advance.
    has_real_data = (delta and delta.get("request_count", 0) > 0)
    consumed_startup = (label == "startup_end" and cp.get("startup_cost"))
    if has_real_data or consumed_startup:
        cp["last_byte_offset"] = new_offset
    _write_checkpoint(card_folder, cp)


def compute_startup_cost(card_folder):
    """If a previous_checkpoint exists, compute the startup cost delta
    from that checkpoint to now. Called by round_deliver on first round.

    Reads all usage since the previous checkpoint's offset (which was 0
    for the new session), computes delta, stores as startup_cost.
    """
    cp = load_checkpoint(card_folder)
    prev = cp.get("previous_checkpoint")
    if not prev:
        return None

    transcript_path = cp.get("transcript_path", "")
    if not transcript_path:
        return None

    entries = read_usage_since(transcript_path, 0)
    delta = compute_delta(entries)

    cp["startup_cost"] = {
        "input_tokens": delta["input_tokens"],
        "output_tokens": delta["output_tokens"],
        "cache_read": delta["cache_read"],
        "cache_hit_pct": delta["cache_hit_pct"],
    }
    # Remove previous_checkpoint — startup cost computed, no longer needed
    cp.pop("previous_checkpoint", None)
    _write_checkpoint(card_folder, cp)

    return delta


def format_token_block(delta, cumulative, startup_cost=None):
    """Format the <tokens> block for response.txt.

    Args:
        delta: dict from compute_delta() — this round's usage
        cumulative: dict from checkpoint["cumulative"] — running totals
        startup_cost: optional dict from checkpoint["startup_cost"] — one-time import/setup cost
    """
    lines = [
        f"<tokens>",
        f"round_in: {delta['input_tokens']}",
        f"round_out: {delta['output_tokens']}",
        f"round_total: {delta['input_tokens'] + delta['output_tokens']}",
        f"cache_read: {delta['cache_read']}",
        f"cache_hit: {delta['cache_hit_pct']}%",
    ]
    if startup_cost:
        st_in = startup_cost.get("input_tokens", 0)
        st_out = startup_cost.get("output_tokens", 0)
        if st_in > 0 or st_out > 0:
            lines.append(f"startup_in: {st_in}")
            lines.append(f"startup_out: {st_out}")
            lines.append(f"startup_total: {st_in + st_out}")
    lines.extend([
        f"cumulative_in: {cumulative.get('input_tokens', 0)}",
        f"cumulative_out: {cumulative.get('output_tokens', 0)}",
        f"cumulative_total: {cumulative.get('input_tokens', 0) + cumulative.get('output_tokens', 0)}",
        f"</tokens>",
    ])
    return "\n".join(lines) + "\n"


def _write_checkpoint(card_folder, data):
    """Write checkpoint dict to .token_checkpoint.json."""
    cp_path = Path(card_folder) / ".token_checkpoint.json"
    # Ensure path components are serializable
    for key in ("transcript_path",):
        if key in data and isinstance(data[key], Path):
            data[key] = str(data[key])
    cp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── CLI: standalone stats dump ─────────────────────────────

if __name__ == "__main__":
    card_folder = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    cp = load_checkpoint(card_folder)
    transcript = locate_transcript()

    print(json.dumps({
        "transcript": str(transcript) if transcript else None,
        "checkpoint": cp if cp else "(none)",
    }, ensure_ascii=False, indent=2))
