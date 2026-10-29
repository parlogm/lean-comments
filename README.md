# lean-comments

A Claude Code plugin that keeps Claude's code comments rare and one sentence long.

Left alone, Claude tends to write comments that are true and well meant but far too long: multi-paragraph Javadoc, five-line rationales above a method, history ("this used to…"), ticket chains, design debates, and background copied straight from the task prompt. This plugin pushes that reasoning into the commit message or PR description, where it belongs, and leaves at most one sentence in the code, and only where a reader would otherwise get the code wrong.

## What's in it

| Piece | What it does |
|---|---|
| **Comment rule** (`hooks/comment-rule.md`) | Injected into every session by a `SessionStart` hook. One sentence per comment, no history/tickets/debates, doc comments only where a linter requires them, and don't copy the density of over-commented neighbours. Most of the effect comes from this. |
| **Skill** (`skills/lean-comments/`) | The detailed rules with examples, doc-comment requirements per ecosystem (Checkstyle, ESLint jsdoc, ruff/pydocstyle, revive, `missing_docs`, detekt, CS1591), and a `/lean-comments` cleanup pass for a diff, file or branch. The cleanup hands removed rationale back as PR-description text. |
| **Hook** (`skills/lean-comments/scripts/comment_density.py`) | `PostToolUse` on Edit/Write/MultiEdit. Looks only at comments the edit *adds*, and nudges Claude when it sees a 3+ line comment paragraph, a doc block with more than 2 prose lines or `<p>` paragraphs, history or ticket-chain wording, or comments above ~20% of the added code. Works for Java, Kotlin, TS/JS, Go, Rust, Swift, C/C++, C#, Python, Ruby, shell, SQL and more. |

## Install

```text
/plugin marketplace add parlogm/lean-comments
/plugin install lean-comments@lean-comments
```

The repository is private, so the marketplace add needs git access to it (e.g. `gh auth login` with the credential helper set up).

If you previously set this up by hand, remove the duplicates: the `# Code comments` section in `~/.claude/CLAUDE.md`, the `PostToolUse` entry for `comment_density.py` in `~/.claude/settings.json`, and `~/.claude/skills/lean-comments/`.

### Without the plugin system

1. Copy `skills/lean-comments/` to `~/.claude/skills/lean-comments/`.
2. Append `hooks/comment-rule.md` to `~/.claude/CLAUDE.md`.
3. Add the hook to `~/.claude/settings.json`:

```json
"hooks": {
  "PostToolUse": [
    { "matcher": "Edit|Write|MultiEdit",
      "hooks": [{ "type": "command", "command": "python3 ~/.claude/skills/lean-comments/scripts/comment_density.py", "timeout": 10 }] }
  ]
}
```

## Use

- Nothing to do day to day: the rule and hook apply to all code Claude writes.
- `/lean-comments [path]` trims the comments your uncommitted diff added (or the given path).
- `CLAUDE_LEAN_COMMENTS=off` disables both hooks for a session.
- If the hook flags a comment that really is essential as written, Claude keeps it and says so in one line.

## Results

All runs used Claude Opus 5.5 in isolated `claude -p` sessions (`--setting-sources project`, so no other user config), one or two runs per configuration. Small samples, but the direction was the same in every round.

**Eval suite** (`skills/lean-comments/evals/`, graded by `tools/grade.py`):

| Cases | With plugin | Without |
|---|---|---|
| 5 Java cases (rich ticket context, essay-heavy neighbour file, test with incident background, cleanup, Checkstyle minimum) | 25/25 | 14/25 |
| TypeScript feature + Python cleanup | 13/13 | 11/13 |

Typical difference: given a ticket with background, a dependency chain and a rejected alternative, Claude without the plugin wrote a 12-line Javadoc with `<p>` paragraphs and five ticket IDs. With it, two lines:

```java
// Grants every check, so callers are ungated: do not grant reports:export:all in production while this is in use.
// TODO(ABC-2153): replace with a remote gateway that calls the entitlements API and fails closed.
```

**Real projects** (3 tasks in existing Java/Spring, TypeScript and Angular codebases, 2 runs each, fresh clone per run):

| Task | Comment lines added (with / without) | Background leaked into comments (with / without) |
|---|---|---|
| Rate limiter method + header (Java) | 5.5 / 10.5 | 0 / 2 |
| Persisted settings migration (TS) | 1 / 3.5 | 0 / 1 |
| Scroll-spy in a navbar (Angular) | 3.5 / 7.5 | 0 / 0.5 |

**Hook calibration**: replaying the history of Claude-co-authored commits from two codebases through the hook flags 19% and 38% of file edits, almost all of them multi-line rationale comments and doc blocks.

## Evals

Test cases live in `skills/lean-comments/evals/<case>/` in the layout `claude plugin eval` reads, so `claude plugin eval .` works too. The scripts in `tools/` run them with a with/without comparison:

```sh
tools/run_case.sh rich-context-feature-stub with_skill    /tmp/lc-iter-1
tools/run_case.sh rich-context-feature-stub without_skill /tmp/lc-iter-1
tools/grade.py /tmp/lc-iter-1                # writes grading.json + comments.txt per run
tools/replay.py skills/lean-comments/scripts/comment_density.py path/to/repo   # hook flag rate on real history
```

- Configurations: `with_skill` loads this repo as a plugin, `rule_only` appends only the rule, `without_skill` uses neither.
- Run iterations outside `~/.claude/`; Claude Code blocks writes there.
- The Checkstyle case needs a Checkstyle classpath in `CHECKSTYLE_CP` (or `tools/checkstyle.cp`); the TypeScript case needs Node 22.6+ for type stripping.
- `tools/trigger/eval_set.json` holds should/shouldn't-trigger queries for skill-creator's description evals.

## License

Apache-2.0
