#!/usr/bin/env python3
"""
import_prepare.py — 导入/启动预处理管线。

统一完成启动阶段所有机械操作:
  1. 清理残留 Python 进程
  2. 解析角色卡数据 (代理 import_card.run_import)
  3. 初始化 session 文件 (.card_path, state.js, content.js, chat_log.json)
  4. 预填 response.txt (卡片 first_mes)
  5. 写入 import_context.txt (启动阶段汇总上下文)
  6. 输出 JSON 摘要到 stdout

替代 CLAUDE.md「自动启动流程」中的步骤 0/2/4/4.5/5/6 机械操作。

用法:
  python import_prepare.py <卡片文件夹> <ROOT>
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Both files live in skills/, so direct import works (same as server.py imports handler).
# import_card.run_import() has no stdout side effects after refactoring.
from import_card import run_import


def read_json(path):
    """Safe JSON file read, returns None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ─── Phase 0: Cleanup ────────────────────────────────────────

def cleanup_residual(styles_dir: Path) -> dict:
    """Kill stale Python processes running skills/ scripts.

    Uses PowerShell to identify and kill processes whose command-line
    contains '*skills*', excluding the current process (self).

    Also removes any stale .pending file from a previous session so
    the bridge server doesn't see a phantom pending event.
    """
    current_pid = os.getpid()
    killed = 0

    cmd = (
        f"Get-Process python -ErrorAction SilentlyContinue | "
        f'Where-Object {{ $_.Id -ne {current_pid} -and '
        f'$_.CommandLine -like "*skills*" }} | '
        f"Select-Object -ExpandProperty Id"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split()
            for pid_str in pids:
                try:
                    pid = int(pid_str)
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True, timeout=5
                    )
                    killed += 1
                except (ValueError, subprocess.TimeoutExpired):
                    pass
    except subprocess.TimeoutExpired:
        pass

    # Drop stale .pending
    pending = styles_dir / ".pending"
    pending_existed = pending.exists()
    if pending_existed:
        try:
            pending.unlink()
        except Exception:
            pass

    return {"killed_processes": killed, "stale_pending_cleared": pending_existed}


# ─── Phase 2: Session File Initialization ────────────────────

def write_card_path(card_folder: str, styles_dir: Path) -> str:
    """Write .card_path so server.py can find the active card folder."""
    abs_path = str(Path(card_folder).resolve())
    (styles_dir / ".card_path").write_text(abs_path, encoding="utf-8")
    return abs_path


def init_state_js(styles_dir: Path, card_name: str, world_name: str,
                  card_folder: str) -> None:
    """Write initial state.js with pre-filled world name.

    The AI can later edit state.js for more specific time/location/env/
    quest/npcs values after reading import_context.txt.

    Dual-writes to styles/ and card folder (matching handler.py pattern).
    """
    safe_world = world_name.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    js = (
        "window.STATE = {\n"
        f'  world: "{safe_world}",\n'
        '  stage: "开局",\n'
        '  time: "",\n'
        '  location: "",\n'
        '  env: "",\n'
        '  quest: "",\n'
        "  generatedCount: 0,\n"
        "  totalTokens: 0,\n"
        "  actions: [],\n"
        '  player: "", hp: 0, hpMax: 0, mp: 0, mpMax: 0, exp: 0, expMax: 0, ed: false,\n'
        "  npcs: []\n"
        "};\n"
    )

    (styles_dir / "state.js").write_text(js, encoding="utf-8")
    # Dual write to card folder
    card_state = Path(card_folder) / "state.js"
    card_state.write_text(js, encoding="utf-8")


