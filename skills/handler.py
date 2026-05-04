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

from mvu_engine import extract_commands, execute_commands, compute_current_variables, audit_variables, validate_command, generate_schema, SchemaNode

STYLES = Path(__file__).parent / "styles"
BRIDGE = "http://localhost:8765"


# ═══ Tag Parsing ═══

def parse_response(text):
    """Parse response.txt into structured parts."""
    result = {}
    for tag in ("polished_input", "content", "summary", "options", "tokens"):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
        if m:
            raw = m.group(1).strip()
            if tag == "tokens":
                result[tag] = _parse_tokens(raw)
            else:
                result[tag] = raw
    return result


def _parse_tokens(raw):
    """Parse <tokens> block: 'key: value' lines → dict.
    Handles int, float, and percentage (77.4%) values."""
    tokens = {}
    for line in raw.split("\n"):
        line = line.strip()
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip()
            key = k.strip()
            # Try int
            try:
                tokens[key] = int(v)
                continue
            except ValueError:
                pass
            # Try float (includes percentage like "77.4%")
            try:
                v_clean = v.replace("%", "")
                tokens[key] = float(v_clean)
                continue
            except ValueError:
                pass
    return tokens


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
    if not path.exists():
        return (
            'window.STATE = {\n'
            '  world: "", stage: "开局", time: "", location: "", env: "",\n'
            '  quest: "", generatedCount: 0, totalTokens: 0, actions: [],\n'
            '  player: "", hp: 0, hpMax: 0, mp: 0, mpMax: 0, exp: 0, expMax: 0, ed: false,\n'
            '  npcs: []\n'
            '};\n'
        )
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_state(js, card_folder=None):
    path = STYLES / "state.js"
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)
    if card_folder:
        card_js_path = Path(card_folder) / "state.js"
        with open(card_js_path, "w", encoding="utf-8") as f:
            f.write(js)


def _get_latest_variables(log):
    """Extract current stat_data from the most recent turn that has variables."""
    for turn in reversed(log):
        variables = turn.get("variables")
        if variables and "stat_data" in variables:
            return variables["stat_data"]
    return {}


def _get_latest_delta(log):
    """Extract delta from the most recent turn."""
    if log:
        variables = log[-1].get("variables")
        if variables and "delta" in variables:
            return variables["delta"]
    return {}


def _get_turn_variables(log):
    """Return per-turn variable snapshots for inline card rendering.
    Returns [{index, stat_data, delta}, ...] for every turn.
    """
    result = []
    for turn in log:
        entry = {"index": turn.get("index", 0)}
        variables = turn.get("variables")
        if variables:
            entry["stat_data"] = variables.get("stat_data", {})
            entry["delta"] = variables.get("delta", {})
        else:
            entry["stat_data"] = {}
            entry["delta"] = {}
        result.append(entry)
    return result


def resolve_macros(text, stat_data):
    """Replace {{getvar::path}} and {{formatvar::path}} macros with variable values.

    {{getvar::玩家.姓名}}   → renders the scalar value directly
    {{formatvar::互动对象}}  → renders nested dict as indented YAML/JSON block
    """
    import re as _re

    def _resolve(path_str):
        keys = path_str.split(".")
        current = stat_data
        for k in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(k)
        return current

    def _format_val(v):
        if v is None:
            return "(未定义)"
        if isinstance(v, (int, float, bool, str)):
            return str(v)
        if isinstance(v, (dict, list)):
            try:
                import yaml
                return yaml.dump(v, allow_unicode=True, default_flow_style=False).strip()
            except ImportError:
                return json.dumps(v, ensure_ascii=False, indent=2)
        return str(v)

    # {{getvar::path}}
    text = _re.sub(
        r"\{\{getvar::([^}]+)\}\}",
        lambda m: _format_val(_resolve(m.group(1).strip())),
        text,
    )

    # {{formatvar::path}}
    text = _re.sub(
        r"\{\{formatvar::([^}]+)\}\}",
        lambda m: _format_val(_resolve(m.group(1).strip())),
        text,
    )

    # {{format_message_variable::stat_data.XXX}} — SillyTavern macro for beautify panel
    text = _re.sub(
        r"\{\{format_message_variable::stat_data\.([^}]+)\}\}",
        lambda m: _format_val(_resolve(m.group(1).strip())),
        text,
    )

    # {{format_message_variable::XXX}} without stat_data prefix (resolve from root)
    text = _re.sub(
        r"\{\{format_message_variable::([^}]+)\}\}",
        lambda m: _format_val(_resolve(m.group(1).strip())),
        text,
    )

    return text


