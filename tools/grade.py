#!/usr/bin/env python3
"""Grade lean-comments eval runs. usage: grade.py <iteration-dir>

Writes grading.json per run dir and comments.txt (every comment found) for manual review.
The Checkstyle case needs a Checkstyle classpath in $CHECKSTYLE_CP or tools/checkstyle.cp.
Assertions needing judgement read overrides from <iteration-dir>/manual.json:
{"<case>/<config>": {"<assertion text>": [true, "evidence"]}}.
"""
import ast
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

S = pathlib.Path(__file__).resolve().parent
SKILL = S.parent / "skills/lean-comments"
CP = os.environ.get("CHECKSTYLE_CP") or ((S / "checkstyle.cp").read_text().strip() if (S / "checkstyle.cp").exists() else "")
STRINGS = re.compile(r'"(?:\\.|[^"\\])*"')


def java_comments(text):
    """Yield (kind, prose_lines, raw, next_code_line) for each comment; kind in line|block|doc."""
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("/*"):
            j = i
            while "*/" not in lines[j]:
                j += 1
            raw = [l.strip() for l in lines[i:j + 1]]
            prose = [p for p in (re.sub(r"^(/\*\*?|\*/|\*)\s*", "", l).replace("*/", "").strip() for l in raw)
                     if p and not p.startswith("@")]
            nxt = next((l.strip() for l in lines[j + 1:] if l.strip() and not l.strip().startswith("@")), "")
            out.append(("doc" if s.startswith("/**") else "block", prose, "\n".join(raw), nxt))
            i = j + 1
            continue
        bare = STRINGS.sub('""', s)
        if "//" in bare:
            out.append(("line", [bare[bare.index("//") + 2:].strip()], s, ""))
        i += 1
    return out


def java_code_lines(text):
    n, in_block = 0, False
    for l in text.splitlines():
        s = l.strip()
        if in_block:
            in_block = "*/" not in s
            continue
        if s.startswith("/*"):
            in_block = "*/" not in s
            continue
        if s and not s.startswith("//"):
            n += 1
    return n


def strip_java(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r'("(?:\\.|[^"\\])*")|//.*', lambda m: m.group(1) or "", text)
    return re.sub(r"\s+", "", text)


def py_comments(text):
    comments = [l.strip() for l in text.splitlines() if re.search(r"(^|\s)#(?!!)", STRINGS.sub('""', l))]
    docs = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            d = ast.get_docstring(node, clean=False)
            if d is not None:
                docs.append(d)
    return comments, docs


def javac(files):
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run(["javac", "-d", d, *map(str, files)], capture_output=True, text=True)
    return r.returncode == 0, r.stderr.strip()[:300]


def ratio_check(comment_lines, code):
    r = comment_lines / max(code, 1)
    return r <= 0.10, f"{comment_lines} comment lines / {code} code lines = {r:.0%}"


MARKERS = re.compile(r"//\s*(given|when|then|arrange|act|assert)\b", re.I)


def max_run(text):
    best = run = 0
    for l in text.splitlines():
        s = l.strip()
        run = run + 1 if s.startswith("//") and not MARKERS.match(s) else 0
        best = max(best, run)
    return best


def java_runs(text):
    runs, run = [], []
    for l in text.splitlines() + [""]:
        s = l.strip()
        if s.startswith("//") and not MARKERS.match(s):
            run.append(s)
        elif run:
            runs.append(tuple(run))
            run = []
    return runs


def essays(text, max_lines=2):
    """Comment paragraphs or doc blocks longer than max_lines."""
    long_docs = [c[2] for c in java_comments(text) if c[0] != "line" and (len(c[1]) > max_lines or "<p>" in c[2])]
    return max_run(text), long_docs


def final_message(run):
    msg = ""
    for line in open(run / "transcript.jsonl"):
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "result":
            msg = ev.get("result", "")
    return msg


def comment_text(text):
    return [" ".join(c[1]) for c in java_comments(text)]


