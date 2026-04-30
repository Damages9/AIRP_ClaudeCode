"""
MVU (MagVarUpdate) Core Engine — Pure Python port.
Parses _.set() / <json_patch> commands from AI output and executes against stat_data.

Usage:
    from mvu_engine import extract_commands, execute_commands, generate_schema
    commands = extract_commands(text)
    new_data, changes = execute_commands(stat_data, commands)
"""

import json
import re
import copy
from typing import Any, Optional, Union


# ═══ Constants ═══

COMMAND_PATTERN = r"_\.(set|insert|assign|remove|unset|delete|add|move)\("
JSON_PATCH_PATTERN = r"<(json_?patch)>\s*(?:```.*)?((?:(?!<json_?patch>)[\s\S])*?)(?:```\s*)?</\1>"
UPDATE_VARIABLE_PATTERN = r"<UpdateVariable>\s*(?:<Analysis>[\s\S]*?</Analysis>\s*)?(?:<JSONPatch>\s*(?:```.*)?([\s\S]*?)(?:```\s*)?</JSONPatch>)\s*</UpdateVariable>"


# ═══ Types (lightweight dataclass-free equivalents) ═══

class Command:
    """Parsed MVU command."""
    __slots__ = ("type", "full_match", "args", "reason")
    def __init__(self, type: str, full_match: str, args: list, reason: str = ""):
        self.type = type
        self.full_match = full_match
        self.args = args
        self.reason = reason

    def __repr__(self):
        return f"Command(type={self.type!r}, args={self.args!r}, reason={self.reason!r})"

    def to_dict(self):
        return {"type": self.type, "full_match": self.full_match, "args": self.args, "reason": self.reason}


class SchemaNode:
    """Schema node for variable validation."""
    __slots__ = ("type", "properties", "element_type", "extensible", "required", "template")
    def __init__(self, type: str, properties: dict = None, element_type: "SchemaNode" = None,
                 extensible: bool = True, required: list = None, template: Any = None):
        self.type = type
        self.properties = properties or {}
        self.element_type = element_type
        self.extensible = extensible
        self.required = required or []
        self.template = template

    def to_dict(self):
        result = {"type": self.type}
        if self.properties:
            result["properties"] = {k: v.to_dict() for k, v in self.properties.items()}
        if self.element_type:
            result["elementType"] = self.element_type.to_dict()
        if not self.extensible:
            result["extensible"] = False
        if self.required:
            result["required"] = self.required
        return result


# ═══ Path Utilities ═══

def to_path(path: str) -> list:
    """Convert dot/bracket path to list of keys. Mirrors lodash _.toPath."""
    if not path:
        return []
    parts = []
    current = ""
    in_bracket = False
    in_quote = False
    quote_char = ""
    i = 0
    while i < len(path):
        ch = path[i]
        if in_quote:
            if ch == quote_char and (i == 0 or path[i-1] != "\\"):
                in_quote = False
            else:
                current += ch
            i += 1
            continue
        if ch == "." and not in_bracket:
            if current:
                parts.append(current)
                current = ""
            i += 1
            continue
        if ch == "[":
            in_bracket = True
            if current:
                parts.append(current)
                current = ""
            i += 1
            continue
        if ch == "]":
            in_bracket = False
            val = current.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            elif val.isdigit():
                val = int(val)
            parts.append(val)
            current = ""
            i += 1
            continue
        if ch in ('"', "'") and in_bracket:
            quote_char = ch
            in_quote = True
            i += 1
            continue
        current += ch
        i += 1
    if current:
        parts.append(current)
    return parts


def path_get(data: dict, path: str, default=None):
    """Get value at dot/bracket path. path="" returns the whole data."""
    if path == "":
        return data
    parts = to_path(path)
    current = data
    for p in parts:
        if isinstance(current, dict):
            current = current.get(p, default)
        elif isinstance(current, list) and isinstance(p, int):
            if 0 <= p < len(current):
                current = current[p]
            else:
                return default
        else:
            return default
    return current


