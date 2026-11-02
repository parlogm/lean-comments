---
name: lean-comments
description: Keeps code comments rare and one sentence long, and trims over-commented code, in any language. Use when the user says there are too many comments, comments are too long, redundant or essay-like, Javadoc/JSDoc/docstrings are too verbose, or asks to clean up, trim, shorten or de-noise comments in a diff, file, branch or PR. Use it when the lean-comments hook flags an edit, for /lean-comments, and when unsure how much Javadoc a Checkstyle config requires.
---

# Lean comments

A comment is worth its reading time only when it stops someone from getting the code wrong. Names, types and tests already say *what* and *how*. Reasoning, history and context belong in the commit message and PR description: reviewers read those once, and they never go stale in the file.

The failure this skill exists for is **the essay**: a true, well-meant "why" that runs to a paragraph. A five-line rationale above a method gets skimmed, drifts out of date, and turns the file into a design doc. The fix is rarely to delete the fact. Compress it to the one sentence that changes how someone edits the code, and send the rest to the PR.

## The budget

- **One sentence per comment.** If you need two, ask which one a future editor actually needs.
- **One line per Javadoc/docstring**, and only where a linter requires one (see below).
- **No paragraph runs.** Three or more consecutive `//` lines is an essay, even with no blank line in it.

## What doesn't go in code comments

| Pattern | Seen in the wild | Do instead |
|---|---|---|
| Restating or narrating code | `// Load the order from the repository` | delete |
| Section banners | `// ===== Helpers =====` | delete, or extract a method/class |
| The change you just made | `// added refund support`, `// now uses the JDK client` | commit message |
| History and archaeology | `retries are now done by the gateway (ABC-831); this client no longer backs off itself…` | delete. Code shows what *is*; git shows what *was*. |
| Ticket chains and status | `waiting on ABC-77, which waits on ABC-80 (spike) and ABC-81, neither started…` | PR description. Keep at most `TODO(ABC-81): call the real API`. |
| Design debate | `two methods instead of a boolean parameter because call sites read better`, `we considered a queue but…` | PR description or ADR |
| Background copied from the task | issue-tracker context, chat decisions, "per the design doc…" | PR description |
| Doc comments on tests explaining what's proven | `/** Verifies retries stop after the third 503 and the last error is rethrown… */` | a test name that says it |
| Commented-out code | `// oldCall(x);` | delete |

## What earns one sentence

A fact that would otherwise cause a wrong edit:

- External behaviour the code can't show: `// The vendor API returns 200 with an empty body for unknown ids, not 404.`
- An irreversible or ordering constraint: `# The bank reads the drop folder once at 02:00 UTC; later files wait a day.`
- A deliberate oddity someone would "fix": `// Outside the transaction on purpose: a slow remote call must not pin a DB connection.`
- A workaround with an exit: `// Workaround for some-lib#12345; remove after 4.2.`
- Tool directives (`// eslint-disable-next-line`, `# noqa: E501`, `//nolint`, `// NOSONAR`) and the repo's own `// given / when / then` convention.

Before writing even that sentence, check whether a name could carry it: `findOrEmptyOnBlankBody()`, a constant `MAX_WEBHOOK_RETRY_DAYS`, a test named `rejects_partial_address`.

The same rules hold in every language. Only the comment syntax and the doc-comment linters differ.

**Compressing an essay:**

```ts
// Before (4 lines)
// We debounce here because the search endpoint is rate-limited to 10 requests per second per
// user, and in the March incident fast typists on the admin page tripped the limit and got
// 429s that the UI showed as "no results". 300ms was picked after trying 150ms and 500ms; 150
// still tripped it on slow networks and 500 felt laggy in user testing.
const search = debounce(runSearch, 300);

// After (1 line). The fact that prevents a wrong edit survives; the story goes to the PR.
// The search API allows 10 req/s per user; shorter delays trip it while typing.
const search = debounce(runSearch, 300);
```

