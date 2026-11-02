use fancy_regex::Regex as FancyRegex;
use regex::Regex;
use serde_json::{json, Value};
use std::collections::HashSet;
use std::env;
use std::io::{Read, Write};
use std::sync::LazyLock;

const RULE: &str = include_str!("../../hooks/comment-rule.md");
const C_STYLE: &[&str] = &[
    "java", "kt", "kts", "groovy", "gradle", "scala", "ts", "tsx", "js", "jsx", "mjs", "cjs", "go", "rs", "swift",
    "c", "h", "cc", "cpp", "hpp", "cs", "dart", "php", "scss",
];
const HASH: &[&str] = &["py", "sh", "bash", "zsh", "rb", "pl", "r", "tf"];
const LINE_RATIO: f64 = 0.2;
const MIN_LINE_COMMENTS: usize = 3;
const MAX_RUN: usize = 2;
const MAX_BLOCK_PROSE: usize = 2;
const MAX_FILES_REPORTED: usize = 5;
const PATCH_START: &str = "*** Begin Patch";
const ADVICE: &str = "Cut each to one sentence or delete it. Reasoning, history, ticket chains and design rationale \
belong in the commit or PR description, not the code. Keep only what a reader would otherwise get wrong, plus Javadoc \
a linter requires. If a flagged comment is genuinely essential as written, leave it and carry on.";

static SKIP_PATH: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"/(\.claude|\.codex|\.copilot|\.agents|skills|build/generated|node_modules|vendor|dist)/").unwrap()
});
static EXEMPT: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(concat!(
        r"(?i)^\s*(//|#|--)\s*(NOSONAR|noinspection|eslint|prettier-ignore|@ts-|noqa|type:|",
        r"pylint|shellcheck|go:|nolint|CHECKSTYLE|spotless|language=|given|when|then|arrange|act|assert)\b"
    ))
    .unwrap()
});
static STRINGS: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r#""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`[^`]*`"#).unwrap());
static HASH_TRAILING: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"(^|\s)#").unwrap());
static DOC_PREFIX: LazyLock<Regex> = LazyLock::new(|| Regex::new(r#"^(/\*\*?|\*/|\*|"""|''')\s*"#).unwrap());
static TODO_TICKET: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"TODO\((\S+?)\)").unwrap());
static HISTORY: LazyLock<FancyRegex> = LazyLock::new(|| {
    FancyRegex::new(concat!(
        r"(?i)\b(previously|no longer (carr|support|use|need|send|return|ship|call|accept|require|has|have)\w*|",
        r"(?<!\bis )(?<!\bare )(?<!\bbe )(?<!\bwas )(?<!\bwere )(?<!\bbeen )used to|",
        r"earlier (attempt|version)|was (changed|renamed|moved)|is now|are now|now (uses|only|a|an|the))\b"
    ))
    .unwrap()
});
static TICKET: LazyLock<FancyRegex> = LazyLock::new(|| {
    FancyRegex::new(r"\b(?!(?:UTF|RFC|SHA|ISO|AES|MD|HTTP|TLS|X)-)[A-Z][A-Z0-9]+-\d+\b").unwrap()
});

type Pairs = Vec<(String, String)>;

#[derive(Clone, Copy, PartialEq)]
enum Lang {
    C,
    Hash,
    Sql,
}

#[derive(Default)]
struct Analysis {
    line_comments: Vec<String>,
    runs: Vec<Vec<String>>,
    code: usize,
    blocks: Vec<Vec<String>>,
}

fn is_space(c: char) -> bool {
    c.is_whitespace() || ('\x1c'..='\x1f').contains(&c)
}

fn strip(s: &str) -> &str {
    s.trim_matches(is_space)
}

fn truncate(s: &str, max: usize) -> String {
    s.chars().take(max).collect()
}

fn split_lines(text: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut chars = text.char_indices().peekable();
    while let Some((i, c)) = chars.next() {
        if matches!(c, '\n' | '\r' | '\x0b' | '\x0c' | '\x1c' | '\x1d' | '\x1e' | '\u{85}' | '\u{2028}' | '\u{2029}') {
            lines.push(&text[start..i]);
            if c == '\r' && matches!(chars.peek(), Some((_, '\n'))) {
                chars.next();
            }
            start = chars.peek().map_or(text.len(), |(next, _)| *next);
        }
    }
    if start < text.len() {
        lines.push(&text[start..]);
    }
    lines
}