def path_set(data: dict, path: str, value):
    """Set value at dot/bracket path. path="" replaces the whole data."""
    if path == "":
        return value
    parts = to_path(path)
    current = data
    for i, p in enumerate(parts[:-1]):
        if isinstance(current, dict):
            if p not in current or not isinstance(current[p], (dict, list)):
                # Determine container type from next key
                next_p = parts[i+1]
                current[p] = [] if isinstance(next_p, int) else {}
        elif isinstance(current, list) and isinstance(p, int):
            while len(current) <= p:
                current.append({})
        current = current[p]
    last = parts[-1]
    if isinstance(current, list) and isinstance(last, int):
        while len(current) <= last:
            current.append(None)
        current[last] = value
    else:
        current[last] = value
    return data


def path_has(data: dict, path: str) -> bool:
    """Check if path exists in data."""
    if path == "":
        return True
    parts = to_path(path)
    current = data
    for p in parts:
        if isinstance(current, dict):
            if p not in current:
                return False
            current = current[p]
        elif isinstance(current, list) and isinstance(p, int):
            if p < 0 or p >= len(current):
                return False
            current = current[p]
        else:
            return False
    return True


def path_delete(data: dict, path: str):
    """Delete key at path."""
    if path == "":
        data.clear()
        return
    parts = to_path(path)
    current = data
    for p in parts[:-1]:
        if isinstance(current, dict):
            current = current[p]
        elif isinstance(current, list) and isinstance(p, int):
            current = current[p]
    last = parts[-1]
    if isinstance(current, list) and isinstance(last, int) and 0 <= last < len(current):
        current.pop(last)
    elif isinstance(current, dict) and last in current:
        del current[last]


def path_fix(path: str) -> str:
    """Normalize path: strip quotes, standardize bracket notation."""
    if not path:
        return path
    path = trim_quotes(path)
    # Rebuild path as clean dot + bracket notation
    parts = to_path(path)
    result = ""
    for p in parts:
        if isinstance(p, int):
            result += f"[{p}]"
        else:
            p_str = str(p)
            if result:
                result += "."
            # Quote keys that contain dots, brackets, or spaces
            if any(c in p_str for c in ".[] "):
                escaped = p_str.replace('"', '\\"')
                result += f'["{escaped}"]'
            else:
                result += p_str
    return result


# ═══ Value Parsing ═══

def trim_quotes(s: str) -> str:
    """Strip surrounding quotes, backslashes, and whitespace."""
    if not isinstance(s, str):
        return s
    s = s.strip()
    for q in ('"', "'", "`"):
        if len(s) >= 2 and s.startswith(q) and s.endswith(q):
            s = s[1:-1]
            break
    return s.strip()


def parse_command_value(val_str: str) -> Any:
    """Convert a string argument to a typed Python value."""
    if not isinstance(val_str, str):
        return val_str
    trimmed = val_str.strip()

    # Boolean / null / undefined
    if trimmed == "true":
        return True
    if trimmed == "false":
        return False
    if trimmed == "null" or trimmed == "None":
        return None
    if trimmed == "undefined":
        return None

    # JSON parse
    try:
        return json.loads(trimmed)
    except (json.JSONDecodeError, ValueError):
        pass

    # JS object/array literals (single-quoted keys, trailing commas, unquoted keys)
    if (trimmed.startswith("{") and trimmed.endswith("}")) or \
       (trimmed.startswith("[") and trimmed.endswith("]")):
        try:
            result = _parse_js_literal(trimmed)
            if isinstance(result, (dict, list)):
                return result
        except Exception:
            pass

    # Numeric
    try:
        if "." in trimmed or "e" in trimmed.lower():
            return float(trimmed)
        return int(trimmed)
    except (ValueError, OverflowError):
        pass

    # Math expression (safe subset)
    try:
        result = _safe_eval_math(trimmed)
        if result is not None and isinstance(result, (int, float)):
            return result
    except Exception:
        pass

    # Fallback: strip quotes and return string
    return trim_quotes(val_str)


