"""
RP Response Handler — parses Claude Code output and manages chat_log / content.js / state.js.
Also provides reroll and delete-turn logic for the bridge server.
Usage:
  python handler.py <card_folder>          # process response.txt → append turn
  python handler.py <card_folder> --opening # first turn, no user input
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

STYLES = Path(__file__).parent / "styles"
BRIDGE = "http://localhost:8765"
IMG_RE = re.compile(r'\[img:\s*(.+?)\]')


# ═══ Tag Parsing ═══

def parse_response(text):
    """Parse response.txt into structured parts. Returns dict with optional image_prompts."""
    result = {}
    for tag in ("polished_input", "content", "summary", "options"):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
        if m:
            result[tag] = m.group(1).strip()

    # Extract [img: ...] from content
    content_text = result.get("content", text)
    image_prompts = []
    for m in IMG_RE.finditer(content_text):
        image_prompts.append({"tags": m.group(1).strip(), "img_url": None})
    result["image_prompts"] = image_prompts

    return result


# ═══ File I/O ═══

def read_chat_log(card_folder):
    path = Path(card_folder) / "chat_log.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def write_chat_log(card_folder, log):
    path = Path(card_folder) / "chat_log.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def read_state():
    path = STYLES / "state.js"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_state(js):
    path = STYLES / "state.js"
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)


def write_content_js(card_folder):
    """Rebuild content.js from chat_log.json. Strips [img:...] from display,
    injects generation buttons, and exposes TURN_IMAGES for persisted images."""
    log = read_chat_log(card_folder)

    html_parts = []
    turn_images = {}  # { "turn_seg": "url" }

    for turn in log:
        ai_raw = turn.get("ai", "")
        user_raw = turn.get("user", "")
        turn_idx = turn.get("index", 0)
        image_prompts = turn.get("image_prompts", [])

        # First strip <options>/<summary> tags
        ai_display = _strip_tags(ai_raw, "options")
        ai_display = _strip_tags(ai_display, "summary")

        # Replace [img: ...] with generation buttons / images
        seg_counter = [0]  # mutable counter for closure

        def replace_img_tag(m):
            idx = seg_counter[0]
            seg_counter[0] += 1
            tags = m.group(1).strip()
            key = f"{turn_idx}_{idx}"

            # Check if image already generated
            img_url = None
            if idx < len(image_prompts):
                img_url = image_prompts[idx].get("img_url", None)

            if img_url:
                turn_images[key] = img_url
                return f'<img src="{img_url}" class="gen-img" data-turn="{turn_idx}" data-seg="{idx}" alt="{_escape_attr(tags[:60])}" title="{_escape_attr(tags)}" loading="lazy">'
            else:
                return (
                    f'<span class="img-gen-btn auto" data-turn="{turn_idx}" data-seg="{idx}" '
                    f'title="{_escape_attr(tags)}">🎨 生成插图</span>'
                )

        ai_display = IMG_RE.sub(replace_img_tag, ai_display)

        wrap = '<div class="turn-wrap">'
        if user_raw:
            wrap += '<div class="turn-user"><div class="turn-role">你</div><div class="turn-text">' + user_raw + '</div></div>'
        wrap += '<div class="turn-ai"><div class="turn-role">叙事</div><div class="turn-text">' + ai_display + '</div></div>'
        wrap += '</div>'
        html_parts.append(wrap)

    content_html = "".join(html_parts)
    latest_summary = log[-1].get("summary", "") if log else ""
    latest_ai = log[-1].get("ai", "") if log else ""

    # Extract options from latest AI content
    opts_match = re.search(r"<options>(.*?)</options>", latest_ai, re.DOTALL)
    options = []
    if opts_match:
        for line in opts_match.group(1).strip().split("\n"):
            line = line.strip()
            if line:
                options.append(line)

    js = (
        "window.CONTENT_HTML = " + json.dumps(content_html, ensure_ascii=False) + ";\n"
        "window.SUMMARY_TEXT = " + json.dumps(latest_summary, ensure_ascii=False) + ";\n"
        "window.TURN_OPTIONS = " + json.dumps(options, ensure_ascii=False) + ";\n"
        "window.TURN_IMAGES = " + json.dumps(turn_images, ensure_ascii=False) + ";\n"
    )

    path = STYLES / "content.js"
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)


def _escape_attr(s):
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def update_state(**kwargs):
    """Update fields in state.js. Keys: stage, time, location, env, quest, generatedCount, npcs, etc."""
    raw = read_state()
    for key, value in kwargs.items():
        if isinstance(value, str):
            raw = re.sub(rf'(\s+{key}:\s*")[^"]*(")', rf'\g<1>{value}\g<2>', raw)
        elif isinstance(value, (int, float)):
            raw = re.sub(rf'(\s+{key}:\s*)\d+', rf'\g<1>{value}', raw)
        elif isinstance(value, list):
            raw = re.sub(rf'(\s+{key}:\s*)\[.*?\]', lambda m: m.group(1) + json.dumps(value, ensure_ascii=False), raw, flags=re.DOTALL)
    write_state(raw)


def _strip_tags(text, tag):
    return re.sub(rf"<{tag}>.*?</{tag}>", "", text, flags=re.DOTALL).strip()


# ═══ Turn Operations ═══

def append_turn(card_folder, polished_input=None, content="", summary="", options="", is_opening=False, image_prompts=None):
    """Append a new turn to chat_log and rebuild content.js."""
    log = read_chat_log(card_folder)
    next_index = len(log)

    ai_text = content
    if summary:
        ai_text += "\n\n<summary>" + summary + "</summary>"
    if options:
        ai_text += "\n\n<options>\n" + options + "\n</options>"

    entry = {"index": next_index, "ai": ai_text, "summary": summary}
    if not is_opening and polished_input:
        entry["user"] = polished_input
    if image_prompts:
        entry["image_prompts"] = image_prompts

    log.append(entry)
    write_chat_log(card_folder, log)
    write_content_js(card_folder)

    # Update state: increment generatedCount
    state_raw = read_state()
    new_count = (next_index + 1)
    state_raw = re.sub(r'(\s+generatedCount:\s*)\d+', rf'\g<1>{new_count}', state_raw)
    write_state(state_raw)

    return next_index


def reroll_last(card_folder):
    """Delete last turn, restore user input for regeneration. Returns the user text."""
    log = read_chat_log(card_folder)
    if not log:
        return None

    last = log[-1]

    # Refuse to reroll an opening (no user field) — nothing to regenerate from
    if not last.get("user"):
        return None

    log.pop()
    write_chat_log(card_folder, log)
    write_content_js(card_folder)

    # Update generatedCount
    state_raw = read_state()
    new_count = len(log) + 2 if log else 1
    state_raw = re.sub(r'(\s+generatedCount:\s*)\d+', rf'\g<1>{new_count}', state_raw)
    write_state(state_raw)

    user_text = last.get("user", "")
    (STYLES / "input.txt").write_text(user_text, encoding="utf-8")
    (STYLES / ".pending").touch()
    return user_text


def delete_turns(card_folder, from_index):
    """Delete turns with index >= from_index."""
    log = read_chat_log(card_folder)
    log = [t for t in log if t.get("index", 0) < from_index]
    write_chat_log(card_folder, log)
    write_content_js(card_folder)

    # Update generatedCount and clear pending
    (STYLES / ".pending").unlink(missing_ok=True)
    state_raw = read_state()
    new_count = len(log) + 2 if log else 1
    state_raw = re.sub(r'(\s+generatedCount:\s*)\d+', rf'\g<1>{new_count}', state_raw)
    write_state(state_raw)


# ═══ Bridge Calls ═══

def bridge_done():
    try:
        urllib.request.urlopen(BRIDGE + "/api/done")
    except Exception:
        pass


# ═══ Openings Management ═══

OPENINGS_FILE = STYLES / "openings.json"


def save_openings(openings):
    """Save openings list to openings.json."""
    with open(OPENINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(openings, f, ensure_ascii=False, indent=2)


def list_openings():
    """Return list of available openings."""
    if OPENINGS_FILE.exists():
        with open(OPENINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def switch_opening(card_folder, opening_id):
    """Replace the current opening (index 0) with a different one."""
    openings = list_openings()
    target = None
    for o in openings:
        if o["id"] == opening_id:
            target = o
            break
    if not target:
        return False

    log = read_chat_log(card_folder)
    if not log:
        return False

    # Only allow switching the opening (index 0, no user field)
    if log[0].get("user") or len(log) > 1:
        return False

    # Replace opening AI content with the selected greeting
    # Convert plain-text paragraphs to <p> tags if not already HTML
    greeting = target["content"]
    if "<p>" not in greeting and "<content>" not in greeting:
        greeting = _text_to_p(greeting)

    # Use per-opening options if available, otherwise keep existing
    opts = target.get("options", "")
    if not opts:
        opts = _extract_options(log[0].get("ai", ""))
    opts_block = "\n".join('<font color="#b06a3d">' + o + '</font>' for o in opts) if isinstance(opts, list) else opts if opts else ""

    log[0]["ai"] = "<div style=\"max-width:700px; margin:auto; font-family:'SimSun','宋体',serif; line-height:2.2; font-size:14px; color:#3a3028;\">\n\n<content>\n" + greeting + "\n</content>\n\n<summary>" + log[0].get("summary", "") + "</summary>\n\n<options>\n" + opts_block + "\n</options>"

    write_chat_log(card_folder, log)
    write_content_js(card_folder)
    return True


def _text_to_p(text):
    """Convert plain text with \\r\\n\\r\\n paragraph breaks to <p>-wrapped HTML."""
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Split on double newlines (blank lines between paragraphs)
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    return "\n".join(f"<p>{p}</p>" for p in paras)


def _extract_options(ai_text):
    """Extract options block from AI text, preserving original."""
    m = re.search(r"<options>(.*?)</options>", ai_text, re.DOTALL)
    return m.group(1).strip() if m else ""


# ═══ CLI ═══

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python handler.py <card_folder> [--opening]")
        sys.exit(1)

    card_folder = sys.argv[1]
    is_opening = "--opening" in sys.argv

    # Read response.txt
    resp_path = STYLES / "response.txt"
    if not resp_path.exists():
        print("[handler] No response.txt found")
        sys.exit(1)

    response_text = resp_path.read_text(encoding="utf-8")
    parts = parse_response(response_text)

    content = parts.get("content", response_text)
    summary = parts.get("summary", "")
    options = parts.get("options", "")
    polished_input = parts.get("polished_input", "")
    image_prompts = parts.get("image_prompts", [])

    idx = append_turn(
        card_folder,
        polished_input=polished_input if not is_opening else None,
        content=content,
        summary=summary,
        options=options,
        is_opening=is_opening,
        image_prompts=image_prompts,
    )

    # Clean up
    resp_path.unlink(missing_ok=True)
    bridge_done()
    print(f"[handler] Turn {idx} saved. content.js rebuilt.")
