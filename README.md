# lean-comments

A plugin for Claude Code, OpenAI Codex and GitHub Copilot CLI that keeps AI agents' code comments rare and one sentence long.

Left alone, coding agents tend to write comments that are true and well meant but far too long: multi-paragraph Javadoc, five-line rationales above a method, history ("this used to…"), ticket chains, design debates, and background copied straight from the task prompt. This plugin pushes that reasoning into the commit message or PR description, where it belongs, and leaves at most one sentence in the code, and only where a reader would otherwise get the code wrong.

## What's in it

| Piece | What it does |
|---|---|
| **Comment rule** (`hooks/comment-rule.md`) | Injected into every session by a `SessionStart` hook, and into every subagent by a `SubagentStart` hook. One sentence per comment, no history/tickets/debates, doc comments only where a linter requires them, and don't copy the density of over-commented neighbours. Most of the effect comes from this. |
| **Skill** (`skills/lean-comments/`) | The detailed rules with examples, doc-comment requirements per ecosystem (Checkstyle, ESLint jsdoc, ruff/pydocstyle, revive, `missing_docs`, detekt, CS1591), and a `/lean-comments` cleanup pass for a diff, file or branch. The cleanup hands removed rationale back as PR-description text. |
| **Hooks** (`hook/`, built into `bin/`) | Look only at comments the agent *adds*, and nudge it when they see a 3+ line comment paragraph, a doc block with more than 2 prose lines or `<p>` paragraphs, history or ticket-chain wording, or comments above ~20% of the added code. Two checks share those rules: `PostToolUse` on each file edit (including Codex and Copilot `apply_patch`), and an end-of-turn check that catches files the agent changed some other way. Works for Java, Kotlin, TS/JS, Go, Rust, Swift, C/C++, C#, Python, Ruby, shell, SQL and more. |

### Edits made outside the edit tools

Agents don't always edit through their edit tools. Particularly in Claude Code's auto mode, they often change files with `sed -i`, `perl -pi`, `cat > File.java` or a short Python script; in one user's auto-mode sessions with Claude Opus 5.5 that was roughly 29% of source-file writes. A `PostToolUse` hook never sees what those commands change.

So when you send a prompt, the hook snapshots the repository's source files (in the background, through a private copy of the git index; your index, stash and history are untouched). When the agent finishes its turn, it compares against that snapshot and checks the comments the turn added, whichever way they were written. If it finds any, the agent gets one more pass to trim them. Comments the edit hook already checked aren't reported again, and moved or renamed files don't count as new.

What it leaves alone: changes from before your prompt, including your own; turns the agent starts without a prompt; git-ignored files, files over 1 MiB, and files whose header comment marks them as generated (`@generated`, `DO NOT EDIT` and similar); turns that change more than 40 files outside the edit tools; and turns where `HEAD` moved to commits the agent didn't just make (switching branches, pulling, resetting). Committing or amending during the turn is fine. It only covers the git repository the session runs in, so outside a git repository only the edit hook applies, and edits in another repository or in a git worktree outside the session's checkout go unchecked. Two agents working in the same checkout at the same time see each other's changes. In a typical repository the snapshot takes about 0.1 s; in one with tens of thousands of directories it takes as long as `git status`.

### Subagents

Subagents get the rule at start-up through `SubagentStart`, in all three tools. The exception is Copilot CLI's built-in `general-purpose` agent, which doesn't fire that event and so runs without the rule. The edit hook checks subagents' edits as it does the main agent's.

The end-of-turn check runs only when the main agent ends its turn. It catches shell-made edits from a subagent that finished during that turn in the same checkout, and asks the main agent to trim them. It misses subagents still running in the background when the turn ends, and subagents working in their own worktree.

## Install

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

Enabling a plugin doesn't trust its hooks: approve them once with `/hooks` in the terminal CLI (`codex`), and again after an update that changes them. The desktop app has no `/hooks` command; its bundled CLI is at `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex` on macOS.

### GitHub Copilot CLI

```sh
copilot plugin marketplace add parlogm/lean-comments
copilot plugin install lean-comments@lean-comments
```

### Copilot cloud agent and VS Code

The cloud agent doesn't load plugin hooks, and plugin support in VS Code hasn't been tested. Copy `hooks/comment-rule.md` into the repository's `.github/copilot-instructions.md` to get the rule, without the skill or hook.

### Requirements

Nothing to install: the hooks are small compiled programs committed in `bin/`, for macOS (Apple silicon and Intel), Linux (x86-64 and ARM64, static) and Windows (x86-64). Claude Code on Windows also needs Git Bash, because it starts the hooks through `sh`; without it the hooks fail and the agent carries on. On other platforms the hooks report that there is no build, and the skill still works. To get the rule there, copy `hooks/comment-rule.md` into your tool's instructions file (`CLAUDE.md`, `AGENTS.md` or `.github/copilot-instructions.md`).

If you previously set this up by hand in Claude Code, remove the duplicates: the `# Code comments` section in `~/.claude/CLAUDE.md`, the `lean-comments` hook entries in `~/.claude/settings.json`, and `~/.claude/skills/lean-comments/`.

### Without the plugin system (Claude Code)

1. Copy `skills/lean-comments/` to `~/.claude/skills/lean-comments/`, and `hooks/run` and `bin/` to `~/.claude/lean-comments/hooks/` and `~/.claude/lean-comments/bin/`.
2. Add the hooks to `~/.claude/settings.json`. `SessionStart` and `SubagentStart` give the main agent and its subagents the rule, so drop any `# Code comments` section an earlier setup appended to `~/.claude/CLAUDE.md`. Without the `UserPromptSubmit` and `Stop` entries, edits made through shell commands or scripts go unchecked:

