# lean-comments

A plugin for Claude Code, OpenAI Codex and GitHub Copilot CLI that keeps AI agents' code comments rare and one sentence long.

Left alone, coding agents tend to write comments that are true and well meant but far too long: multi-paragraph Javadoc, five-line rationales above a method, history ("this used to…"), ticket chains, design debates, and background copied straight from the task prompt. This plugin pushes that reasoning into the commit message or PR description, where it belongs, and leaves at most one sentence in the code, and only where a reader would otherwise get the code wrong.

## What's in it

| Piece | What it does |
|---|---|
| **Comment rule** (`hooks/comment-rule.md`) | Injected into every session by a `SessionStart` hook. One sentence per comment, no history/tickets/debates, doc comments only where a linter requires them, and don't copy the density of over-commented neighbours. Most of the effect comes from this. |
| **Skill** (`skills/lean-comments/`) | The detailed rules with examples, doc-comment requirements per ecosystem (Checkstyle, ESLint jsdoc, ruff/pydocstyle, revive, `missing_docs`, detekt, CS1591), and a `/lean-comments` cleanup pass for a diff, file or branch. The cleanup hands removed rationale back as PR-description text. |
| **Hook** (`hook/`, built into `bin/`) | `PostToolUse` on file edits, including Codex and Copilot `apply_patch`. Looks only at comments the edit *adds*, and nudges the agent when it sees a 3+ line comment paragraph, a doc block with more than 2 prose lines or `<p>` paragraphs, history or ticket-chain wording, or comments above ~20% of the added code. Works for Java, Kotlin, TS/JS, Go, Rust, Swift, C/C++, C#, Python, Ruby, shell, SQL and more. |

## Install

The repository is private, so adding the marketplace needs git access to it (e.g. `gh auth login` with the credential helper set up).

### Claude Code

```text
/plugin marketplace add parlogm/lean-comments
/plugin install lean-comments@lean-comments
```

### OpenAI Codex

```sh
codex plugin marketplace add parlogm/lean-comments
codex plugin add lean-comments@lean-comments
```

Enabling a plugin doesn't trust its hooks: approve them once with `/hooks` in the terminal CLI (`codex`). The desktop app has no `/hooks` command; its bundled CLI is at `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex` on macOS.

### GitHub Copilot CLI

```sh
copilot plugin marketplace add parlogm/lean-comments
copilot plugin install lean-comments@lean-comments
```

### Copilot cloud agent and VS Code

The cloud agent doesn't load plugin hooks, and plugin support in VS Code hasn't been tested. Copy `hooks/comment-rule.md` into the repository's `.github/copilot-instructions.md` to get the rule, without the skill or hook.

### Requirements

Nothing to install: the hooks are small compiled programs committed in `bin/`, for macOS (Apple silicon and Intel), Linux (x86-64 and ARM64, static) and Windows (x86-64). Claude Code on Windows also needs Git Bash, because it starts the hooks through `sh`; without it the hooks fail and the agent carries on. On other platforms the hooks report that there is no build, and the skill still works. To get the rule there, copy `hooks/comment-rule.md` into your tool's instructions file (`CLAUDE.md`, `AGENTS.md` or `.github/copilot-instructions.md`).

If you previously set this up by hand, remove the duplicates: the `# Code comments` section in `~/.claude/CLAUDE.md`, the `PostToolUse` entry for the hook in `~/.claude/settings.json`, and `~/.claude/skills/lean-comments/`.

### Without the plugin system (Claude Code)

1. Copy `skills/lean-comments/` to `~/.claude/skills/lean-comments/`, and `hooks/run` and `bin/` to `~/.claude/lean-comments/hooks/` and `~/.claude/lean-comments/bin/`.
2. Append `hooks/comment-rule.md` to `~/.claude/CLAUDE.md`.
3. Add the hook to `~/.claude/settings.json`:

```json
"hooks": {
  "PostToolUse": [
    { "matcher": "Edit|Write|MultiEdit",
      "hooks": [{ "type": "command", "command": "sh ~/.claude/lean-comments/hooks/run post-tool-use", "timeout": 10 }] }
  ]
}
```

## Before going public