def _parse_js_literal(s: str) -> Any:
    """Parse JavaScript-style object/array literal with relaxed syntax."""
    # Normalize: single quotes -> double quotes, unquoted keys -> quoted
    s = s.strip()
    if s.startswith("["):
        # Array: just try JSON first, then eval
        s_fixed = _fix_js_string(s)
        try:
            return json.loads(s_fixed)
        except (json.JSONDecodeError, ValueError):
            import ast
            return ast.literal_eval(s)
    if s.startswith("{"):
        s_fixed = _fix_js_object(s)
        try:
            return json.loads(s_fixed)
        except (json.JSONDecodeError, ValueError):
            import ast
            return ast.literal_eval(s_fixed)
    return s


def _fix_js_string(s: str) -> str:
    """Convert JS string to JSON-compatible: single quotes -> double quotes."""
    result = []
    in_single = False
    in_double = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\":
            result.append(ch)
            if i + 1 < len(s):
                result.append(s[i+1])
                i += 2
            else:
                i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            result.append(ch)
        elif ch == "'" and not in_double:
            in_single = not in_single
            result.append('"')
        else:
            result.append(ch)
        i += 1
    return "".join(result)


def _fix_js_object(s: str) -> str:
    """Convert JS object literal to JSON."""
    s = _fix_js_string(s)
    # Quote unquoted keys: {key: value} -> {"key": value}
    s = re.sub(r'([{,])\s*([a-zA-Z_$][\w$]*)\s*:', r'\1"\2":', s)
    return s


def _safe_eval_math(expr: str) -> Optional[Union[int, float]]:
    """Safely evaluate a math expression. Returns None if unsafe."""
    import math

    # Only allow math expressions: digits, operators, whitespace, parens, math functions
    allowed = re.compile(r'^[\d\s+\-*/().,%<>=!&|^~a-zA-Z_]+$')
    if not allowed.match(expr):
        return None

    allowed_names = {
        "abs": abs, "round": round, "min": min, "max": max, "pow": pow, "sum": sum,
        "int": int, "float": float, "str": str, "bool": bool, "len": len,
        "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "log": math.log, "log10": math.log10, "log2": math.log2,
        "exp": math.exp, "floor": math.floor, "ceil": math.ceil,
        "pi": math.pi, "e": math.e, "tau": math.tau,
        "true": True, "false": False, "null": None, "Math": math,
    }

    try:
        code = compile(expr, "<math>", "eval")
        for name in code.co_names:
            if name not in allowed_names:
                return None
        result = eval(code, {"__builtins__": {}}, allowed_names)
        if isinstance(result, (int, float)):
            if isinstance(result, float):
                return round(result, 12)
            return result
        return None
    except Exception:
        return None


# ═══ ValueWithDescription ═══

def is_value_with_description(value) -> bool:
    """Check if value is a [value, description_string] tuple."""
    return (isinstance(value, list) and len(value) == 2
            and isinstance(value[1], str) and not isinstance(value[0], (list, dict)))


# ═══ Command Extraction ═══

