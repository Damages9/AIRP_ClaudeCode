"""Read real DeepSeek token usage from Claude Code session transcript, append to response.txt."""
import json, os, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Get session ID from lock file
lock_path = os.path.join(ROOT, ".claude", "scheduled_tasks.lock")
with open(lock_path, "r") as f:
    sid = json.load(f)["sessionId"]

# Derive project slug (e.g. D:\ds4 -> D--ds4)
slug = ROOT.replace(":", "-").replace(chr(92), "-").replace("/", "-")

transcript = os.path.join(
    os.environ["USERPROFILE"], ".claude", "projects", slug, f"{sid}.jsonl"
)

# Scan backwards for last assistant message with usage data
with open(transcript, "r", encoding="utf-8") as f:
    lines = f.readlines()

usage = None
for line in reversed(lines):
    entry = json.loads(line.strip() or "{}")
    if entry.get("type") == "assistant":
        u = entry.get("message", {}).get("usage", {})
        if u.get("input_tokens") or u.get("output_tokens"):
            usage = u
            break

if usage:
    intok = usage.get("input_tokens", 0)
    outtok = usage.get("output_tokens", 0)
    total = intok + outtok
    tokens_block = f"\n<tokens>\nin: {intok}\nout: {outtok}\ntotal: {total}\n</tokens>\n"

    resp = os.path.join(ROOT, "skills", "styles", "response.txt")
    with open(resp, "a", encoding="utf-8") as wf:
        wf.write(tokens_block)

    print(f"Token: in={intok} out={outtok} total={total}")
else:
    print("WARNING: no usage data in transcript")
