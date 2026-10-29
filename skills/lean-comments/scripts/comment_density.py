#!/usr/bin/env python3
"""PostToolUse hook: nudge Claude when an Edit/Write/MultiEdit adds essay-style or redundant comments.

Only comments the edit *adds* count, so touching a legacy file full of comments doesn't flag.
Exits silently unless something trips. Disable with CLAUDE_LEAN_COMMENTS=off.
"""
import json
import os
import re
import sys

C_STYLE = {"java", "kt", "kts", "groovy", "gradle", "scala", "ts", "tsx", "js", "jsx", "mjs", "cjs",
           "go", "rs", "swift", "c", "h", "cc", "cpp", "hpp", "cs", "dart", "php", "scss"}
HASH = {"py", "sh", "bash", "zsh", "rb", "pl", "r", "tf"}
SQL = {"sql"}

SKIP_PATH = re.compile(r"/(\.claude|skills|build/generated|node_modules|vendor|dist)/")
# Tool directives and test-structure markers are not prose.
EXEMPT = re.compile(r"^\s*(//|#|--)\s*(NOSONAR|noinspection|eslint|prettier-ignore|@ts-|noqa|type:|"
                    r"pylint|shellcheck|go:|nolint|CHECKSTYLE|spotless|language=|given|when|then|arrange|act|assert)\b",
                    re.IGNORECASE)
STRINGS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`[^`]*`')
HISTORY = re.compile(r"\b(previously|no longer (carr|support|use|need|send|return|ship|call|accept|require|has|have)\w*|"
                     r"(?<!\bis )(?<!\bare )(?<!\bbe )(?<!\bwas )(?<!\bwere )(?<!\bbeen )used to|"
                     r"earlier (attempt|version)|was (changed|renamed|moved)|is now|are now|now (uses|only|a|an|the))\b",
                     re.IGNORECASE)
TICKET = re.compile(r"\b(?!(?:UTF|RFC|SHA|ISO|AES|MD|HTTP|TLS|X)-)[A-Z][A-Z0-9]+-\d+\b")

LINE_RATIO = 0.2
MIN_LINE_COMMENTS = 3
MAX_RUN = 2
MAX_BLOCK_PROSE = 2


def analyze(text, lang):
    """Return (line_comments, runs, code_lines, blocks); runs are lists of consecutive full-line comments."""
    line_comments, runs, code, blocks = [], [], 0, []
    block, run, closer = None, [], None
    marker = {"c": "//", "hash": "#", "sql": "--"}[lang]

    def end_run():
        nonlocal run
        if run:
            runs.append(run)
        run = []

    for raw in text.splitlines():
        line = raw.strip()
        if block is not None:
            block.append(line)
            if closer in line:
                blocks.append(block)
                block = None
            continue
        if not line:
            end_run()
            continue
        opener = None
        if lang != "hash" and line.startswith("/*"):
            opener, closer = "/*", "*/"
        elif lang == "hash" and line.startswith(('"""', "'''")):
            opener = closer = line[:3]
        if opener:
            end_run()
            if closer in line[len(opener):]:
                if not line.startswith("/**"):
                    blocks.append([line])
            else:
                block = [line]
            continue
        if lang == "hash" and line.startswith("#!"):
            continue
        if line.startswith(marker):
            if not EXEMPT.match(line):
                line_comments.append(line)
                run.append(line)
            continue
        end_run()
        code += 1
        bare = STRINGS.sub('""', line)
        pattern = r"(^|\s)#" if lang == "hash" else re.escape(marker)
        trailing = re.search(pattern, bare)
        if trailing and not EXEMPT.match(bare[trailing.start():].strip()):
            line_comments.append(line)
    end_run()
    return line_comments, runs, code, blocks


def prose_lines(block):
    body = [re.sub(r"^(/\*\*?|\*/|\*|\"\"\"|''')\s*", "", l).replace("*/", "").strip(" \"'") for l in block]
    tags = next((i for i, l in enumerate(body) if l.startswith("@")), len(body))
    return [l for l in body[:tags] if l]


def lang_for(path):
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in C_STYLE:
        return "c"
    if ext in HASH:
        return "hash"
    if ext in SQL:
        return "sql"
    return None


def pairs(tool, inp):
    if tool == "Write":
        return [("", inp.get("content", ""))]
    if tool == "Edit":
        return [(inp.get("old_string", ""), inp.get("new_string", ""))]
    if tool == "MultiEdit":
        return [(e.get("old_string", ""), e.get("new_string", "")) for e in inp.get("edits", [])]
    return []


def findings_for(tool, inp, lang):
    added, code, long_runs, long_blocks = [], 0, [], []
    for old, new in pairs(tool, inp):
        old_lc, old_runs, _, old_blocks = analyze(old, lang)
        new_lc, new_runs, new_code, new_blocks = analyze(new, lang)
        seen = set(old_lc)
        added += [c for c in new_lc if c not in seen]
        code += new_code
        old_run_text = {"\n".join(r) for r in old_runs}
        long_runs += [r for r in new_runs if len(r) > MAX_RUN and "\n".join(r) not in old_run_text]
        old_block_text = {"\n".join(b) for b in old_blocks}
        long_blocks += [b for b in new_blocks if "\n".join(b) not in old_block_text
                        and (len(prose_lines(b)) > MAX_BLOCK_PROSE or any(l.startswith("<p>") for l in prose_lines(b)))]

    out = []
    if len(added) >= MIN_LINE_COMMENTS and len(added) > LINE_RATIO * max(code, 1):
        out.append(f"{len(added)} comment lines added against {code} lines of code, e.g.:")
        out += [f"  {c[:120]}" for c in added[:5]]
    for r in long_runs[:3]:
        out.append(f"{len(r)}-line comment paragraph: {r[0][:100]}")
    for b in long_blocks[:3]:
        prose = prose_lines(b)
        out.append(f"{len(prose)}-line doc/block comment: {prose[0][:100]}")
    texts = added + [" ".join(prose_lines(b)) for b in long_blocks]
    history = [t for t in texts if HISTORY.search(t) or len(set(TICKET.findall(t)) - set(re.findall(r"TODO\((\S+?)\)", t))) > 1]
    for t in history[:3]:
        out.append(f"history/ticket narration: {t[:100]}")
    return out


def main():
    if os.environ.get("CLAUDE_LEAN_COMMENTS", "").lower() == "off":
        return
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return
    inp = event.get("tool_input", {})
    path = inp.get("file_path", "")
    lang = lang_for(path)
    if not lang or SKIP_PATH.search(path):
        return
    findings = findings_for(event.get("tool_name", ""), inp, lang)
    if not findings:
        return
    reason = (f"lean-comments: {os.path.basename(path)} has comments to trim.\n" + "\n".join(findings) +
              "\nCut each to one sentence or delete it. Reasoning, history, ticket chains and design rationale "
              "belong in the commit or PR description, not the code. Keep only what a reader would otherwise get "
              "wrong, plus Javadoc a linter requires. If a flagged comment is genuinely essential as written, "
              "leave it and carry on.")
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