def extract_commands(input_text: str) -> list[Command]:
    """Extract all MVU commands from text. Supports _.set() and <json_patch> formats."""

    def _find_matching_close_paren(text: str, start: int) -> int:
        """Find matching ) starting from position after (."""
        paren_count = 1
        in_quote = False
        quote_char = ""
        i = start
        while i < len(text):
            ch = text[i]
            prev = text[i-1] if i > 0 else ""
            if ch in ('"', "'", "`") and prev != "\\":
                if not in_quote:
                    in_quote = True
                    quote_char = ch
                elif ch == quote_char:
                    in_quote = False
            if not in_quote:
                if ch == "(":
                    paren_count += 1
                elif ch == ")":
                    paren_count -= 1
                    if paren_count == 0:
                        return i
            i += 1
        return -1

    results = []

    # ── Format 1: _.set() commands ──
    i = 0
    while i < len(input_text):
        match = re.search(COMMAND_PATTERN, input_text[i:])
        if not match:
            break

        cmd_type = match.group(1)
        cmd_start = i + match.start()
        open_paren = cmd_start + len(match.group(0))

        close_paren = _find_matching_close_paren(input_text, open_paren)
        if close_paren == -1:
            i = open_paren
            continue

        end_pos = close_paren + 1
        if end_pos >= len(input_text) or input_text[end_pos] != ";":
            i = close_paren + 1
            continue
        end_pos += 1

        # Optional // comment
        comment = ""
        comment_match = re.match(r'\s*//(.*)', input_text[end_pos:])
        if comment_match:
            comment = comment_match.group(1).strip()
            end_pos += len(comment_match.group(0))

        full_match = input_text[cmd_start:end_pos]
        params_str = input_text[open_paren:close_paren]
        params = _parse_parameters(params_str)

        # Validate
        valid = False
        if cmd_type in ("set",) and len(params) >= 2:
            valid = True
        elif cmd_type in ("assign", "insert") and len(params) >= 2:
            valid = True
        elif cmd_type in ("remove", "unset", "delete") and len(params) >= 1:
            valid = True
        elif cmd_type == "add" and len(params) in (1, 2):
            valid = True
        elif cmd_type == "move" and len(params) >= 2:
            valid = True

        if valid:
            results.append((cmd_start, Command(
                type=cmd_type,
                full_match=full_match,
                args=params,
                reason=comment,
            )))

        i = end_pos

    # Strip <UpdateVariable> blocks before Format 2 to avoid double-extraction
    clean_text = re.sub(UPDATE_VARIABLE_PATTERN, "", input_text, flags=re.IGNORECASE)

    # ── Format 2: <json_patch> blocks ──
    for m in re.finditer(JSON_PATCH_PATTERN, clean_text, re.IGNORECASE):
        patch_text = m.group(2).strip()
        patch_index = m.start()
        try:
            patch = json.loads(patch_text)
        except (json.JSONDecodeError, ValueError):
            try:
                patch = _parse_js_literal(patch_text)
            except Exception:
                continue
        if not isinstance(patch, list):
            continue
        for op in patch:
            if not isinstance(op, dict):
                continue
            translated = _translate_json_patch_op(op)
            if translated:
                results.append((patch_index, translated))

    # ── Format 3: <UpdateVariable> blocks (JS-Slash-Runner / 酒馆助手 format) ──
    for m in re.finditer(UPDATE_VARIABLE_PATTERN, input_text, re.IGNORECASE):
        patch_text = m.group(1).strip()
        patch_index = m.start()
        try:
            patch = json.loads(patch_text)
        except (json.JSONDecodeError, ValueError):
            try:
                patch = _parse_js_literal(patch_text)
            except Exception:
                continue
        if not isinstance(patch, list):
            continue
        for op in patch:
            if not isinstance(op, dict):
                continue
            translated = _translate_json_patch_op(op)
            if translated:
                results.append((patch_index, translated))

    # Sort by position and return
    results.sort(key=lambda x: x[0])
    return [r[1] for r in results]


def _translate_json_patch_op(op: dict) -> Optional[Command]:
    """Translate a JSON Patch operation into a Command."""
    op_type = op.get("op", "")
    path = _json_patch_path(op.get("path", ""))
    from_path = _json_patch_path(op.get("from", ""))
    value = op.get("value")

    if op_type == "replace":
        return Command("set", json.dumps(op), [path, json.dumps(value)], "json_patch")
    elif op_type == "delta":
        return Command("add", json.dumps(op), [path, json.dumps(value)], "json_patch")
    elif op_type in ("add", "insert"):
        parts = to_path(path)
        last = parts[-1] if parts else ""
        container = ".".join(str(p) for p in parts[:-1]) if len(parts) > 1 else ""
        key_arg = str(last) if isinstance(last, int) and last >= 0 else f"'{last}'"
        return Command("insert", json.dumps(op), [container, key_arg, json.dumps(value)], "json_patch")
    elif op_type == "remove":
        return Command("delete", json.dumps(op), [path], "json_patch")
    elif op_type == "move":
        return Command("move", json.dumps(op), [from_path, path], "json_patch")
    return None


def _json_patch_path(path: str) -> str:
    """Convert JSON Pointer path (/foo/0/bar) to dot/bracket notation (foo[0].bar)."""
    if not path or not path.startswith("/"):
        return path
    segments = path[1:].split("/")
    result = ""
    for seg in segments:
        # Unescape ~1 -> /, ~0 -> ~
        seg = seg.replace("~1", "/").replace("~0", "~")
        if seg.isdigit():
            if result:
                result += f"[{seg}]"
            else:
                result = seg
        else:
            if result:
                result += f".{seg}"
            else:
                result = seg
    return result