def grade(case, out):
    res = {}
    java = sorted(out.rglob("*.java"))
    dump = []
    if case == "rich-context-feature-stub":
        f = next((p for p in java if p.name == "PlaceholderEntitlementGateway.java"), None)
        if not f:
            return {k: (False, "PlaceholderEntitlementGateway.java missing") for k in ("01", "02", "03", "04", "05", "06")}, []
        text = f.read_text()
        run, docs = essays(text)
        res["01"] = (run <= 2 and not docs, f"longest // run {run}; long blocks: {[d[:60] for d in docs]}")
        raw = [c[2] for c in java_comments(text)]
        bad = [r for r in raw if re.search(r"ABC-1210|ABC-2281|ABC-2354|ABC-1024|ABC-2410", r)
               or ("ABC-2153" in r and "TODO" not in r)]
        res["02"] = (not bad, bad[0][:150] if bad else "clean")
        bg = [r for r in raw if re.search(r"design review|feature flag|flag service|considered|rejected", r, re.I)]
        res["03"] = (not bg, bg[0][:150] if bg else "clean")
        todo = [r for r in raw if "TODO" in r and "ABC-2153" in r]
        res["04"] = (bool(todo), todo[0][:150] if todo else "no TODO(ABC-2153)")
        n = sum(len(c[1]) for c in java_comments(text))
        res["05"] = (n <= 4, f"{n} comment lines")
        ok, err = javac(java)
        res["06"] = (ok, err or "ok")
        dump = raw
    elif case == "test-rich-context":
        tests = [p for p in java if p.name.endswith("Test.java")]
        if not tests:
            return {k: (False, "no test file") for k in ("01", "02", "03", "04")}, []
        text = "\n".join(p.read_text() for p in tests)
        cs = java_comments(text)
        docs = [c[2] for c in cs if c[0] == "doc"]
        res["01"] = (not docs, f"{len(docs)} Javadocs" + (f": {docs[0][:80]}" if docs else ""))
        run = max_run(text)
        res["02"] = (run <= 2, f"longest // run {run}")
        story = [c[2] for c in cs if re.search(r"INC-311|incident|24 ?h|cache\.enabled|stale", c[2], re.I)]
        res["03"] = (not story, story[0][:150] if story else "clean")
        n = sum(len(c[1]) for c in cs if not MARKERS.match(c[2]))
        res["04"] = (n <= 3, f"{n} comment lines (excluding markers)")
        dump = [c[2] for c in cs]
    elif case == "essay-neighbourhood-edit":
        base = SKILL / "evals" / case / "files"
        before = {c[2] for f in base.rglob("*.java") for c in java_comments(f.read_text())}
        added = [c for f in java for c in java_comments(f.read_text()) if c[2] not in before]
        ok, err = javac(java)
        res["01"] = (ok, err or "ok")
        n = sum(len(c[1]) for c in added)
        res["02"] = (n <= 2, f"{n} comment lines added")
        long_docs = [c[2] for c in added if c[0] != "line" and len(c[1]) > 1]
        base_runs = {r for f in base.rglob("*.java") for r in java_runs(f.read_text())}
        runs = max((len(r) for f in java for r in java_runs(f.read_text()) if r not in base_runs), default=0)
        res["03"] = (not long_docs and runs <= 2, f"long added docs: {[d[:60] for d in long_docs]}, longest added // run {runs}")
        svc = next((p for p in java if p.name == "RegistrationService.java"), None)
        orig = {c[2] for c in java_comments((base / "src/main/java/com/example/onboarding/partner/RegistrationService.java").read_text())}
        now = {c[2] for c in java_comments(svc.read_text())} if svc else set()
        missing = orig - now
        res["04"] = (not missing, f"{len(missing)} original comments changed" + (f": {next(iter(missing))[:60]}" if missing else ""))
        dump = [c[2] for c in added]
    elif case == "cleanup-essay-diff":
        f = out / "src/main/java/com/acme/config/ConfigMerger.java"
        text = f.read_text()
        orig = (SKILL / "evals" / case / "files/src/main/java/com/acme/config/ConfigMerger.java").read_text()
        run, docs = essays(text)
        res["01"] = (run <= 2 and not docs, f"longest // run {run}; long blocks: {[d[:60] for d in docs]}")
        raw = [c[2] for c in java_comments(text)]
        hist = [r for r in raw if re.search(r"ABC-8\d\d|used to|is now|no longer|we considered", r, re.I)]
        res["02"] = (not hist, hist[0][:150] if hist else "clean")
        res["03"] = ("---- writing" not in text and "---- resolving" not in text, "banners checked")
        joined = " ".join(" ".join(c[1]) for c in java_comments(text)).lower()
        ov = bool(re.search(r"replace|wholesale|instead of merg", joined))
        ls = "list" in joined
        res["04"] = (ov and ls, f"override-replaces kept={ov}, lists kept={ls}")
        legacy = '    // Tenant configs written before 2025 may still carry "override"; it is ignored on read.'
        res["05"] = (legacy in text, "present" if legacy in text else "changed or removed")
        ok, err = javac(java)
        same = strip_java(text) == strip_java(orig)
        res["06"] = (same and ok, f"code identical={same}, compiles={ok} {err}")
        msg = final_message(out.parent)
        offers = bool(re.search(r"PR description|pull request|PR body|commit message", msg, re.I))
        res["07"] = (offers, msg[-300:].replace("\n", " "))
        dump = raw
    elif case == "ts-rich-context-webhook":
        f = out / "src/payments/refundWebhook.ts"
        if not f.exists():
            return {k: (False, "refundWebhook.ts missing") for k in ("01", "02", "03", "04", "05")}, []
        text = f.read_text()
        run, docs = essays(text)
        res["01"] = (run <= 2 and not docs, f"longest // run {run}; long blocks: {[d[:60] for d in docs]}")
        raw = [c[2] for c in java_comments(text)]
        tickets = [r for r in raw if re.search(r"SHOP-\d+", r)]
        res["02"] = (not tickets, tickets[0][:150] if tickets else "clean")
        hist = [r for r in raw if re.search(r"\bv1\b|legacy|migrat|used to|queue|architecture", r, re.I)]
        res["03"] = (not hist, hist[0][:150] if hist else "clean")
        n = sum(len(c[1]) for c in java_comments(text))
        res["04"] = (n <= 3, f"{n} comment lines")
        r = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "-e",
                            f"import({json.dumps(str(f))}).then(m => process.exit(typeof m.handleRefundWebhook === 'function' ? 0 : 3))"],
                           capture_output=True, text=True, cwd=out)
        res["05"] = (r.returncode == 0 and "hasRefund" in text, f"node exit {r.returncode} {r.stderr.strip()[:150]}")
        dump = raw
    elif case == "python-cleanup-essay":
        f = out / "billing/proration.py"
        text = f.read_text()
        orig = (SKILL / "evals" / case / "files/billing/proration.py").read_text()
        tree = ast.parse(text)
        fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "prorated_charge_cents"), None)
        doc = ast.get_docstring(fn, clean=True) if fn else None
        res["01"] = (fn is not None and (doc is None or len(doc.strip().splitlines()) == 1), repr(doc)[:150])
        best = run = 0
        for l in text.splitlines():
            run = run + 1 if l.strip().startswith("#") else 0
            best = max(best, run)
        res["02"] = (best <= 2, f"longest # run {best}")
        hist = re.findall(r"BILL-\d+|Historically|fixed offset", text, re.I)
        res["03"] = (not hist, f"found {hist}" if hist else "clean")
        comments, _ = py_comments(text)
        tz = [c for c in comments if re.search(r"timezone|time zone|UTC", c, re.I) and "get the timezone" not in c.lower()]
        res["04"] = (bool(tz), tz[0] if tz else "timezone constraint gone")
        narr = [n for n in ("-----", "Get the timezone", "Calculate the daily rate", "Return the total", "multiply rate")
                if n.lower() in text.lower()]
        res["05"] = (not narr, f"remaining {narr}" if narr else "clean")
        legacy = "# Plans are billed in whole cents; never return fractional cents."
        res["06"] = (legacy in text, "present" if legacy in text else "changed or removed")

        def code_only(src):
            t = ast.parse(src)
            for n in ast.walk(t):
                body = getattr(n, "body", None)
                if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                        and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
                    n.body = body[1:] or [ast.Pass()]
            return ast.dump(t)

        res["07"] = (code_only(text) == code_only(orig), "AST without docstrings compared")
        msg = final_message(out.parent)
        res["08"] = (bool(re.search(r"PR description|pull request|PR body|commit message", msg, re.I)),
                     msg[-300:].replace("\n", " "))
        dump = comments + ([f'"""{doc}"""'] if doc else [])
    elif case == "checkstyle-javadoc-minimal":
        fs = [f for f in java if f.name == "ProviderAvailability.java"]
        if not fs:
            return {k: (False, "ProviderAvailability.java missing") for k in ("01", "02", "03", "04")}, []
        f = fs[0]
        if CP:
            r = subprocess.run(["java", "-cp", CP, "com.puppycrawl.tools.checkstyle.Main", "-c",
                                str(out / "config/checkstyle/checkstyle.xml"), str(f)], capture_output=True, text=True)
            v = [l.split("/")[-1] for l in r.stdout.splitlines() if l.startswith(("[WARN]", "[ERROR]"))]
            res["01"] = (r.returncode == 0 and not v, "; ".join(v)[:300] or "0 violations")
        else:
            res["01"] = (False, "no Checkstyle classpath: set CHECKSTYLE_CP")
        cs = java_comments(f.read_text())
        field = re.compile(r"^(private|protected|public)?\s*(static\s+)?(final\s+)?[\w<>, .?]+\s+\w+\s*(=.*)?;$")
        fdocs = [c for c in cs if c[0] == "doc" and field.match(c[3])]
        res["02"] = (bool(fdocs) and all("\n" not in c[2] and len(c[1]) == 1 for c in fdocs),
                     " | ".join(c[2] for c in fdocs)[:300])
        mdocs = [c for c in cs if c[0] == "doc" and "(" in c[3] and not field.match(c[3])]
        res["03"] = (not mdocs, f"{len(mdocs)} method/ctor Javadocs" + (f": {mdocs[0][2][:80]}" if mdocs else ""))
        ok, err = javac(java)
        res["04"] = (ok, err or "ok")
        dump = [c[2] for c in cs]
    return res, dump


