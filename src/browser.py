import glob
import json
import os
import re
import textwrap
import sys

# KEYWORD = "illegal_aliens"
KEYWORD = sys.argv[1]

WRAP = 92                    # 문장 줄바꿈 폭
GPT_MAX_LINES = 60           # gpt_output 너무 길면 이 줄까지만 보여줌

# scene.py writes to either ./scene/<keyword>-<model>.jsonl (flat input) or
# ./scene/<data_name>/<keyword>/<keyword>-<model>.jsonl (input organized by
# data source). Search both layouts for this keyword's non-failed output.
def resolve_path(keyword):
    patterns = [
        os.path.join("scene", f"{keyword}-*.jsonl"),
        os.path.join("scene", "**", f"{keyword}-*.jsonl"),
    ]
    found = []
    for pat in patterns:
        found.extend(glob.glob(pat, recursive=True))
    candidates = [p for p in dict.fromkeys(found) if not p.endswith("-failed.jsonl")]
    if not candidates:
        return None
    if len(candidates) > 1:
        print(f"Multiple scene outputs found for keyword '{keyword}':")
        for c in candidates:
            print(" -", c)
        print(f"Using: {candidates[0]}\n")
    return candidates[0]

# ---------- ANSI colors ----------
RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"

FG_CYAN   = "\033[36m"
FG_GREEN  = "\033[32m"
FG_YELLOW = "\033[33m"
FG_MAG    = "\033[35m"
FG_BLUE   = "\033[34m"
FG_RED    = "\033[31m"
FG_WHITE  = "\033[37m"

def clear():
    os.system("clear" if os.name != "nt" else "cls")

def wrap(s, width=WRAP):
    return textwrap.fill(s, width=width)

def clamp(i, n):
    return max(0, min(i, n-1))

def trim_lines(text, max_lines=GPT_MAX_LINES):
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n{DIM}... ({len(lines)-max_lines} more lines hidden){RESET}"

def highlight(text, pattern):
    """Highlight regex matches with reverse video."""
    if not pattern:
        return text
    try:
        regex = re.compile(pattern, flags=re.IGNORECASE)
    except re.error:
        return text
    return regex.sub(lambda m: f"\033[7m{m.group(0)}{RESET}", text)

def load_rows(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows

# Optional metadata fields to show in the header, tried in order, whichever
# are present in a given row (schema varies across datasets/collection runs).
META_FIELDS = [
    ("scene", "scene label"),
    ("scene-id", "scene-id"),
    ("text-id", "text-id"),
    ("cluster", "cluster"),
    ("article", "article_id"),
]

def get_sentence(row):
    return row.get("sentence", row.get("keyword_sentence", ""))

def render(row, idx, n, search_pat=None):
    uid = row.get("id", row.get("unique_id", "(no id)"))
    keyword = str(row.get("keyword", ""))
    sent = get_sentence(row)
    gpt = row.get("gpt_output", "")

    # highlight search matches in displayed fields
    sent_show = highlight(wrap(sent), search_pat)
    gpt_show = highlight(trim_lines(gpt), search_pat)

    meta = " ".join(
        f"{DIM}|{RESET} {FG_MAG}{label}{RESET}={BOLD}{row[key]}{RESET}"
        for label, key in META_FIELDS
        if row.get(key) not in (None, "")
    )

    bar = f"{FG_BLUE}{'━'*110}{RESET}"
    print(bar)
    print(
        f"{BOLD}{FG_CYAN}[{idx+1}/{n}]{RESET}  "
        f"{BOLD}{FG_WHITE}{uid}{RESET}  "
        f"{meta} "
        f"{DIM}|{RESET} {FG_MAG}keyword{RESET}={BOLD}{FG_YELLOW}{keyword}{RESET}"
    )
    if search_pat:
        print(f"{DIM}Search:{RESET} {BOLD}{search_pat}{RESET}")
    print(bar)

    print(f"{BOLD}{FG_GREEN}Sentence{RESET}")
    print(sent_show)
    print()

    print(f"{BOLD}{FG_GREEN}GPT output{RESET} {DIM}(trimmed){RESET}")
    print(gpt_show)
    print(bar)

    print(
        f"{DIM}Keys:{RESET} "
        f"{BOLD}Enter/n{RESET}=next  "
        f"{BOLD}p{RESET}=prev  "
        f"{BOLD}/text{RESET}=search next  "
        f"{BOLD}q{RESET}=quit"
    )

def find_next(rows, start_idx, pattern):
    """Find next row index > start_idx where pattern appears in sentence or gpt_output."""
    if not pattern:
        return None
    try:
        regex = re.compile(pattern, flags=re.IGNORECASE)
    except re.error:
        return None

    for k in range(start_idx + 1, len(rows)):
        blob = (get_sentence(rows[k]) + "\n" + rows[k].get("gpt_output", ""))
        if regex.search(blob):
            return k
    return None

# ---------- main ----------
PATH = resolve_path(KEYWORD)
if PATH is None:
    print(f"No scene output found for keyword '{KEYWORD}' under ./scene/")
    raise SystemExit(1)

rows = load_rows(PATH)
if not rows:
    print(f"No rows loaded from {PATH}.")
    raise SystemExit(1)

i = 0
last_search = None

while True:
    clear()
    render(rows[i], i, len(rows), search_pat=last_search)

    cmd = input("> ").rstrip("\n")

    if cmd == "" or cmd.lower() == "n":
        i = clamp(i + 1, len(rows))
        continue
    if cmd.lower() == "p":
        i = clamp(i - 1, len(rows))
        continue
    if cmd.lower() == "q":
        break

    # search: "/amnesty" or "/Tapper|Priebus"
    if cmd.startswith("/"):
        pat = cmd[1:].strip()
        if not pat:
            # empty search clears highlight
            last_search = None
            continue
        last_search = pat
        nxt = find_next(rows, i, pat)
        if nxt is None:
            # no next match; small message and stay
            print(f"{FG_RED}No further match found.{RESET}")
            input("Press Enter to continue...")
        else:
            i = nxt
        continue

    # ignore unknown commands