def _parse_parameters(params_str: str) -> list[str]:
    """Split comma-separated parameters respecting nested brackets/braces/quotes."""
    params = []
    current = ""
    in_quote = False
    quote_char = ""
    bracket = brace = paren = 0

    for i, ch in enumerate(params_str):
        if ch in ('"', "'", "`") and (i == 0 or params_str[i-1] != "\\"):
            if not in_quote:
                in_quote = True
                quote_char = ch
            elif ch == quote_char:
                in_quote = False

        if not in_quote:
            if ch == "(":
                paren += 1
            elif ch == ")":
                paren -= 1
            elif ch == "[":
                bracket += 1
            elif ch == "]":
                bracket -= 1
            elif ch == "{":
                brace += 1
            elif ch == "}":
                brace -= 1

        if ch == "," and not in_quote and paren == 0 and bracket == 0 and brace == 0:
            params.append(current.strip())
            current = ""
            continue

        current += ch

    if current.strip():
        params.append(current.strip())

    return params


# ═══ Command Execution ═══

def execute_commands(stat_data: dict, commands: list[Command]) -> tuple[dict, dict]:
    """
    Execute a list of MVU commands against stat_data.
    Returns (new_stat_data, changes_dict).

    changes_dict maps path -> {"old": ..., "new": ..., "reason": str}
    """
    data = copy.deepcopy(stat_data)
    changes = {}

    # Normalize aliases
    for cmd in commands:
        if cmd.type == "remove" or cmd.type == "unset":
            cmd.type = "delete"
        elif cmd.type == "assign":
            cmd.type = "insert"

    # Normalize paths
    for cmd in commands:
        if cmd.args:
            cmd.args[0] = path_fix(trim_quotes(cmd.args[0]))
            if cmd.type == "move" and len(cmd.args) >= 2:
                cmd.args[1] = path_fix(trim_quotes(cmd.args[1]))

    for cmd in commands:
        path = cmd.args[0]
        reason_str = f" ({cmd.reason})" if cmd.reason else ""

        if cmd.type == "set":
            _exec_set(data, cmd, path, reason_str, changes)
        elif cmd.type == "insert":
            _exec_insert(data, cmd, path, reason_str, changes)
        elif cmd.type == "delete":
            _exec_delete(data, cmd, path, reason_str, changes)
        elif cmd.type == "add":
            _exec_add(data, cmd, path, reason_str, changes)
        elif cmd.type == "move":
            _exec_move(data, cmd, path, reason_str, changes)

    return data, changes


def _exec_set(data: dict, cmd: Command, path: str, reason: str, changes: dict):
    """Execute a set command. Creates intermediate paths if they don't exist."""
    new_value = parse_command_value(cmd.args[-1])
    old_value = copy.deepcopy(path_get(data, path)) if path_has(data, path) else None

    # Handle ValueWithDescription on existing value
    if is_value_with_description(old_value):
        stripped_old = old_value[0]
        if isinstance(stripped_old, (int, float)) and new_value is not None:
            old_value[0] = float(new_value) if isinstance(stripped_old, float) else int(float(new_value))
        else:
            old_value[0] = new_value
    elif isinstance(old_value, (int, float)) and new_value is not None and isinstance(new_value, str):
        try:
            new_value = float(new_value) if isinstance(old_value, float) else int(float(new_value))
        except (ValueError, OverflowError):
            pass
        if path:
            path_set(data, path, new_value)
        else:
            data.clear()
            data.update(new_value)
    else:
        if path:
            path_set(data, path, new_value)
        else:
            data.clear()
            data.update(new_value)

    final_new = path_get(data, path) if path else data
    changes[path or "(root)"] = {"old": old_value, "new": final_new, "reason": cmd.reason}