def _stat_color(name):
    """Map stat names to bar colors."""
    n = name.lower()
    if '悔恨' in n: return '#b0624a'
    if '情欲' in n or '情慾' in n: return '#d4948a'
    if '屈从' in n or '屈從' in n: return '#c49a56'
    if '献身' in n or '獻身' in n: return '#9a7aaa'
    if 'hp' in n or '血' in n: return '#b0624a'
    if 'mp' in n or '魔' in n or '蓝' in n: return '#5a8a9a'
    if 'exp' in n or '经验' in n: return '#cc9a56'
    return '#5a7a5a'


def _stat_max_guess(val):
    """Guess a sensible max for a stat value to normalize bar width."""
    if val <= 10: return 10
    if val <= 50: return 50
    if val <= 100: return 100
    mag = 10 ** (len(str(int(val))) - 1)
    import math
    return int(math.ceil(val / mag) * mag)


def _render_stat_bar(label, val, max_val=None):
    """Render a single stat bar as inline HTML."""
    if max_val is None:
        max_val = _stat_max_guess(val)
    pct = min(100, round(val / max_val * 100))
    color = _stat_color(label)
    return (
        '<div class="tv-stat-row">'
        '<span class="tv-stat-label">' + label + '</span>'
        '<div class="tv-stat-bar-bg"><div class="tv-stat-bar-fill" style="width:'
        + str(pct) + '%;background:' + color + '"></div></div>'
        '<span class="tv-stat-value">' + str(val) + '</span>'
        '</div>'
    )