## Doc comments (Javadoc, JSDoc, docstrings, `///`, …)

Write the minimum the project's linters require, which is usually none. Check what is actually configured and enforced before writing any:

| Ecosystem | Where to look | Rules that *require* doc comments |
|---|---|---|
| Java | Checkstyle config (often `config/checkstyle/checkstyle.xml`) and whether the build applies it | `JavadocVariable`, `MissingJavadocMethod`, `MissingJavadocType` (details below) |
| TS/JS | ESLint config | `jsdoc/require-jsdoc`. If any JSDoc exists, `jsdoc/require-param`/`require-returns` may demand full tags, so prefer none. |
| Python | `ruff`/`pydocstyle` config (`pyproject.toml`, `setup.cfg`) | `D100`–`D107` (missing docstrings). A one-line `"""Summary."""` satisfies them. |
| Go | `golangci-lint` / `revive` | `exported`: one line starting with the identifier's name |
| Rust | `#![warn(missing_docs)]` / clippy | `missing_docs`: one `///` line |
| Kotlin | detekt | `UndocumentedPublicClass`/`UndocumentedPublicFunction` |
| C# | `GenerateDocumentationFile` + CS1591 | one-line `<summary>` |

If nothing enforces doc comments, write none. Library code with external consumers is the exception: give a public symbol one line only when its contract (units, nullability, side effects, thrown errors) isn't obvious from the signature.

**Java Checkstyle specifics**, verified against Checkstyle 10.26:

- **`JavadocVariable`**: every field needs Javadoc. Write one line ending in a period (`JavadocStyle` checks that), saying something the name doesn't if you can: `/** Bookable start times, local to {@link #zone}. */`
- **`JavadocMethod` without `MissingJavadocMethod`**: method Javadoc is optional, so don't write any. A method that does have Javadoc fails unless it has every `@param` and `@return`, so a lean one-liner isn't possible.
- **`MissingJavadocMethod`/`MissingJavadocType`**: one summary sentence plus the required tags, nothing more.
- **No Javadoc modules**: no Javadoc.

## Existing comments

Don't rewrite comments outside the code you're changing, because that's diff noise. There is one exception: if your change makes a nearby comment false, fix or delete it. Don't take surrounding essay-style comments as the density to match.

## Cleanup pass (`/lean-comments`)

When asked to trim comments, or when invoked as `/lean-comments [path]`:

1. **Scope.** Use the given path. Otherwise use the working-tree diff (`git diff -U0 HEAD`, plus untracked files from `git status --porcelain`). Touch only comments the diff added, unless the user asked for a whole-file or whole-repo sweep.
2. **Decide** for each comment:
   - **Delete** it if it matches the table above.
   - **Compress** it to one sentence if it holds a real constraint.
   - **Keep** it if it's already one useful sentence.

   When unsure, compress rather than keep.
3. **Hand off what you cut.** If you removed reasoning that reviewers should still see (design rationale, ticket context), offer it to the user as a few lines for the PR description instead of discarding it.
4. **Verify.** Run the project's formatter and linters (Spotless/Checkstyle, ESLint/Prettier, ruff, golangci-lint and so on). Trimming doc comments can trip doc-format rules.
5. **Report** briefly: how many comments you deleted and compressed, and anything borderline you kept, with `file:line`.

## The hook

A PostToolUse hook (wired up by the plugin) checks the comments each file edit *adds*. It flags any of:
- 3 or more consecutive `//` or `#` lines
- a doc block or docstring with more than 2 prose lines (tag lines don't count)
- history or ticket-chain wording
- comment lines above about 20% of the added code (minimum 3)

One-line Javadoc and tool directives are exempt.

When it fires, compress or delete what it lists, following the rules above. It's a heuristic. If a flagged comment really is essential as written (a required multi-tag Javadoc, say), keep it, say so in one line, and move on. To silence it for a session, set `CLAUDE_LEAN_COMMENTS=off`.