def _exec_add(data: dict, cmd: Command, path: str, reason: str, changes: dict):
    """Execute an add (numeric delta) command. Creates path with delta if it doesn't exist."""
    delta = parse_command_value(cmd.args[1]) if len(cmd.args) >= 2 else 1

    if not path_has(data, path):
        # Path doesn't exist — initialize with delta value
        path_set(data, path, delta)
        changes[path] = {"old": None, "new": delta, "reason": cmd.reason}
        return

    old_value = copy.deepcopy(path_get(data, path))
    is_vwd = is_value_with_description(old_value)
    target = old_value[0] if is_vwd else old_value

    if isinstance(target, (int, float)):
        new_target = target + delta
        if is_vwd:
            old_value[0] = new_target
        else:
            path_set(data, path, new_target)
        changes[path] = {"old": target, "new": new_target, "reason": cmd.reason}


def _exec_insert(data: dict, cmd: Command, path: str, reason: str, changes: dict):
    """Execute an insert/assign command."""
    collection = path_get(data, path) if path else data

    if collection is not None and not isinstance(collection, (dict, list)):
        return

    if len(cmd.args) == 2:
        # _.insert(path, value) — append or merge
        value = parse_command_value(cmd.args[1])
        if isinstance(collection, list):
            collection.append(value)
            changes[path] = {"old": f"[...+1]", "new": value, "reason": cmd.reason}
        elif isinstance(collection, dict) and isinstance(value, dict):
            collection.update(value)
            changes[path] = {"old": "(merged)", "new": value, "reason": cmd.reason}
        elif collection is None:
            # Create new collection
            new_coll = [value] if not isinstance(value, dict) else value
            if path:
                path_set(data, path, new_coll)
            else:
                data.clear()
                data.update(new_coll)
            changes[path or "(root)"] = {"old": None, "new": new_coll, "reason": cmd.reason}

    elif len(cmd.args) >= 3:
        # _.insert(path, key_or_index, value)
        key_or_index = parse_command_value(cmd.args[1])
        value = parse_command_value(cmd.args[2])

        if isinstance(key_or_index, str):
            key_or_index = trim_quotes(key_or_index)

        if isinstance(collection, list) and (isinstance(key_or_index, int) or key_or_index == "-"):
            idx = len(collection) if key_or_index == "-" else key_or_index
            collection.insert(idx, value)
            changes[path] = {"old": f"[...{idx}]", "new": value, "reason": cmd.reason}
        elif isinstance(collection, dict):
            k = str(key_or_index)
            collection[k] = value
            changes[path] = {"old": collection.get(k, "(new)"), "new": value, "reason": cmd.reason}
        else:
            # Create new object/array
            if isinstance(key_or_index, int) or key_or_index == "-":
                new_coll = [value]
            else:
                new_coll = {str(key_or_index): value}
            if path:
                path_set(data, path, new_coll)
            else:
                data.clear()
                data.update(new_coll)
            changes[path or "(root)"] = {"old": None, "new": new_coll, "reason": cmd.reason}


def _exec_delete(data: dict, cmd: Command, path: str, reason: str, changes: dict):
    """Execute a delete/remove command."""
    if not path_has(data, path):
        return

    if len(cmd.args) == 1:
        # _.delete(path) — delete entire path
        old_value = copy.deepcopy(path_get(data, path))
        path_delete(data, path)
        changes[path] = {"old": old_value, "new": None, "reason": cmd.reason}
    else:
        # _.delete(path, key_or_index) — delete from collection
        key_or_index = parse_command_value(cmd.args[1])
        if isinstance(key_or_index, str):
            key_or_index = trim_quotes(key_or_index)

        collection = path_get(data, path)
        if isinstance(collection, list) and isinstance(key_or_index, int):
            if 0 <= key_or_index < len(collection):
                removed = collection.pop(key_or_index)
                changes[path] = {"old": removed, "new": None, "reason": cmd.reason}
        elif isinstance(collection, dict):
            k = str(key_or_index)
            if k in collection:
                removed = collection.pop(k)
                changes[path] = {"old": {k: removed}, "new": None, "reason": cmd.reason}
        elif isinstance(collection, list) and not isinstance(key_or_index, int):
            # Remove by value
            try:
                idx = collection.index(key_or_index)
                removed = collection.pop(idx)
                changes[path] = {"old": removed, "new": None, "reason": cmd.reason}
            except ValueError:
                pass