def init_content_js(styles_dir: Path, card_folder: str) -> None:
    """Write placeholder content.js.

    handler.py's write_content_js() will rebuild this when the first
    turn is appended via handler.py --opening.
    """
    js = (
        "window.CONTENT_HTML = '<div style=\"padding:60px;text-align:center;color:#999;\">正在生成开场...</div>';\n"
        "window.BEAUTIFY_HTML = '';\n"
        "window.SUMMARY_TEXT = '';\n"
        "window.TURN_OPTIONS = [];\n"
        "window.TURN_TOKENS = {};\n"
        "window.MVU_VARIABLES = {};\n"
        "window.MVU_DELTA = {};\n"
        "window.TURN_VARIABLES = [];\n"
        "window.BEAUTIFY_DATA = {};\n"
        "window.REGEX_SCRIPTS = [];\n"
    )
    (styles_dir / "content.js").write_text(js, encoding="utf-8")
    card_content = Path(card_folder) / "content.js"
    card_content.write_text(js, encoding="utf-8")


def init_chat_log(card_folder: str) -> bool:
    """Initialize chat_log.json as empty array if not exists.

    Returns True if created, False if it already existed (re-import).
    """
    path = Path(card_folder) / "chat_log.json"
    if not path.exists():
        path.write_text("[]", encoding="utf-8")
        return True
    return False


# ─── Phase 3: Import Context File ────────────────────────────