def _html_escape(text):
    """Minimal HTML escaping."""
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def _build_beautify_panel(stat_data, delta, beautify_data):
    """Build the full inline beautify panel HTML from latest variables.

    Returns a complete HTML string to be appended after all turn-wrap divs.
    Supports phone_data from tavern_helper for rich theme rendering
    (avatars, backgrounds, fonts, user profile).
    """
    if not stat_data:
        return ''

    bd = beautify_data or {}
    phone = bd.get('phone_data', {})
    panel_title = bd.get('panel_title', '') or phone.get('user', {}).get('name', '') or ''
    user_name = bd.get('user_name', '') or phone.get('user', {}).get('name', '')
    user_avatar = bd.get('user_avatar', '') or phone.get('user', {}).get('avatar', '')
    panel_bg = bd.get('panel_bg', '') or phone.get('user', {}).get('phoneBg', '')
    panel_font = bd.get('panel_font', '') or phone.get('user', {}).get('font', '')
    fonts = bd.get('fonts', []) or phone.get('fonts', [])
    random_avatars = bd.get('randomAvatars', []) or phone.get('randomAvatars', [])

    # Separate world metadata from characters
    world_data = stat_data.get('世界', {})
    # Character keys — main cast (with sub-objects) come first, NPCs last
    char_keys = []
    npc_keys = []
    for k in stat_data:
        if k == '世界':
            continue
        v = stat_data[k]
        if isinstance(v, dict):
            has_subs = any(isinstance(sv, dict) for sv in v.values())
            if has_subs:
                char_keys.append(k)
            else:
                npc_keys.append(k)
    ordered_keys = char_keys + npc_keys

    # ---- Font CSS (load from phone_data fonts list) ----
    font_css = ''
    if fonts:
        for f in fonts:
            fname = f.get('name', '')
            furl = f.get('url', '')
            if furl:
                font_css += '@import url(' + _html_escape(furl) + ');\n'

    # ---- Panel background style ----
    bg_style = ''
    if panel_bg:
        bg_style = 'background-image:url(' + _html_escape(panel_bg) + ');background-size:cover;background-position:center;'

    # ---- Tabs ----
    tabs_html = ''
    all_tabs = []
    if world_data:
        all_tabs.append(('世界', '世界'))

    for i, ck in enumerate(ordered_keys):
        # Assign avatar round-robin from randomAvatars if available
        all_tabs.append((ck, ck))

    for i, (tab_id, tab_label) in enumerate(all_tabs):
        active = ' active' if i == 0 else ''
        # Avatar icon for character tabs
        avatar_html = ''
        if tab_id != '世界' and random_avatars:
            av_idx = (i - (1 if world_data else 0)) % len(random_avatars)
            avatar_html = '<span class="beautify-tab-avatar" style="background-image:url(' + _html_escape(random_avatars[av_idx]) + ')"></span>'
        tabs_html += '<button class="beautify-tab-btn' + active + '" data-tab="' + _html_escape(tab_id) + '">' + avatar_html + '<span>' + _html_escape(tab_label) + '</span></button>'

    # ---- Tab body ----
    body_html = ''

    # World tab
    if world_data:
        body_html += '<div class="beautify-tab-panel" data-tab="世界">'
        body_html += '<div class="beautify-info-grid">'
        for key in world_data:
            val = world_data[key]
            body_html += '<div class="beautify-info-card"><div class="beautify-info-label">' + _html_escape(key) + '</div><div class="beautify-info-value">' + _html_escape(str(val)) + '</div></div>'
        body_html += '</div></div>'

    # Character tabs
    for ci, ck in enumerate(ordered_keys):
        cd = stat_data[ck]
        is_npc = ck in npc_keys
        body_html += '<div class="beautify-tab-panel" data-tab="' + _html_escape(ck) + '">'

        # ---- Character card header with avatar ----
        av_idx = ci % len(random_avatars) if random_avatars else -1
        char_avatar = random_avatars[av_idx] if av_idx >= 0 else ''

        body_html += '<div class="beautify-char-card">'

        # Avatar
        if char_avatar:
            body_html += '<div class="beautify-char-avatar-wrap"><div class="beautify-char-avatar" style="background-image:url(' + _html_escape(char_avatar) + ')" onclick="zoomPortrait(this)" title="点击放大"></div></div>'

        # Info column
        body_html += '<div class="beautify-char-info">'
        body_html += '<div class="beautify-char-name">' + _html_escape(ck) + '</div>'

        # Current condition
        if cd.get('当前状况'):
            body_html += '<div class="beautify-char-condition">' + _html_escape(str(cd['当前状况'])) + '</div>'

        # Stat bars
        stat_items = [(k, v) for k, v in cd.items() if isinstance(v, (int, float))]
        if stat_items:
            body_html += '<div class="beautify-stat-bars">'
            for skey, sval in stat_items:
                body_html += _render_stat_bar(skey, sval)
            body_html += '</div>'

        # Pregnancy / stage badges
        badges_html = ''
        if cd.get('是否受孕'):
            badges_html += '<span class="beautify-badge badge-pregnant">孕</span>'
        if cd.get('当前阶段'):
            badges_html += '<span class="beautify-badge badge-stage">阶段 ' + _html_escape(str(cd['当前阶段'])) + '</span>'
        if badges_html:
            body_html += '<div class="beautify-badges">' + badges_html + '</div>'

        body_html += '</div>'  # end char-info
        body_html += '</div>'  # end char-card

        # ---- Sub-objects: 着装 + 身体状况 side by side ----
        outfit = cd.get('着装', {})
        body_stats = cd.get('身体状况', {})
        if outfit or body_stats:
            body_html += '<div class="beautify-sub-grid">'
            if outfit:
                body_html += '<div class="beautify-sub-card"><div class="beautify-sub-title">着装</div>'
                for sk, sv in outfit.items():
                    body_html += '<div class="beautify-sub-row"><span class="beautify-sub-key">' + _html_escape(sk) + '</span><span class="beautify-sub-val">' + _html_escape(str(sv)) + '</span></div>'
                body_html += '</div>'
            if body_stats:
                body_html += '<div class="beautify-sub-card"><div class="beautify-sub-title">身体</div>'
                for sk, sv in body_stats.items():
                    body_html += '<div class="beautify-sub-row"><span class="beautify-sub-key">' + _html_escape(sk) + '</span><span class="beautify-sub-val">' + _html_escape(str(sv)) + '</span></div>'
                body_html += '</div>'
            body_html += '</div>'

        # Other dict sub-objects (not 着装/身体状况)
        for key, val in cd.items():
            if isinstance(val, dict) and key not in ('着装', '身体状况'):
                body_html += '<details class="beautify-sub"><summary>' + _html_escape(key) + '</summary>'
                for sk, sv in val.items():
                    body_html += '<div class="beautify-sub-row"><span class="beautify-sub-key">' + _html_escape(sk) + '</span><span class="beautify-sub-val">' + _html_escape(str(sv)) + '</span></div>'
                body_html += '</details>'

        # Delta changes
        char_delta = {}
        for dk, dv in (delta or {}).items():
            if dk.startswith(ck + '.'):
                short_key = dk[len(ck) + 1:]
                char_delta[short_key] = dv

        if char_delta:
            body_html += '<div class="beautify-delta">'
            for dk, dv in char_delta.items():
                old_v = dv.get('old', '?') if isinstance(dv, dict) else '?'
                new_v = dv.get('new', '?') if isinstance(dv, dict) else str(dv)
                body_html += '<div class="beautify-delta-item"><span class="beautify-delta-key">' + _html_escape(dk) + '</span> <span class="beautify-delta-old">' + _html_escape(str(old_v)) + '</span> → <span class="beautify-delta-new">' + _html_escape(str(new_v)) + '</span></div>'
            body_html += '</div>'

        body_html += '</div>'  # end tab-panel

    # ---- Assemble full panel ----
    panel_html = ''

    # Font loading
    if font_css:
        panel_html += '<style>' + font_css + '</style>'

    panel_html += '<div class="beautify-panel-inline" style="' + bg_style + '">'

    # Overlay for readability when bg is set
    if panel_bg:
        panel_html += '<div class="beautify-panel-overlay">'

    panel_html += '<div class="beautify-dashboard">'

    # Header with user avatar
    panel_html += '<div class="beautify-header">'
    if user_avatar:
        panel_html += '<div class="beautify-user-avatar" style="background-image:url(' + _html_escape(user_avatar) + ')"></div>'
    panel_html += '<div class="beautify-header-text">'
    panel_html += '<span class="beautify-header-title">' + _html_escape(panel_title or '状态面板') + '</span>'
    if user_name:
        panel_html += '<span class="beautify-header-sub">' + _html_escape(user_name) + '</span>'
    panel_html += '</div></div>'

    # Tabs
    panel_html += '<div class="beautify-tabs">' + tabs_html + '</div>'

    # Tab body
    panel_html += '<div class="beautify-tab-content">' + body_html + '</div>'

    panel_html += '</div>'  # end dashboard

    if panel_bg:
        panel_html += '</div>'  # end overlay

    panel_html += '</div>'  # end panel-inline

    # Font family
    if panel_font:
        panel_html += '<style>.beautify-panel-inline .beautify-dashboard{font-family:"' + _html_escape(panel_font) + '",sans-serif;}</style>'

    # Tab switching script
    panel_html += '''<script>
(function(){
  var panel = document.querySelector('.beautify-panel-inline');
  if (!panel || panel.getAttribute('data-tab-wired')) return;
  panel.setAttribute('data-tab-wired', '1');
  var tabs = panel.querySelectorAll('.beautify-tab-btn');
  var panels = panel.querySelectorAll('.beautify-tab-panel');
  for (var i = 0; i < panels.length; i++) {
    panels[i].style.display = (i === 0) ? '' : 'none';
  }
  for (var j = 0; j < tabs.length; j++) {
    tabs[j].addEventListener('click', function(e) {
      var tabId = this.getAttribute('data-tab');
      for (var k = 0; k < tabs.length; k++) {
        tabs[k].classList.remove('active');
      }
      this.classList.add('active');
      for (var m = 0; m < panels.length; m++) {
        panels[m].style.display = (panels[m].getAttribute('data-tab') === tabId) ? '' : 'none';
      }
    });
  }
})();
</script>'''

    return panel_html