def _exec_move(data: dict, cmd: Command, path: str, reason: str, changes: dict):
    """Execute a move command: _.move('from.path', 'to.path')."""
    if len(cmd.args) < 2:
        return
    from_path = path
    to_path = path_fix(trim_quotes(cmd.args[1]))

    if not path_has(data, from_path):
        return

    value = copy.deepcopy(path_get(data, from_path))
    path_delete(data, from_path)
    path_set(data, to_path, value)
    changes[from_path] = {"old": value, "new": f"→ {to_path}", "reason": cmd.reason}


# ═══ Schema Generation ═══

def generate_schema(data, strict_template: bool = False) -> SchemaNode:
    """Generate a SchemaNode from stat_data structure."""
    if data is None:
        return SchemaNode(type="any")

    if isinstance(data, dict):
        # Skip $meta and $internal keys
        props = {}
        for k, v in data.items():
            if k.startswith("$"):
                continue
            props[k] = generate_schema(v, strict_template)
        return SchemaNode(type="object", properties=props, extensible=True)
    elif isinstance(data, list):
        if data:
            elem_type = generate_schema(data[0], strict_template)
        else:
            elem_type = SchemaNode(type="any")
        return SchemaNode(type="array", element_type=elem_type, extensible=True)
    elif isinstance(data, bool):
        return SchemaNode(type="boolean")
    elif isinstance(data, int):
        return SchemaNode(type="number")
    elif isinstance(data, float):
        return SchemaNode(type="number")
    elif isinstance(data, str):
        return SchemaNode(type="string")
    else:
        return SchemaNode(type="any")


def validate_command(cmd: Command, schema: SchemaNode) -> tuple[bool, str]:
    """
    Validate a command against schema. Returns (valid, error_message).
    Currently checks: type compatibility for set commands, path existence.
    """
    if schema is None or cmd.type not in ("set", "add"):
        return True, ""

    path = cmd.args[0]
    if not path or path == "":
        return True, ""

    # Get target schema
    target_schema = _get_schema_for_path(schema, path)
    if target_schema is None:
        return True, ""

    if cmd.type == "set":
        new_value = parse_command_value(cmd.args[-1])
        if target_schema.type == "number" and not isinstance(new_value, (int, float)):
            return False, f"Type mismatch at '{path}': expected number, got {type(new_value).__name__}"
        if target_schema.type == "string" and not isinstance(new_value, str):
            return False, f"Type mismatch at '{path}': expected string, got {type(new_value).__name__}"
        if target_schema.type == "boolean" and not isinstance(new_value, bool):
            return False, f"Type mismatch at '{path}': expected boolean, got {type(new_value).__name__}"

    if cmd.type == "add" and target_schema.type != "number":
        return False, f"Cannot add to non-numeric field at '{path}'"

    return True, ""


def _get_schema_for_path(schema: SchemaNode, path: str) -> Optional[SchemaNode]:
    """Navigate schema tree following a path."""
    if not path:
        return schema
    parts = to_path(path)
    current = schema
    for p in parts:
        if current.type == "object":
            if isinstance(p, str) and p in current.properties:
                current = current.properties[p]
            else:
                return None
        elif current.type == "array":
            if current.element_type:
                current = current.element_type
            else:
                return None
        else:
            return None
    return current


# ═══ Utility ═══

def compute_current_variables(chat_log: list) -> dict:
    """Walk chat_log backward and return the latest stat_data, or {} if none."""
    for turn in reversed(chat_log):
        variables = turn.get("variables")
        if variables and "stat_data" in variables:
            return copy.deepcopy(variables["stat_data"])
    return {}


def apply_variables_to_turn(turn_entry: dict, stat_data: dict, delta: dict = None) -> dict:
    """Attach variable data to a turn entry."""
    turn_entry["variables"] = {
        "stat_data": copy.deepcopy(stat_data),
    }
    if delta:
        turn_entry["variables"]["delta"] = delta
    return turn_entry