def _walk_vars(obj, prefix=""):
    """Recursively list all leaf paths with values for context display."""
    lines = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            lines.extend(_walk_vars(v, f"{prefix}/{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            lines.extend(_walk_vars(v, f"{prefix}/{i}"))
    else:
        val_str = json.dumps(obj, ensure_ascii=False)
        if len(val_str) > 80:
            val_str = val_str[:80] + "..."
        lines.append(f"  {prefix} = {val_str}")
    return lines


def build_import_context(card_folder: str, styles_dir: Path,
                         import_result: dict) -> tuple:
    """Write import_context.txt — consolidated startup context for the AI.

    Analogous to round_context.txt in the per-round pipeline.  Groups all
    the information the AI currently reads from 8+ separate files into
    one structured document.

    Returns (Path, size_in_bytes).
    """
    card_path = Path(card_folder)
    parts = []

    # ── CARD_INFO ──
    card_name = import_result.get("card_name", "") or "(unknown)"
    world_name = import_result.get("world_name", "") or "(unknown)"
    source_type = import_result.get("source_type", "?")
    source_file = import_result.get("source_file", "")

    parts.append("=== CARD_INFO ===")
    parts.append(f"  Name: {card_name}")
    parts.append(f"  World: {world_name}")
    parts.append(f"  Source: {source_type}")
    if source_file:
        parts.append(f"  File: {source_file}")
    if import_result.get("merged_worldbooks"):
        mw = import_result["merged_worldbooks"]
        parts.append(f"  Merged worldbooks: {mw['files']} files, {mw['entries']} extra entries")
    parts.append("")

    # ── MEMORY_FILES ──
    memory_dir = card_path / "memory"
    parts.append("=== MEMORY_FILES ===")
    if memory_dir.exists():
        for fname in sorted(memory_dir.iterdir()):
            if fname.suffix == ".md" and fname.name != "MEMORY.md":
                desc = ""
                try:
                    content = fname.read_text(encoding="utf-8")
                    for line in content.split("\n"):
                        if line.startswith("description:"):
                            desc = " — " + line.split(":", 1)[1].strip()
                            break
                except Exception:
                    pass
                parts.append(f"  {fname.name}{desc}")
            elif fname.suffix == ".json" and fname.name.startswith("."):
                size = fname.stat().st_size
                parts.append(f"  {fname.name} ({size} bytes)")
    else:
        parts.append("  (no memory directory)")
    parts.append("")

    # ── WORLDBOOK_INDEX ──
    wb_index = read_json(card_path / "memory" / ".worldbook_index.json")
    if wb_index:
        parts.append(f"=== WORLDBOOK_INDEX ({len(wb_index)} entries) ===")
        for entry in wb_index[:30]:
            kw = entry.get("keyword", "?")
            ol = entry.get("one_liner", "")[:80]
            parts.append(f"  [{kw}] {ol}")
        if len(wb_index) > 30:
            parts.append(f"  ... ({len(wb_index) - 30} more — Grep reference.md for details)")
    else:
        parts.append("=== WORLDBOOK_INDEX ===\n  (none)")
    parts.append("")

    # ── CARD_STRUCTURE ──
    structure = import_result.get("card_structure", {})
    if structure:
        parts.append("=== CARD_STRUCTURE ===")
        parts.append(f"  has_stages: {structure.get('has_stages', False)}")
        parts.append(f"  has_events: {structure.get('has_events', False)}")
        chars = structure.get("characters", {})
        if chars:
            parts.append(f"  characters ({len(chars)}): {', '.join(chars.keys())}")
    else:
        parts.append("=== CARD_STRUCTURE ===\n  (none)")
    parts.append("")

    # ── INITIAL_VARIABLES ──
    initvar = read_json(card_path / ".initvar.json")
    if initvar:
        parts.append("=== INITIAL_VARIABLES ===")
        var_lines = _walk_vars(initvar)
        if var_lines:
            for line in var_lines:
                parts.append(line)
        else:
            parts.append("  (empty)")
    else:
        parts.append("=== INITIAL_VARIABLES ===\n  (none)")
    parts.append("")

    # ── INJECTION_RULES ── (if present)
    injections = read_json(card_path / ".injection_rules.json")
    if injections:
        parts.append(f"=== INJECTION_RULES ({len(injections)} rules) ===")
        for inj in injections[:10]:
            src = inj.get("source_path", "?")
            pattern = inj.get("split_pattern", "")
            parts.append(f"  {src} -> split={pattern[:40]}")
    parts.append("")

    # ── OPENINGS ──
    openings_count = import_result.get("openings_count", 0)
    parts.append(f"=== OPENINGS ({openings_count} available) ===")
    if openings_count > 0:
        openings = read_json(styles_dir / "openings.json")
        if openings:
            for i, o in enumerate(openings):
                label = o.get("label", "")[:60]
                content_preview = o.get("content", "")[:150]
                parts.append(f"  [{o.get('id', i)}] {label}")
                if i == 0:
                    parts.append(f"       Preview: {content_preview}...")
                    parts.append(f"       (this is the active opening — pre-filled in response.txt)")
    parts.append("")

    # ── SESSION_STATE ──
    parts.append("=== SESSION_STATE ===")
    parts.append(f"  .card_path: written")
    parts.append(f"  state.js: world=\"{world_name}\"")
    parts.append(f"  content.js: placeholder")
    parts.append(f"  chat_log.json: {'created (new)' if import_result.get('chat_log_created') else 'already exists (preserved)'}")
    parts.append(f"  response.txt: {'pre-filled from first_mes' if import_result.get('response_txt_written') else '(empty — AI must generate opening)'}")
    parts.append(f"  .session_init: created")
    parts.append(f"  .initvar.json: {'present' if import_result.get('initvar_keys') else '(none)'}")
    parts.append(f"  .beautify.json: {'present' if import_result.get('beautify_keys') else '(none)'}")
    parts.append(f"  .regex_scripts.json: {'present' if import_result.get('regex_scripts') else '(none)'}")
    parts.append(f"  .injection_rules.json: {'present' if import_result.get('injection_rules') else '(none)'}")
    parts.append("")

    parts.append("=== NEXT_STEPS ===")
    parts.append("  1. Read this file for full startup context")
    parts.append("  2. (Optional) Edit state.js: set time/location/env/quest/npcs")
    parts.append("  3. If response.txt is empty: generate opening narrative → write response.txt")
    parts.append("  4. Deliver opening: python handler.py <card_folder> --opening")
    parts.append("  5. ScheduleWakeup to start input monitoring loop")

    # Write
    output_path = styles_dir / "import_context.txt"
    output_text = "\n".join(parts)
    output_path.write_text(output_text, encoding="utf-8")
    return output_path, len(output_text.encode("utf-8"))


# ─── Main Pipeline ──────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print(json.dumps({
            "ok": False, "action": "error",
            "error": "Usage: python import_prepare.py <card_folder> <ROOT>"
        }, ensure_ascii=False))
        sys.exit(1)

    card_folder = sys.argv[1]
    root = sys.argv[2]
    styles_dir = Path(root) / "skills" / "styles"
    os.makedirs(styles_dir, exist_ok=True)

    # ══ Phase 0: Cleanup ══
    cleanup_info = cleanup_residual(styles_dir)

    # ══ Phase 1: Card Import ══
    import_result = run_import(card_folder, root)

    card_name = import_result.get("card_name", "")
    world_name = import_result.get("world_name", "")

    # ══ Phase 2: Session Initialization ══
    card_path_abs = write_card_path(card_folder, styles_dir)
    init_state_js(styles_dir, card_name, world_name, card_folder)
    init_content_js(styles_dir, card_folder)
    chat_log_created = init_chat_log(card_folder)

    # Pass chat_log status through to context builder
    import_result["chat_log_created"] = chat_log_created

    # ══ Phase 3: Import Context File ══
    context_path, context_size = build_import_context(
        card_folder, styles_dir, import_result
    )

    # ══ Phase 3.5: Token Checkpoint Init ══
    # Write initial checkpoint so round_deliver can compute deltas.
    # load_checkpoint handles cross-session transcript switching automatically.
    try:
        import token_stats
        token_stats.save_checkpoint(card_folder)  # no delta — just record baseline offset
    except Exception:
        pass

    # ══ Phase 4: JSON Summary ══
    summary = {
        "ok": True,
        "action": "imported" if import_result.get("status") == "ok" else "partial",
        "card_dir": card_folder,
        "card_name": card_name,
        "world_name": world_name,
        "source_type": import_result.get("source_type", ""),
        "files_written": {
            "card_path": str(styles_dir / ".card_path"),
            "state_js": str(styles_dir / "state.js"),
            "content_js": str(styles_dir / "content.js"),
            "chat_log_created": chat_log_created,
            "import_context": str(context_path),
            "import_context_size": context_size,
            "response_txt_prefilled": import_result.get("response_txt_written", False),
            "openings_json": import_result.get("openings_count", 0) > 0,
            "session_init": import_result.get("session_init", False),
        },
        "openings_count": import_result.get("openings_count", 0),
        "worldbook_entries": import_result.get("worldbook_entries_total", 0),
        "memory": import_result.get("memory", {}),
        "initvar_keys": import_result.get("initvar_keys", []),
        "initvar_source": import_result.get("initvar_source", ""),
        "card_structure": {
            "has_stages": import_result.get("card_structure", {}).get("has_stages", False),
            "has_events": import_result.get("card_structure", {}).get("has_events", False),
            "character_count": len(import_result.get("card_structure", {}).get("characters", {})),
        },
        "cleanup": cleanup_info,
    }

    # Carry forward optional detail keys from import_card
    for key in ["regex_scripts", "beautify_keys", "injection_rules",
                 "schema_fields", "merged_worldbooks"]:
        if key in import_result:
            summary[key] = import_result[key]

    # Cards with no detectable data
    if import_result.get("status") == "no_card_found":
        summary.update({
            "ok": True,
            "action": "no_card_data",
            "warning": "No recognizable card data found (no PNG/JSON/TXT with card format)",
            "files_scanned": import_result.get("files_scanned", {}),
        })

    # Output (with Windows encoding safety)
    try:
        output_str = json.dumps(summary, ensure_ascii=False, indent=2)
        sys.stdout.reconfigure(encoding='utf-8')
        print(output_str)
    except (UnicodeEncodeError, AttributeError):
        print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