def write_content_js(card_folder):
    """Rebuild content.js from chat_log.json. Exposes TURN_TOKENS for per-turn token display."""
    log = read_chat_log(card_folder)

    html_parts = []
    turn_tokens = {}  # { "N": {"in": X, "out": Y, "total": Z}, ... }

    for turn in log:
        ai_raw = turn.get("ai", "")
        user_raw = turn.get("user", "")
        turn_idx = turn.get("index", 0)

        # Strip <options>/<summary>/<tokens> from display
        ai_display = _strip_tags(ai_raw, "options")
        ai_display = _strip_tags(ai_display, "summary")
        ai_display = _strip_tags(ai_display, "tokens")
        # Strip MVU commands (_.set / _.add / _.insert etc.) from display.
        # These are parsed by extract_commands() for variable updates; the
        # card author's regex #1 strips <UpdateVariable> blocks, but bare
        # _.set() lines are the MVU engine's own responsibility.
        ai_display = _strip_mvu_commands(ai_display)
        # Strip hardcoded text colors from inline styles (card authors
        # often bake light-theme colors that become invisible in dark mode)
        ai_display = re.sub(
            r'\bcolor\s*:\s*#[0-9a-fA-F]{3,8}\s*;?\s*',
            '', ai_display,
        )

        # Collect token data for exposure
        tokens = turn.get("tokens")
        if tokens:
            turn_tokens[str(turn_idx)] = tokens

    # Extract startup cost from turn 0 token data (persistent across rounds)
    startup_cost = {}
    if log and log[0].get("tokens"):
        t0 = log[0]["tokens"]
        st_in = t0.get("startup_in", 0) or t0.get("in", 0)
        st_out = t0.get("startup_out", 0) or t0.get("out", 0)
        st_total = t0.get("startup_total", 0) or t0.get("total", 0)
        if st_total > 0:
            startup_cost = {
                "in": st_in,
                "out": st_out,
                "total": st_total,
                "cache_hit": t0.get("cache_hit", 0),
            }

        wrap = '<div class="turn-wrap">'
        if user_raw:
            wrap += '<div class="turn-user"><div class="turn-role">你</div><div class="turn-text">' + user_raw + '</div></div>'
        wrap += '<div class="turn-ai"><div class="turn-role">叙事</div><div class="turn-text">' + ai_display + '</div></div>'
        wrap += '</div>'
        html_parts.append(wrap)

    content_html = "".join(html_parts)

    # Load card-specific beautify data if available
    beautify_data = {}
    beautify_path = Path(card_folder) / ".beautify.json"
    if beautify_path.exists():
        try:
            with open(beautify_path, "r", encoding="utf-8") as f:
                beautify_data = json.load(f)
        except Exception:
            pass

    # Load card author's beautify panel template (from regex_scripts).
    # The template is provided as a separate BEAUTIFY_HTML variable so the
    # beautify panel renders independently of narrative content — opening
    # switches and name changes no longer destroy the panel DOM.
    # _st_shims.js (loaded in index.html) provides ST/MVU API shims so the
    # original author script runs unchanged.
    beautify_html = ""
    template_path = Path(card_folder) / ".beautify_template.html"
    if template_path.exists():
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template_html = f.read()
            # Strip structural document tags
            template_html = re.sub(
                r'<!doctype[^>]*>', '', template_html, flags=re.IGNORECASE,
            )
            template_html = re.sub(
                r'</?html[^>]*>', '', template_html, flags=re.IGNORECASE,
            )
            template_html = re.sub(
                r'</?head[^>]*>', '', template_html, flags=re.IGNORECASE,
            )
            template_html = re.sub(
                r'</?body[^>]*>', '', template_html, flags=re.IGNORECASE,
            )
            # <script type="module"> → <script> so it runs as classic script
            template_html = template_html.replace(
                '<script type="module">', '<script>'
            )
            # Macros ({{format_message_variable}}, {{getvar}}, etc.) are left INTACT
            # in the template — they are resolved client-side at display time
            # against window.MVU_VARIABLES, matching the real MVU pipeline where
            # the engine resolves macros dynamically on each render cycle.
            beautify_html = template_html
        except Exception:
            pass
    else:
        # No author template — use fallback inline beautify panel
        latest_vars = _get_latest_variables(log)
        latest_delta = _get_latest_delta(log)
        panel_html = _build_beautify_panel(latest_vars, latest_delta, beautify_data)
        if panel_html:
            beautify_html = panel_html

    # Strip <StatusPlaceHolderImpl/> markers from narrative content
    content_html = content_html.replace("<StatusPlaceHolderImpl/>", "")

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

    # Load card author's regex_scripts for frontend application
    regex_scripts = []
    regex_path = Path(card_folder) / ".regex_scripts.json"
    if regex_path.exists():
        try:
            with open(regex_path, "r", encoding="utf-8") as f:
                regex_scripts = json.load(f)
        except Exception:
            pass

    js = (
        "window.CONTENT_HTML = " + json.dumps(content_html, ensure_ascii=False) + ";\n"
        "window.BEAUTIFY_HTML = " + json.dumps(beautify_html, ensure_ascii=False) + ";\n"
        "window.SUMMARY_TEXT = " + json.dumps(latest_summary, ensure_ascii=False) + ";\n"
        "window.TURN_OPTIONS = " + json.dumps(options, ensure_ascii=False) + ";\n"
        "window.TURN_TOKENS = " + json.dumps(turn_tokens, ensure_ascii=False) + ";\n"
        "window.STARTUP_COST = " + json.dumps(startup_cost, ensure_ascii=False) + ";\n"
        "window.MVU_VARIABLES = " + json.dumps(_get_latest_variables(log), ensure_ascii=False) + ";\n"
        "window.MVU_DELTA = " + json.dumps(_get_latest_delta(log), ensure_ascii=False) + ";\n"
        "window.TURN_VARIABLES = " + json.dumps(_get_turn_variables(log), ensure_ascii=False) + ";\n"
        "window.BEAUTIFY_DATA = " + json.dumps(beautify_data, ensure_ascii=False) + ";\n"
        "window.REGEX_SCRIPTS = " + json.dumps(regex_scripts, ensure_ascii=False) + ";\n"
    )

    path = STYLES / "content.js"
    with open(path, "w", encoding="utf-8") as f:
        f.write(js)

    # Dual write to card folder for per-card frontend
    card_path = Path(card_folder) / "content.js"
    with open(card_path, "w", encoding="utf-8") as f:
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


