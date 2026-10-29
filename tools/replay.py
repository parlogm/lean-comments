#!/usr/bin/env python3
"""usage: replay.py <hook-script> <repo> [<repo>...]

Replays every code hunk from each repo's history through the hook, per language.
Set CLAUDE_ONLY=1 to restrict to commits with a Claude co-author trailer.
"""
import collections
import importlib.util
import os
import random
import re
import subprocess
import sys

spec = importlib.util.spec_from_file_location("hook", sys.argv[1])
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
claude_only = os.environ.get("CLAUDE_ONLY") == "1"

stats = collections.defaultdict(lambda: [0, 0])
kinds = collections.Counter()
samples = collections.defaultdict(list)
for repo in sys.argv[2:]:
    log = subprocess.run(["git", "-C", repo, "log", "--no-merges", "--format=%h%x09%B%x00"],
                         capture_output=True, text=True).stdout
    for entry in log.split("\0"):
        if "\t" not in entry:
            continue
        sha, body = entry.strip().split("\t", 1)
        if claude_only and "co-authored-by: claude" not in body.lower():
            continue
        diff = subprocess.run(["git", "-C", repo, "show", "--format=", "--unified=0", sha],
                              capture_output=True, text=True).stdout
        for f in re.split(r"^diff --git ", diff, flags=re.M)[1:]:
            path = f.split("\n", 1)[0].split(" b/")[-1]
            if hook.SKIP_PATH.search("/" + path) or "graphify-out" in path:
                continue
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            lang = hook.lang_for(path)
            if not lang:
                continue
            edits = []
            for hunk in re.split(r"^@@.*@@.*$", f, flags=re.M)[1:]:
                lines = hunk.splitlines()
                edits.append({"old_string": "\n".join(l[1:] for l in lines if l.startswith("-") and not l.startswith("---")),
                              "new_string": "\n".join(l[1:] for l in lines if l.startswith("+") and not l.startswith("+++"))})
            if not any(e["new_string"] for e in edits):
                continue
            stats[ext][0] += 1
            found = hook.findings_for("MultiEdit", {"edits": edits}, lang)
            if found:
                stats[ext][1] += 1
                for x in found:
                    m = re.match(r"(\d+ comment lines added|\d+-line comment paragraph|\d+-line doc/block|history)", x)
                    if m:
                        kinds[re.sub(r"\d+", "N", m.group(1))] += 1
                        samples[ext].append(f"{os.path.basename(repo)}@{sha} {path.rsplit('/', 1)[-1]}: {x[:140]}")

total = sum(s[0] for s in stats.values())
flagged = sum(s[1] for s in stats.values())
print(f"all: {flagged}/{total} file-edits flagged ({flagged / max(total, 1):.0%})  {dict(kinds)}")
for ext, (n, k) in sorted(stats.items(), key=lambda kv: -kv[1][0]):
    print(f"  .{ext:5} {k:4}/{n:<5} ({k / max(n, 1):.0%})")
random.seed(1)
for ext, xs in samples.items():
    if ext != "java":
        for x in random.sample(xs, min(6, len(xs))):
            print("   ", x)