def main():
    it = pathlib.Path(sys.argv[1])
    manual = json.loads((it / "manual.json").read_text()) if (it / "manual.json").exists() else {}
    for meta in sorted(it.glob("*/eval_metadata.json")):
        case = meta.parent.name
        asserts = json.loads(meta.read_text())["assertions"]
        for run in sorted(p for p in meta.parent.iterdir() if (p / "outputs").is_dir()):
            res, dump = grade(case, run / "outputs")
            exps = []
            for i, text in enumerate(asserts, 1):
                key = f"{i:02d}"
                override = manual.get(f"{case}/{run.name}", {}).get(text)
                if override:
                    passed, ev = override
                elif key in res:
                    passed, ev = res[key]
                else:
                    continue
                exps.append({"text": text, "passed": bool(passed), "evidence": ev})
            p = sum(e["passed"] for e in exps)
            json.dump({"expectations": exps, "summary": {"passed": p, "failed": len(exps) - p, "total": len(exps),
                                                         "pass_rate": round(p / max(len(exps), 1), 2)}},
                      open(run / "grading.json", "w"), indent=2)
            (run / "comments.txt").write_text("\n".join(dump) + "\n")
            print(f"{case:34} {run.name:14} {p}/{len(exps)}  " +
                  " ".join(("✓" if e["passed"] else "✗") for e in exps))


if __name__ == "__main__":
    main()