fn analyze(text: &str, lang: Lang) -> Analysis {
    let marker = match lang {
        Lang::C => "//",
        Lang::Hash => "#",
        Lang::Sql => "--",
    };
    let mut out = Analysis::default();
    let mut block: Option<Vec<String>> = None;
    let mut run: Vec<String> = Vec::new();
    let mut closer = "";

    for raw in split_lines(text) {
        let line = strip(raw);
        if let Some(open) = block.as_mut() {
            open.push(line.to_string());
            if line.contains(closer) {
                out.blocks.extend(block.take());
            }
            continue;
        }
        if line.is_empty() {
            end_run(&mut run, &mut out.runs);
            continue;
        }
        let opener = if lang != Lang::Hash && line.starts_with("/*") {
            closer = "*/";
            Some("/*")
        } else if lang == Lang::Hash && line.starts_with("\"\"\"") {
            closer = "\"\"\"";
            Some("\"\"\"")
        } else if lang == Lang::Hash && line.starts_with("'''") {
            closer = "'''";
            Some("'''")
        } else {
            None
        };
        if let Some(opener) = opener {
            end_run(&mut run, &mut out.runs);
            if line[opener.len()..].contains(closer) {
                if !line.starts_with("/**") {
                    out.blocks.push(vec![line.to_string()]);
                }
            } else {
                block = Some(vec![line.to_string()]);
            }
            continue;
        }
        if lang == Lang::Hash && line.starts_with("#!") {
            continue;
        }
        if line.starts_with(marker) {
            if !EXEMPT.is_match(line) {
                out.line_comments.push(line.to_string());
                run.push(line.to_string());
            }
            continue;
        }
        end_run(&mut run, &mut out.runs);
        out.code += 1;
        let bare = STRINGS.replace_all(line, "\"\"");
        let trailing = if lang == Lang::Hash {
            HASH_TRAILING.find(&bare).map(|m| m.start())
        } else {
            bare.find(marker)
        };
        if let Some(start) = trailing {
            if !EXEMPT.is_match(strip(&bare[start..])) {
                out.line_comments.push(line.to_string());
            }
        }
    }
    end_run(&mut run, &mut out.runs);
    out
}

fn end_run(run: &mut Vec<String>, runs: &mut Vec<Vec<String>>) {
    if !run.is_empty() {
        runs.push(std::mem::take(run));
    }
}

fn prose_lines(block: &[String]) -> Vec<String> {
    let body: Vec<String> = block
        .iter()
        .map(|line| {
            let unprefixed = DOC_PREFIX.replace(line, "").replace("*/", "");
            strip_prose(&unprefixed).to_string()
        })
        .collect();
    let tags = body.iter().position(|l| l.starts_with('@')).unwrap_or(body.len());
    body[..tags].iter().filter(|l| !l.is_empty()).cloned().collect()
}

fn strip_prose(s: &str) -> &str {
    s.trim_matches([' ', '"', '\''])
}

fn lang_for(path: &str) -> Option<Lang> {
    let ext = path.rsplit_once('.').map(|(_, ext)| ext.to_lowercase())?;
    if C_STYLE.contains(&ext.as_str()) {
        Some(Lang::C)
    } else if HASH.contains(&ext.as_str()) {
        Some(Lang::Hash)
    } else if ext == "sql" {
        Some(Lang::Sql)
    } else {
        None
    }
}

fn narrates_history(text: &str) -> bool {
    if HISTORY.is_match(text).unwrap_or(false) {
        return true;
    }
    let todo: HashSet<&str> = TODO_TICKET.captures_iter(text).filter_map(|c| c.get(1)).map(|m| m.as_str()).collect();
    let tickets: HashSet<&str> =
        TICKET.find_iter(text).filter_map(Result::ok).map(|m| m.as_str()).filter(|t| !todo.contains(t)).collect();
    tickets.len() > 1
}