def _strip_mvu_commands(text):
    """Strip MVU _.set/add/insert etc. commands and UpdateVariable/json_patch blocks.

    These are the MVU engine's responsibility — the card author's regex
    scripts handle <UpdateVariable> blocks for ST compatibility, but bare
    _.set() lines must be removed by us before the content reaches the user.
    """
    # Bare lodash-style commands: _.set('path', value);
    text = re.sub(
        r"^\s*_\.(?:set|insert|assign|remove|unset|delete|add|move)\s*\(.*?\)\s*;?\s*$",
        "",
        text,
        flags=re.MULTILINE,
    )
    # <json_patch> blocks
    text = re.sub(
        r"<json_patch>[\s\S]*?</json_patch>",
        "",
        text,
    )
    # <UpdateVariable> blocks
    text = re.sub(
        r"<UpdateVariable>[\s\S]*?</UpdateVariable>",
        "",
        text,
    )
    # Collapse consecutive blank lines
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


# ═══ Turn Operations ═══

MVU_SERVER = "http://127.0.0.1:8766"

def _mvu_post(endpoint, data=None):
    """POST to mvu_server, return parsed JSON or None on failure."""
    import urllib.request as _ur
    try:
        body = json.dumps(data or {}, ensure_ascii=False).encode("utf-8")
        req = _ur.Request(f"{MVU_SERVER}/{endpoint}", data=body,
                          headers={"Content-Type": "application/json"})
        with _ur.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _validate_commands_via_server(commands):
    """Batch validate commands via mvu_server. Returns (valid_cmds, errors)."""
    if not commands:
        return commands, []
    payload = {"commands": []}
    for cmd in commands:
        item = {"op": cmd.type}
        if cmd.args:
            item["path"] = cmd.args[0] if len(cmd.args) > 0 else None
            item["value"] = cmd.args[1] if len(cmd.args) > 1 else None
        if len(cmd.args) > 2:
            item["extra"] = cmd.args[2]
        payload["commands"].append(item)
    result = _mvu_post("validate_all", payload)
    if result is None or "results" not in result:
        return commands, []  # Server unavailable → allow all
    valid = []
    errors = []
    for i, r in enumerate(result["results"]):
        if r.get("ok"):
            valid.append(commands[i])
        else:
            errors.append({
                "command": commands[i].full_match.strip() if commands[i].full_match else str(commands[i].args),
                "error": r.get("error", "unknown"),
            })
    return valid, errors