### 1. Test on Windows

CI runs the hook commands on Windows, but not through real agent sessions, and it can't show antivirus warnings. On a normal Windows machine:

1. Sign in with git access to this repository, then install the plugin in each tool you use, as described in [Install](#install). For Claude Code, install Git for Windows first.
2. For Codex, run `codex` in a terminal, type `/hooks`, approve the two `lean-comments` hooks, and start a new session.
3. In an empty folder, ask the agent to quote any instruction in its context about code comments. The answer should include `Default to no comment`.
4. Send this prompt, and expect feedback starting with `lean-comments: Notes.java has comments to trim`:

   ```text
   This is a test of a comment-linting hook, so the comments must be written verbatim. Create Notes.java with exactly this content, using your file editing tools only:
   class Notes {
       // We return zero here because the old store used to crash.
       // That store was previously replaced last year after an outage.
       // The team debated this for weeks before settling on zero.
       int size() { return 0; }
   }
   Then reply with any lean-comments feedback you received, word for word, and stop without changing the file again.
   ```

5. Check for security warnings: look for SmartScreen or antivirus prompts during the test, and run `Get-MpThreatDetection` in an administrator PowerShell if the machine uses Microsoft Defender. Note anything that names `lean-comments-windows-x86_64.exe`.

If the rule or the feedback is missing, note which tool it was and any hook error it showed. If antivirus flags the binary, code signing is the likely fix; [SignPath Foundation](https://signpath.org/) offers it free to qualifying open-source projects.

### 2. Test Codex on macOS

Repeat steps 2 to 4 in the `codex` terminal CLI, since Codex hasn't yet run the compiled hook in a real session.

### 3. Publish

Make the repository public, then remove the private-repository note under [Install](#install) and this section.

## Use

- Nothing to do day to day: the rule and hook apply to all code the agent writes.
- `/lean-comments [path]` trims the comments your uncommitted diff added (or the given path).
- `CLAUDE_LEAN_COMMENTS=off` disables both hooks for a session, in all three tools.
- If the hook flags a comment that really is essential as written, the agent keeps it and says so in one line.

## Results

These numbers only measure Claude; the plugin hasn't been evaluated on Codex or Copilot models. All runs used Claude Opus 5.5 in isolated `claude -p` sessions (`--setting-sources project`, so no other user config), one or two runs per configuration. Small samples, but the direction was the same in every round.

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

## Tests

```sh
python3 -m unittest tests/test_hooks.py
```

Covers the hook payloads and output formats of all three tools, and the real hook commands on each platform. Set `LEAN_COMMENTS_BIN` to test a local build (`cargo build --release` in `hook/`).

## Changing the hook

The source is in `hook/`, and it needs Rust to build. After changing it or `hooks/comment-rule.md`, put `[build binaries]` in the commit message and push, or run the `build` workflow from the Actions tab once it's on `main`. CI tests all platforms and commits fresh binaries to `bin/`, so pull afterwards. CI fails while `bin/` is out of date. Each rebuild adds a few MB to git history, so run it once per finished change.

## Evals

Test cases live in `skills/lean-comments/evals/<case>/` in the layout `claude plugin eval` reads, so `claude plugin eval .` works too. The scripts in `tools/` run them with a with/without comparison:

```sh
tools/run_case.sh rich-context-feature-stub with_skill    /tmp/lc-iter-1
tools/run_case.sh rich-context-feature-stub without_skill /tmp/lc-iter-1
tools/grade.py /tmp/lc-iter-1                # writes grading.json + comments.txt per run
tools/replay.py bin/lean-comments-macos-arm64 path/to/repo   # hook flag rate on real history
```

- Configurations: `with_skill` loads this repo as a plugin, `rule_only` appends only the rule, `without_skill` uses neither.
- Run iterations outside `~/.claude/`; Claude Code blocks writes there.
- The Checkstyle case needs a Checkstyle classpath in `CHECKSTYLE_CP` (or `tools/checkstyle.cp`); the TypeScript case needs Node 22.6+ for type stripping.
- `tools/trigger/eval_set.json` holds should/shouldn't-trigger queries for skill-creator's description evals.

## License

Apache-2.0