fn findings_for(pairs: &[(String, String)], lang: Lang) -> Vec<String> {
    let (mut added, mut code, mut long_runs, mut long_blocks) = (Vec::new(), 0, Vec::new(), Vec::new());
    for (old, new) in pairs {
        let before = analyze(old, lang);
        let after = analyze(new, lang);
        let seen: HashSet<&String> = before.line_comments.iter().collect();
        added.extend(after.line_comments.iter().filter(|c| !seen.contains(c)).cloned());
        code += after.code;
        let old_runs: HashSet<String> = before.runs.iter().map(|r| r.join("\n")).collect();
        long_runs.extend(after.runs.iter().filter(|r| r.len() > MAX_RUN && !old_runs.contains(&r.join("\n"))).cloned());
        let old_blocks: HashSet<String> = before.blocks.iter().map(|b| b.join("\n")).collect();
        long_blocks.extend(after.blocks.iter().filter(|b| !old_blocks.contains(&b.join("\n"))).filter(|b| {
            let prose = prose_lines(b);
            prose.len() > MAX_BLOCK_PROSE || prose.iter().any(|l| l.starts_with("<p>"))
        }).cloned());
    }

    let mut out = Vec::new();
    if added.len() >= MIN_LINE_COMMENTS && added.len() as f64 > LINE_RATIO * code.max(1) as f64 {
        out.push(format!("{} comment lines added against {} lines of code, e.g.:", added.len(), code));
        out.extend(added.iter().take(5).map(|c| format!("  {}", truncate(c, 120))));
    }
    for run in long_runs.iter().take(3) {
        out.push(format!("{}-line comment paragraph: {}", run.len(), truncate(&run[0], 100)));
    }
    for block in long_blocks.iter().take(3) {
        let prose = prose_lines(block);
        out.push(format!("{}-line doc/block comment: {}", prose.len(), truncate(&prose[0], 100)));
    }
    let texts = added.iter().cloned().chain(long_blocks.iter().map(|b| prose_lines(b).join(" ")));
    let history = texts.filter(|t| narrates_history(t));
    out.extend(history.take(3).map(|t| format!("history/ticket narration: {}", truncate(&t, 100))));
    out
}

fn add_pair(files: &mut Vec<(String, Pairs)>, path: &str, pair: (String, String)) {
    match files.iter_mut().find(|(p, _)| p == path) {
        Some((_, pairs)) => pairs.push(pair),
        None => files.push((path.to_string(), vec![pair])),
    }
}

fn parse_patch(text: &str) -> Vec<(String, Pairs)> {
    let mut files = Vec::new();
    let mut path: Option<String> = None;
    let (mut old, mut new): (Vec<&str>, Vec<&str>) = (Vec::new(), Vec::new());

    fn end_hunk(files: &mut Vec<(String, Pairs)>, path: &Option<String>, old: &mut Vec<&str>, new: &mut Vec<&str>) {
        if let Some(p) = path {
            if !old.is_empty() || !new.is_empty() {
                add_pair(files, p, (old.join("\n"), new.join("\n")));
            }
        }
        old.clear();
        new.clear();
    }

    for line in split_lines(text) {
        if line.starts_with("*** Add File: ") || line.starts_with("*** Update File: ") || line.starts_with("*** Move to: ") {
            end_hunk(&mut files, &path, &mut old, &mut new);
            let target = strip(line.split_once(": ").map_or("", |(_, p)| p));
            path = (!target.is_empty()).then(|| target.to_string());
        } else if line.starts_with("*** Delete File: ") {
            end_hunk(&mut files, &path, &mut old, &mut new);
            path = None;
        } else if line.starts_with("***") || line.starts_with("@@") {
            end_hunk(&mut files, &path, &mut old, &mut new);
        } else if path.is_some() {
            let mut chars = line.chars();
            let first = chars.next();
            let body = chars.as_str();
            match first {
                Some('+') => new.push(body),
                Some('-') => old.push(body),
                _ => {
                    old.push(body);
                    new.push(body);
                }
            }
        }
    }
    end_hunk(&mut files, &path, &mut old, &mut new);
    files
}