def _get_injections_via_server(stat_data):
    """Get injection keywords from mvu_server. Returns list of dicts."""
    result = _mvu_post("inject", {"stat_data": stat_data})
    if result is None:
        return []
    keywords = result.get("keywords", [])
    return [{"keyword": kw, "section": f"## {kw}"} for kw in keywords]


def _load_var_schema(card_folder, fallback_data=None):
    """Load variable schema.

    Prefers mvu_server (real Zod schema loaded from card scripts).
    Falls back to .initvar_schema.json → generate_schema() from data.
    """
    # Try mvu_server first
    schema_meta = _mvu_post("schema")
    if schema_meta and schema_meta.get("fields"):
        return _build_schema_from_definition(schema_meta)

    # Fallback: file-based schema
    schema_path = Path(card_folder) / ".initvar_schema.json"
    if schema_path.exists():
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_raw = json.load(f)
            return _build_schema_from_definition(schema_raw)
        except Exception:
            pass

    # Last resort: generate from data
    if fallback_data is None:
        initvar_path = Path(card_folder) / ".initvar.json"
        if initvar_path.exists():
            try:
                with open(initvar_path, "r", encoding="utf-8") as f:
                    fallback_data = json.load(f)
            except Exception:
                pass
    if fallback_data:
        return generate_schema(fallback_data)
    return None


def _build_schema_from_definition(schema_def):
    """Build a SchemaNode tree from Node.js runner's schema definition."""
    fields = schema_def.get("fields", {})
    enums = schema_def.get("enums", {})
    constraints = schema_def.get("constraints", [])

    # Group field paths into a tree structure
    root = {"_children": {}, "_type": "object"}

    for path, info in fields.items():
        parts = path.split(".")
        node = root
        for i, part in enumerate(parts):
            if part == "*":
                # Wildcard = key can be anything
                node["_type"] = "object"
                continue
            if part not in node["_children"]:
                node["_children"][part] = {"_children": {}, "_type": "any"}
            node = node["_children"][part]
            if i == len(parts) - 1:
                node["_type"] = info.get("type", "any")
                node["_nullable"] = info.get("nullable", True)

    # Apply enum constraints
    for enum_path, enum_values in enums.items():
        parts = enum_path.split(".")
        node = root
        for part in parts:
            if part.startswith("_"):
                # _keys / _values are metadata keys
                break
            if part == "*":
                node["_type"] = "object"
                continue
            if part not in node["_children"]:
                node["_children"][part] = {"_children": {}, "_type": "any"}
            node = node["_children"][part]

    # Convert to SchemaNode
    return _dict_to_schema_node(root)


def _dict_to_schema_node(d):
    """Recursively convert dict tree to SchemaNode."""
    node_type = d.get("_type", "any")
    properties = {}
    for k, v in d.get("_children", {}).items():
        properties[k] = _dict_to_schema_node(v)

    schema = SchemaNode(
        type=node_type,
        extensible="*" in d.get("_children", {}),
    )
    if properties:
        schema.properties = properties
    return schema