# ═══ Variable Diff / Audit ═══

def compute_var_diff(old_data: dict, new_data: dict, prefix: str = "") -> dict:
    """Deep recursive diff between two stat_data dicts.
    Returns {changed: {path: {old, new}}, untouched_sections: [paths], new_paths: [paths], removed_paths: [paths]}
    """
    changed = {}
    new_paths_list = []
    removed_paths_list = []

    all_keys = set(old_data.keys()) | set(new_data.keys())

    for key in all_keys:
        full_path = f"{prefix}.{key}" if prefix else key
        old_val = old_data.get(key)
        new_val = new_data.get(key)

        if key not in old_data:
            new_paths_list.append(full_path)
            changed[full_path] = {"old": None, "new": new_val}
        elif key not in new_data:
            removed_paths_list.append(full_path)
            changed[full_path] = {"old": old_val, "new": None}
        elif isinstance(old_val, dict) and isinstance(new_val, dict):
            sub = compute_var_diff(old_val, new_val, full_path)
            changed.update(sub["changed"])
            new_paths_list.extend(sub["new_paths"])
            removed_paths_list.extend(sub["removed_paths"])
        elif old_val != new_val:
            changed[full_path] = {"old": old_val, "new": new_val}

    return {
        "changed": changed,
        "new_paths": new_paths_list,
        "removed_paths": removed_paths_list,
    }


def summarize_sections(stat_data: dict, changed_paths: set[str]) -> dict:
    """Group stat_data by top-level sections and flag which were touched.
    Returns {sections: {name: {touched: bool, paths: int, touched_paths: [str]}}}
    """
    sections = {}
    for section_name, section_data in stat_data.items():
        prefix = section_name
        all_paths = _collect_paths(section_data, prefix)
        touched = [p for p in all_paths if p in changed_paths]
        sections[section_name] = {
            "touched": len(touched) > 0,
            "total_paths": len(all_paths),
            "touched_paths": touched,
        }
    return sections


def _collect_paths(data, prefix=""):
    """Collect all leaf paths under a data node."""
    paths = []
    if isinstance(data, dict):
        for k, v in data.items():
            full = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                paths.extend(_collect_paths(v, full))
            else:
                paths.append(full)
    return paths


def audit_variables(prev_data: dict, new_data: dict, content_text: str = "") -> dict:
    """Full audit: diff + section summary. Returns a dict suitable for .var_diff.json."""
    diff = compute_var_diff(prev_data or {}, new_data or {})

    changed_paths = set(diff["changed"].keys())
    sections = summarize_sections(new_data, changed_paths)

    untouched = [name for name, info in sections.items() if not info["touched"]]

    return {
        "changed": diff["changed"],
        "new_paths": diff["new_paths"],
        "removed_paths": diff["removed_paths"],
        "sections": sections,
        "untouched_sections": untouched,
        "change_count": len(diff["changed"]),
    }


# ═══ Self-test ═══

if __name__ == "__main__":
    # Test command extraction
    test_text = """
    Some narrative text...
    _.set('player.hp', 80); // took damage
    _.add('player.gold', 50);
    _.insert('inventory.items', 'Health Potion');
    _.delete('npcs[0]');

    <json_patch>
    [{"op": "replace", "path": "/player/mp", "value": 60}]
    </json_patch>
    """

    print("=== Command Extraction ===")
    cmds = extract_commands(test_text)
    for c in cmds:
        print(f"  {c}")

    # Test execution
    print("\n=== Command Execution ===")
    initial = {
        "player": {"hp": 100, "mp": 100, "gold": 0},
        "inventory": {"items": ["Sword"]},
        "npcs": [{"name": "Guard"}, {"name": "Merchant"}],
    }

    new_data, changes = execute_commands(initial, cmds)
    print(f"  Changes: {json.dumps(changes, ensure_ascii=False, indent=2)}")
    print(f"  New data: {json.dumps(new_data, ensure_ascii=False, indent=2)}")

    # Test schema
    print("\n=== Schema ===")
    schema = generate_schema(new_data)
    print(f"  {json.dumps(schema.to_dict(), ensure_ascii=False, indent=2)}")
