"""
Claude Code RP Bridge Server
Serves frontend + receives user input via POST, writes to input.txt for Claude Code to read.
Usage: python server.py [port]
"""
import http.server
import json
import os
import sys
import urllib.parse
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
SKILLS = Path(__file__).parent
ROOT = SKILLS / "styles"
PROFILES_DIR = ROOT / "profiles"
INPUT_FILE = ROOT / "input.txt"
PENDING_FILE = ROOT / ".pending"
SETTINGS_FILE = ROOT / "settings.json"
CARD_PATH_FILE = ROOT / ".card_path"

# Allow importing handler from skills/
sys.path.insert(0, str(SKILLS))
import handler
from image_gen import image_handler

DEFAULT_SETTINGS = {
    "style": "北棱特调",
    "nsfw": "直白",
    "person": "第二人称",
    "antiImpersonation": True,
    "bgNpc": False,
    "charName": "",
    "wordCount": 600,
    "imageGenEnabled": True,
    "imageGenAuto": True,
    "imageGenBackend": "novelai",
    "naiApiKey": "",
    "naiModel": "nai-diffusion-4-5-curated",
    "naiWidth": 832,
    "naiHeight": 1216,
    "naiSteps": 28,
    "naiScale": 3,
    "comfyUrl": "http://127.0.0.1:8188",
    "comfyWorkflow": "",
}

os.chdir(str(ROOT))