```json
"hooks": {
  "SessionStart": [
    { "hooks": [{ "type": "command", "command": "sh ~/.claude/lean-comments/hooks/run session-start", "timeout": 10 }] }
  ],
  "SubagentStart": [
    { "hooks": [{ "type": "command", "command": "sh ~/.claude/lean-comments/hooks/run subagent-start", "timeout": 10 }] }
  ],
  "UserPromptSubmit": [
    { "hooks": [{ "type": "command", "command": "sh ~/.claude/lean-comments/hooks/run user-prompt-submit", "async": true, "timeout": 30 }] }
  ],
  "PostToolUse": [
    { "matcher": "Edit|Write|MultiEdit",
      "hooks": [{ "type": "command", "command": "sh ~/.claude/lean-comments/hooks/run post-tool-use", "timeout": 10 }] }
  ],
  "Stop": [
    { "hooks": [{ "type": "command", "command": "sh ~/.claude/lean-comments/hooks/run stop", "timeout": 30 }] }
  ]
}
```

## Use

- Nothing to do day to day: the rule and hooks apply to all code the agent writes.
- Ask the agent to trim comments, or invoke the `lean-comments` skill (`/lean-comments:lean-comments` in Claude Code), to trim the comments your uncommitted diff added, or a path you give it.
- `LEAN_COMMENTS=off` disables all the hooks for a session, in all three tools. The older `CLAUDE_LEAN_COMMENTS=off` still works.
- If a hook flags a comment that really is essential as written, the agent keeps it and says so in one line.

## Results

These numbers only measure Claude; the plugin hasn't been evaluated on Codex or Copilot models. All runs used Claude Opus 5.5 in isolated `claude -p` sessions (`--setting-sources project`, so no other user config), one or two runs per configuration. Small samples, but the direction was the same in every round. They predate the end-of-turn check, and those runs allowed no `sed` or `perl`, so nearly every edit went through the edit tools.

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

Covers the hook payloads and output formats of all three tools, the end-of-turn check in throwaway git repositories, and the real hook commands on each platform. Set `LEAN_COMMENTS_BIN` to test a local build (`cargo build --release` in `hook/`).

## Changing the hook

The source is in `hook/`, and it needs Rust to build. After changing it or `hooks/comment-rule.md`, put `[build binaries]` in the commit message and push, or run the `build` workflow from the Actions tab once it's on `main`. CI tests all platforms and commits fresh binaries to `bin/`, so pull afterwards. CI fails while `bin/` is out of date. Each rebuild adds a few MB to git history, so run it once per finished change.

## Checking a release by hand

CI runs the hook commands on every platform, but not through real agent sessions, and it can't show antivirus warnings. On the machine you want to check:

1. Install the plugin in each tool you use, as described in [Install](#install). On Windows, install Git for Windows first if you use Claude Code.
2. For Codex, run `codex` in a terminal, type `/hooks`, approve the five `lean-comments` hooks, and start a new session.
3. In an empty folder, ask the agent to quote any instruction in its context about code comments. The answer should include `Default to no comment`. Then ask it to have an `Explore` subagent (`explore` in Copilot) quote the same, without passing the rule along; that answer should include it too.
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

5. In a git repository, send this prompt, and expect feedback starting with `lean-comments: end-of-turn check`:

   ```text
   This is a test of a comment-linting hook, so the comments must be written verbatim. Create Notes2.java with exactly the content from the previous test, using one shell command (a heredoc or a python3 script), not your file editing tools. Don't change the file again in this reply, and end your turn. If a hook then reports anything, reply with that feedback word for word and stop without changing the file.
   ```

6. On Windows, check for security warnings: look for SmartScreen or antivirus prompts during the test, and run `Get-MpThreatDetection` in an administrator PowerShell if the machine uses Microsoft Defender. Note anything that names `lean-comments-windows-x86_64.exe`.

If the rule or the feedback is missing, note which tool it was and any hook error it showed. If antivirus flags the binary, code signing is the likely fix; [SignPath Foundation](https://signpath.org/) offers it free to qualifying open-source projects.

## Evals

Test cases live in `skills/lean-comments/evals/<case>/` in the layout `claude plugin eval` reads, so `claude plugin eval .` works too. The scripts in `tools/` run them in Claude Code (`claude -p`) with a with/without comparison:

```sh
tools/run_case.sh rich-context-feature-stub with_skill    /tmp/lc-iter-1
tools/run_case.sh rich-context-feature-stub without_skill /tmp/lc-iter-1
PERMISSION_MODE=auto tools/run_case.sh rich-context-feature-stub hook_only /tmp/lc-iter-2
tools/grade.py /tmp/lc-iter-1                # writes grading.json + comments.txt per run
tools/replay.py bin/lean-comments-macos-arm64 path/to/repo   # hook flag rate on real history
```

- Configurations: `with_skill` loads this repo as a plugin, `rule_only` appends only the rule, `hook_only` wires only the hooks, `without_skill` uses none of them. Comparing `rule_only` and `hook_only` with the other two shows what each part contributes.
- `MODEL` and `PERMISSION_MODE` (default `acceptEdits`) override the session. `auto` is closest to how many people run Claude Code, and it's where agents most often edit through the shell.
- Each run's `timing.json` also records `hook_flags` (how many times a hook reported comments), `edit_tool_writes` and `bash_writes` (file writes through shell commands, by pattern match).
- Run iterations outside `~/.claude/`; Claude Code blocks writes there.
- The Checkstyle case needs a Checkstyle classpath in `CHECKSTYLE_CP` (or `tools/checkstyle.cp`); the TypeScript case needs Node 22.6+ for type stripping.
- `tools/trigger/eval_set.json` holds should/shouldn't-trigger queries for skill-creator's description evals.

## License

Apache-2.0