fn truthy(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64() != Some(0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

fn text_field(input: &Value, primary: &str, secondary: Option<&str>) -> Result<String, ()> {
    let value = input.get(primary).or_else(|| secondary.and_then(|key| input.get(key)));
    match value {
        None => Ok(String::new()),
        Some(Value::String(s)) => Ok(s.clone()),
        Some(_) => Err(()),
    }
}

// Judge by payload shape: the same tool name carries different shapes across agents and models.
fn edits_by_file(event: &Value) -> Result<Vec<(String, Pairs)>, ()> {
    if !event.is_object() {
        return Err(());
    }
    let empty = json!({});
    let raw = event.get("tool_input").or_else(|| event.get("toolArgs")).unwrap_or(&empty);
    let parsed;
    let input = match raw.as_str().map(serde_json::from_str::<Value>) {
        Some(Ok(value)) => {
            parsed = value;
            &parsed
        }
        _ => raw,
    };
    let patch = if input.is_object() { input.get("command") } else { Some(input) };
    if let Some(body) = patch.and_then(Value::as_str) {
        if body.trim_start_matches(is_space).starts_with(PATCH_START) {
            return Ok(parse_patch(body));
        }
    }
    if !input.is_object() {
        return Ok(Vec::new());
    }
    let path_value = input.get("file_path").filter(|v| truthy(v)).or_else(|| input.get("path"));
    let Some(path_value) = path_value.filter(|v| truthy(v)) else {
        return Ok(Vec::new());
    };
    let path = path_value.as_str().ok_or(())?.to_string();
    if let Some(edits) = input.get("edits") {
        let mut pairs = Vec::new();
        for edit in edits.as_array().ok_or(())? {
            if !edit.is_object() {
                return Err(());
            }
            pairs.push((text_field(edit, "old_string", None)?, text_field(edit, "new_string", None)?));
        }
        return Ok(vec![(path, pairs)]);
    }
    let written = input.get("content").or_else(|| input.get("file_text")).filter(|v| !v.is_null());
    if let Some(written) = written {
        return Ok(vec![(path, vec![(String::new(), written.as_str().ok_or(())?.to_string())])]);
    }
    let old = text_field(input, "old_string", Some("old_str"))?;
    let new = text_field(input, "new_string", Some("new_str"))?;
    Ok(vec![(path, vec![(old, new)])])
}

fn sections_for(event: &Value) -> Result<Vec<String>, ()> {
    let files = edits_by_file(event)?;
    let cwd = event.get("cwd").and_then(Value::as_str).unwrap_or("").replace('\\', "/");
    let prefix = format!("{}/", cwd.trim_end_matches('/'));
    let mut sections = Vec::new();
    for (path, pairs) in &files {
        let shown = path.replace('\\', "/");
        let Some(lang) = lang_for(path) else { continue };
        if SKIP_PATH.is_match(&format!("/{shown}")) {
            continue;
        }
        let findings = findings_for(pairs, lang);
        if !findings.is_empty() {
            let name = if files.len() > 1 {
                shown.strip_prefix(prefix.as_str()).unwrap_or(&shown)
            } else {
                shown.rsplit('/').next().unwrap_or(&shown)
            };
            sections.push(format!("lean-comments: {name} has comments to trim.\n{}", findings.join("\n")));
        }
    }
    if sections.len() > MAX_FILES_REPORTED {
        let hidden = sections.len() - MAX_FILES_REPORTED;
        sections.truncate(MAX_FILES_REPORTED);
        sections.push(format!("lean-comments: {hidden} more files have comments to trim."));
    }
    Ok(sections)
}

fn is_off() -> bool {
    ["LEAN_COMMENTS", "CLAUDE_LEAN_COMMENTS"]
        .iter()
        .any(|name| env::var_os(name).is_some_and(|v| v.to_string_lossy().to_lowercase() == "off"))
}

fn is_copilot() -> bool {
    env::var_os("COPILOT_CLI").is_some_and(|v| !v.is_empty())
}

fn emit(value: &Value) {
    let _ = writeln!(std::io::stdout(), "{value}");
}

fn session_start() {
    if is_off() {
        return;
    }
    if is_copilot() {
        emit(&json!({"additionalContext": RULE}));
    } else {
        emit(&json!({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": RULE}}));
    }
}

fn post_tool_use() {
    if is_off() {
        return;
    }
    let mut input = Vec::new();
    if std::io::stdin().read_to_end(&mut input).is_err() {
        return;
    }
    let body = input.strip_prefix(b"\xef\xbb\xbf").unwrap_or(&input);
    let Ok(event) = serde_json::from_slice::<Value>(body) else { return };
    let Ok(sections) = sections_for(&event) else { return };
    if sections.is_empty() {
        return;
    }
    let reason = format!("{}\n{ADVICE}", sections.join("\n"));
    // Copilot documents only additionalContext for feeding postToolUse output to the model.
    if is_copilot() {
        emit(&json!({"additionalContext": reason}));
    } else {
        emit(&json!({"decision": "block", "reason": reason}));
    }
}

fn main() {
    let command = env::args().nth(1).unwrap_or_default();
    std::panic::set_hook(Box::new(|_| {}));
    // A linting bug must never fail the agent's edit, so panics end the hook quietly.
    let _ = std::panic::catch_unwind(|| match command.as_str() {
        "session-start" => session_start(),
        "post-tool-use" => post_tool_use(),
        other => {
            eprintln!("lean-comments: unknown command '{other}', expected session-start or post-tool-use");
            std::process::exit(1);
        }
    });
}