def _card_folder():
    """Read the current card folder path from .card_path config."""
    if CARD_PATH_FILE.exists():
        for enc in ("utf-8", "gbk", "cp936"):
            try:
                path = CARD_PATH_FILE.read_text(encoding=enc).strip()
                if path and os.path.isdir(path):
                    return path
            except (UnicodeDecodeError, LookupError):
                continue
    return None


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/submit":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {"text": body}

            text = data.get("text", "").strip()
            char_name = data.get("charName", "").strip()

            if text:
                # Write input for Claude Code
                full = f"【{char_name}】{text}" if char_name else text
                INPUT_FILE.write_text(full, encoding="utf-8")
                PENDING_FILE.touch()
                self._json({"ok": True, "text": full})
            else:
                self._json({"ok": False, "error": "empty input"})

        elif parsed.path == "/api/settings":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                current = DEFAULT_SETTINGS.copy()
                if SETTINGS_FILE.exists():
                    try:
                        current.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
                    except Exception:
                        pass
                current.update(data)
                SETTINGS_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
                self._json({"ok": True, "settings": current})
            except json.JSONDecodeError:
                self._json({"ok": False, "error": "invalid json"})

        elif parsed.path == "/api/reroll":
            card = _card_folder()
            if not card:
                self._json({"ok": False, "error": "no card path configured"}, 400)
                return
            try:
                user_text = handler.reroll_last(card)
                if user_text:
                    self._json({"ok": True, "text": user_text})
                else:
                    self._json({"ok": False, "error": "no turns to reroll"}, 400)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._json({"ok": False, "error": str(e)}, 500)

        elif parsed.path == "/api/delete_turns":
            card = _card_folder()
            if not card:
                self._json({"ok": False, "error": "no card path configured"}, 400)
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                from_index = int(data.get("from_index", 0))
                handler.delete_turns(card, from_index)
                self._json({"ok": True})
            except (json.JSONDecodeError, ValueError) as e:
                self._json({"ok": False, "error": str(e)}, 400)

        elif parsed.path == "/api/switch_opening":
            card = _card_folder()
            if not card:
                self._json({"ok": False, "error": "no card path configured"}, 400)
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                opening_id = int(data.get("opening_id", 0))
                ok = handler.switch_opening(card, opening_id)
                if ok:
                    self._json({"ok": True})
                else:
                    self._json({"ok": False, "error": "cannot switch — opening already in progress"}, 400)
            except (json.JSONDecodeError, ValueError) as e:
                self._json({"ok": False, "error": str(e)}, 400)

        elif parsed.path == "/api/image-gen/generate":
            card = _card_folder()
            if not card:
                self._json({"ok": False, "error": "no card path configured"}, 400)
                return
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                turn = int(data.get("turn", 0))
                seg = int(data.get("seg", 0))
                result = image_handler.generate(turn, seg, card)
                if "error" in result:
                    self._json({"ok": False, "error": result["error"]}, 500)
                else:
                    self._json({"ok": True, "url": result["url"]})
            except (json.JSONDecodeError, ValueError) as e:
                self._json({"ok": False, "error": str(e)}, 400)

        elif parsed.path == "/api/style-profiles/delete":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
                name = data.get("name", "").strip()
                if not name:
                    self._json({"ok": False, "error": "missing name"}, 400)
                    return
                target = PROFILES_DIR / f"{name}.md"
                if target.exists():
                    target.unlink()
                    self._json({"ok": True})
                else:
                    self._json({"ok": False, "error": "profile not found"}, 404)
            except (json.JSONDecodeError, OSError) as e:
                self._json({"ok": False, "error": str(e)}, 400)

        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # API: check if new input is pending
        if parsed.path == "/api/pending":
            if PENDING_FILE.exists():
                text = INPUT_FILE.read_text(encoding="utf-8") if INPUT_FILE.exists() else ""
                self._json({"pending": True, "text": text})
            else:
                self._json({"pending": False})
            return

        # API: mark as processed (Claude Code calls this after reading)
        if parsed.path == "/api/done":
            PENDING_FILE.unlink(missing_ok=True)
            self._json({"ok": True})
            return

        # API: list available openings
        if parsed.path == "/api/openings":
            openings = handler.list_openings()
            self._json(openings)
            return

        # API: list available style profiles
        if parsed.path == "/api/style-profiles":
            profiles = []
            if PROFILES_DIR.exists():
                for f in sorted(PROFILES_DIR.glob("*.md")):
                    name = f.stem
                    content = f.read_text(encoding="utf-8")
                    title = name
                    desc = ""
                    lines = content.strip().split("\n")
                    for line in lines:
                        if line.startswith("# ") and not line.startswith("## "):
                            title = line[2:].strip()
                        elif line.strip() and not line.startswith("#"):
                            desc = line.strip()
                            break
                    profiles.append({"name": name, "title": title, "description": desc})
            self._json(profiles)
            return

        # API: get current settings
        if parsed.path == "/api/settings":
            settings = DEFAULT_SETTINGS.copy()
            if SETTINGS_FILE.exists():
                try:
                    saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                    settings.update(saved)
                except Exception:
                    pass
            self._json(settings)
            return

        # GET: serve generated images from card_folder/images/
        if parsed.path.startswith("/images/"):
            card = _card_folder()
            if not card:
                self._json({"ok": False, "error": "no card path configured"}, 400)
                return
            filename = parsed.path[len("/images/"):]
            img_path = image_handler.serve_image_by_filename(card, filename)
            if img_path:
                ext = os.path.splitext(filename)[1].lower()
                ct = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                      "webp": "image/webp", "gif": "image/gif"}.get(ext, "image/png")
                self.send_response(200)
                self.send_header("Content-Type", ct)
                self.send_header("Cache-Control", "public, max-age=3600")
                self.send_header("Content-Length", str(os.path.getsize(img_path)))
                self.end_headers()
                with open(img_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self._json({"ok": False, "error": "image not found"}, 404)
            return

        # Default: serve static files
        super().do_GET()

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        # Quieter logging
        if "POST" in fmt or "/api/" in fmt:
            print(f"[server] {fmt % args}")


if __name__ == "__main__":
    print(f"\n  RP Bridge Server")
    print(f"  Frontend → http://localhost:{PORT}")
    print(f"  Input file → {INPUT_FILE}")
    print(f"  Ctrl+C to stop\n")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] stopped")
        server.shutdown()