def append_turn(card_folder, polished_input=None, content="", summary="", options="", is_opening=False, tokens=None, full_text=""):
    """Append a new turn to chat_log and rebuild content.js."""
    log = read_chat_log(card_folder)
    next_index = len(log)

    # ── MVU: Compute current variables ──
    prev_vars = compute_current_variables(log)

    # ── MVU: Load variable schema for validation ──
    var_schema = _load_var_schema(card_folder, prev_vars)

    # ── MVU: Extract commands from full response text ──
    commands = extract_commands(full_text or content)
    # On first turn, try loading .initvar.json as baseline
    if not prev_vars:
        initvar_path = Path(card_folder) / ".initvar.json"
        if initvar_path.exists():
            try:
                with open(initvar_path, "r", encoding="utf-8") as f:
                    prev_vars = json.load(f)
            except Exception:
                pass

    # ── MVU: Validate commands against schema via mvu_server (real Zod) ──
    valid_commands = []
    validation_errors = []
    if commands:
        # Try server-side validation first (real Zod schema)
        valid_commands, validation_errors = _validate_commands_via_server(commands)
        # If server returned nothing (unavailable), fall back to file-based schema
        if not valid_commands and not validation_errors:
            if var_schema:
                for cmd in commands:
                    ok, err = validate_command(cmd, var_schema)
                    if ok:
                        valid_commands.append(cmd)
                    else:
                        validation_errors.append({"command": cmd.full_match.strip() if cmd.full_match else str(cmd.args), "error": err})
            else:
                valid_commands = commands
        if validation_errors:
            for ve in validation_errors:
                print(f"[handler] schema validation: {ve['error']} (command: {ve['command'][:80]})")
    else:
        valid_commands = commands

    new_vars, changes = execute_commands(prev_vars, valid_commands) if valid_commands else (prev_vars, {})
    # Attach validation errors to changes delta
    if validation_errors:
        changes["_validation_errors"] = validation_errors

    # ── Resolve template macros in content ──
    resolved_vars = new_vars if new_vars else prev_vars
    content = resolve_macros(content, resolved_vars)

    ai_text = content
    if summary:
        ai_text += "\n\n<summary>" + summary + "</summary>"
    if options:
        ai_text += "\n\n<options>\n" + options + "\n</options>"

    entry = {"index": next_index, "ai": ai_text, "summary": summary}
    if not is_opening and polished_input:
        entry["user"] = polished_input
    if tokens:
        entry["tokens"] = tokens
    # Store variables if any exist or were changed
    if new_vars:
        entry["variables"] = {"stat_data": new_vars}
        if changes:
            entry["variables"]["delta"] = changes
    # Always carry forward variables from previous turns even if unchanged
    elif prev_vars:
        entry["variables"] = {"stat_data": prev_vars}

    log.append(entry)
    write_chat_log(card_folder, log)
    write_content_js(card_folder)

    # ── Variable audit: write diff to .var_diff.json for next-turn awareness ──
    try:
        audit = audit_variables(prev_vars or {}, new_vars or {}, content)
        audit_path = Path(card_folder) / ".var_diff.json"
        with open(audit_path, "w", encoding="utf-8") as f:
            json.dump(audit, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # never block turn delivery for audit failure

    # Update state: increment generatedCount and accumulate totalTokens
    state_raw = read_state()
    new_count = (next_index + 1)
    state_raw = re.sub(r'(\s+generatedCount:\s*)\d+', rf'\g<1>{new_count}', state_raw)
    if tokens:
        turn_total = tokens.get("total") or tokens.get("round_total") or tokens.get("startup_total") or 0
        if turn_total > 0:
            # Accumulate into totalTokens
            m = re.search(r'totalTokens:\s*(\d+)', state_raw)
            prev_total = int(m.group(1)) if m else 0
            new_total = prev_total + turn_total
            state_raw = re.sub(r'(\s+totalTokens:\s*)\d+', rf'\g<1>{new_total}', state_raw)
    write_state(state_raw, card_folder)

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
    write_state(state_raw, card_folder)

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
    write_state(state_raw, card_folder)


# ═══ Injection Rules ═══

def apply_injections(card_folder):
    """Get injection keywords from mvu_server (real script execution).

    Falls back to file-based .injection_rules.json parsing.

    Returns a list of dicts: [{keyword, source_path, one_liner, section}, ...]
    Prints JSON to stdout for consumption by Cron prompt.
    """
    import re as _re

    # Get current variables from chat_log
    log = read_chat_log(card_folder)
    stat_data = {}
    for turn in reversed(log):
        v = turn.get("variables")
        if v and "stat_data" in v:
            stat_data = v["stat_data"]
            break

    # Try mvu_server first (real keyword script execution)
    server_keywords = _get_injections_via_server(stat_data)
    if server_keywords:
        # Load worldbook index for one_liner enrichment
        index_path = Path(card_folder) / "memory" / ".worldbook_index.json"
        worldbook_index = {}
        if index_path.exists():
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    for entry in json.load(f):
                        worldbook_index[entry.get("keyword", "")] = entry
            except Exception:
                pass
        for kw in server_keywords:
            entry = worldbook_index.get(kw["keyword"], {})
            kw["one_liner"] = entry.get("one_liner", "")
            kw["section"] = entry.get("section", kw["section"])
        print(json.dumps(server_keywords, ensure_ascii=False))
        return server_keywords

    # Fallback: file-based rules
    rules_path = Path(card_folder) / ".injection_rules.json"
    if not rules_path.exists():
        print(json.dumps([]))
        return []

    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = json.load(f)
    except Exception:
        print(json.dumps([]))
        return []

    if not rules:
        print(json.dumps([]))
        return []

    # Load worldbook index
    index_path = Path(card_folder) / "memory" / ".worldbook_index.json"
    worldbook_index = {}
    if index_path.exists():
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                for entry in json.load(f):
                    worldbook_index[entry.get("keyword", "")] = entry
        except Exception:
            pass

    results = []
    seen = set()

    for rule in rules:
        source_path = rule.get("source_path", "")
        split_pattern = rule.get("split_pattern", "[、,，\\n]")
        prefix = rule.get("prefix", "")

        value = _lodash_get(stat_data, source_path)
        if not value or not isinstance(value, str) or not value.strip():
            continue

        split_re = split_pattern
        if split_re.startswith("/") and split_re.rfind("/") > 0:
            last_slash = split_re.rfind("/")
            split_re = split_re[1:last_slash]
        try:
            keywords = _re.split(split_re, value)
        except _re.error:
            keywords = value.replace("、", ",").replace("，", ",").split(",")

        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            if prefix and not kw.startswith(prefix):
                kw = prefix + kw
            if kw in seen:
                continue
            seen.add(kw)
            entry = worldbook_index.get(kw, {})
            results.append({
                "keyword": kw,
                "source_path": source_path,
                "one_liner": entry.get("one_liner", ""),
                "section": entry.get("section", f"## {kw}"),
            })

    print(json.dumps(results, ensure_ascii=False))
    return results


def _lodash_get(obj, path_str):
    """Resolve dot-separated path like '世界设定.性癖' from nested dict."""
    if not obj or not path_str:
        return None
    keys = path_str.split(".")
    current = obj
    for k in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(k)
        if current is None:
            return None
    return current


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

    # Only allow switching the opening (index 0 must be AI-only, no user input)
    if log[0].get("user"):
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

    log[0]["ai"] = "<content>\n" + greeting + "\n</content>\n\n<summary>" + log[0].get("summary", "") + "</summary>\n\n<options>\n" + opts_block + "\n</options>"

    # Apply per-opening variable state if the opening defines one.
    # This matches real MVU behaviour where alternate greetings embed
    # <UpdateVariable> blocks to override [InitVar] baseline values.
    opening_vars = target.get("variables")
    if opening_vars:
        if "variables" not in log[0] or not log[0]["variables"]:
            log[0]["variables"] = {}
        log[0]["variables"]["stat_data"] = opening_vars
        log[0]["variables"]["delta"] = {}

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
        print("Usage: python handler.py <card_folder> [--opening|--injections]")
        sys.exit(1)

    card_folder = sys.argv[1]

    if "--injections" in sys.argv:
        result = apply_injections(card_folder)
        if result:
            print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

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
    tokens = parts.get("tokens", None)

    # ── Opening: compute startup cost BEFORE append_turn so turn 0 has token stats ──
    if is_opening and not tokens:
        try:
            from token_stats import save_checkpoint, load_checkpoint
            save_checkpoint(card_folder, label="startup_end")
            cp = load_checkpoint(card_folder)
            startup_cost = cp.get("startup_cost", {})
            st_in = startup_cost.get("input_tokens", 0)
            st_out = startup_cost.get("output_tokens", 0)
            if st_in > 0 or st_out > 0:
                tokens = {
                    "in": st_in,
                    "out": st_out,
                    "total": st_in + st_out,
                    "cache_read": startup_cost.get("cache_read", 0),
                    "cache_hit": startup_cost.get("cache_hit_pct", 0.0),
                    "is_startup": True,
                }
        except Exception:
            pass

    idx = append_turn(
        card_folder,
        polished_input=polished_input if not is_opening else None,
        content=content,
        summary=summary,
        options=options,
        is_opening=is_opening,
        tokens=tokens,
        full_text=response_text,
    )

    # Clean up
    resp_path.unlink(missing_ok=True)
    bridge_done()

    print(f"[handler] Turn {idx} saved. content.js rebuilt.")
