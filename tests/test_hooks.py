import json
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DENSITY = ROOT / "skills/lean-comments/scripts/comment_density.py"
SESSION_START = ROOT / "hooks/session_start.py"
ESSAY = "// one\n// two\n// three\nint x = 1;\n"
PLUS_ESSAY = "+// one\n+// two\n+// three\n+int x = 1;\n"
CLEAN = "// The vendor returns 200 for unknown ids.\nint x = 1;\n"


def run(script, event=None, copilot=False, **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in ("COPILOT_CLI", "CLAUDE_LEAN_COMMENTS")}
    env.update(env_extra)
    if copilot:
        env["COPILOT_CLI"] = "1"
    payload = json.dumps(event if event is not None else {}).encode()
    done = subprocess.run([sys.executable, str(script)], input=payload, capture_output=True, env=env, check=True)
    return json.loads(done.stdout) if done.stdout.strip() else None


def patch(*body):
    return "*** Begin Patch\n" + "\n".join(body) + "\n*** End Patch\n"


class ClaudePayloads(unittest.TestCase):
    def test_edit_flag_blocks_with_reason(self):
        out = run(DENSITY, {"tool_name": "Edit", "tool_input": {"file_path": "/r/A.java", "old_string": "", "new_string": ESSAY}})
        self.assertEqual(out["decision"], "block")
        self.assertTrue(out["reason"].startswith("lean-comments: A.java has comments to trim.\n"))
        self.assertIn("3-line comment paragraph: // one", out["reason"])

    def test_write_is_flagged(self):
        out = run(DENSITY, {"tool_name": "Write", "tool_input": {"file_path": "/r/A.java", "content": ESSAY}})
        self.assertEqual(out["decision"], "block")

    def test_multiedit_is_flagged(self):
        edits = [{"old_string": "", "new_string": ESSAY}]
        out = run(DENSITY, {"tool_name": "MultiEdit", "tool_input": {"file_path": "/r/A.java", "edits": edits}})
        self.assertEqual(out["decision"], "block")

    def test_existing_essay_kept_by_edit_is_not_flagged(self):
        event = {"tool_name": "Edit", "tool_input": {"file_path": "/r/A.java", "old_string": ESSAY, "new_string": ESSAY + "int y;\n"}}
        self.assertIsNone(run(DENSITY, event))

    def test_clean_edit_is_silent(self):
        event = {"tool_name": "Write", "tool_input": {"file_path": "/r/A.java", "content": CLEAN}}
        self.assertIsNone(run(DENSITY, event))

    def test_off_switch_silences_hook(self):
        event = {"tool_name": "Write", "tool_input": {"file_path": "/r/A.java", "content": ESSAY}}
        self.assertIsNone(run(DENSITY, event, CLAUDE_LEAN_COMMENTS="off"))

    def test_windows_skip_path_is_respected(self):
        event = {"tool_name": "Write", "tool_input": {"file_path": "C:\\r\\node_modules\\A.java", "content": ESSAY}}
        self.assertIsNone(run(DENSITY, event))


class CodexPayloads(unittest.TestCase):
    def event(self, body):
        return {"tool_name": "apply_patch", "turn_id": "t", "tool_input": {"command": body}}

    def test_added_file_is_flagged_with_block(self):
        out = run(DENSITY, self.event(patch("*** Add File: src/A.java", PLUS_ESSAY.rstrip())))
        self.assertEqual(out["decision"], "block")
        self.assertIn("A.java", out["reason"])

    def test_context_essay_in_update_is_not_flagged(self):
        body = patch("*** Update File: A.java", "@@", " // one", " // two", " // three", "-int x = 1;", "+int x = 2;")
        self.assertIsNone(run(DENSITY, self.event(body)))

    def test_only_flagged_files_of_a_multi_file_patch_are_named(self):
        body = patch("*** Add File: Clean.java", "+int x = 1;", "*** Add File: Essay.java", PLUS_ESSAY.rstrip())
        reason = run(DENSITY, self.event(body))["reason"]
        self.assertIn("Essay.java", reason)
        self.assertNotIn("Clean.java", reason)

    def test_each_file_uses_its_own_comment_syntax(self):
        body = patch("*** Add File: a.py", "+# one", "+# two", "+# three", "+x = 1")
        self.assertIn("a.py", run(DENSITY, self.event(body))["reason"])

    def test_moved_file_uses_destination_language(self):
        body = patch("*** Update File: notes.txt", "*** Move to: A.java", "@@", PLUS_ESSAY.rstrip())
        self.assertIn("A.java", run(DENSITY, self.event(body))["reason"])

    def test_deleted_file_is_ignored(self):
        body = patch("*** Delete File: A.java")
        self.assertIsNone(run(DENSITY, self.event(body)))

    def test_relative_skip_path_is_respected(self):
        body = patch("*** Add File: node_modules/A.java", PLUS_ESSAY.rstrip())
        self.assertIsNone(run(DENSITY, self.event(body)))

    def test_shell_command_is_ignored(self):
        event = {"tool_name": "Bash", "tool_input": {"command": "echo '// one'"}}
        self.assertIsNone(run(DENSITY, event))


class MultiFilePatches(unittest.TestCase):
    def reason(self, *paths):
        body = [line for path in paths for line in (f"*** Add File: {path}", PLUS_ESSAY.rstrip())]
        return run(DENSITY, {"tool_name": "apply_patch", "tool_input": {"command": patch(*body)}})["reason"]

    def test_same_named_files_are_labelled_by_their_patch_paths(self):
        reason = self.reason("pkg/a/Main.java", "pkg/b/Main.java")
        self.assertIn("lean-comments: pkg/a/Main.java has comments", reason)
        self.assertIn("lean-comments: pkg/b/Main.java has comments", reason)

    def test_absolute_patch_paths_are_labelled_relative_to_cwd(self):
        body = [line for path in ("/r/a/Main.java", "/r/b/Main.java") for line in (f"*** Add File: {path}", PLUS_ESSAY.rstrip())]
        event = {"cwd": "/r", "toolName": "apply_patch", "toolArgs": patch(*body)}
        reason = run(DENSITY, event)["reason"]
        self.assertIn("lean-comments: a/Main.java has comments", reason)
        self.assertIn("lean-comments: b/Main.java has comments", reason)

    def test_report_stops_at_five_files_and_counts_the_rest(self):
        reason = self.reason(*[f"pkg/m{i}/Main.java" for i in range(30)])
        self.assertEqual(reason.count("has comments to trim."), 5)
        self.assertIn("lean-comments: 25 more files have comments to trim.", reason)
        self.assertIn("Cut each to one sentence", reason)

    def test_exactly_five_files_have_no_overflow_line(self):
        reason = self.reason(*[f"pkg/m{i}/Main.java" for i in range(5)])
        self.assertNotIn("more files", reason)


class MalformedPayloads(unittest.TestCase):
    def test_each_is_ignored_without_output_or_failure(self):
        events = [
            {"tool_name": "edit", "tool_input": {"path": "a.py", "old_str": None, "new_str": "x"}},
            {"tool_name": "MultiEdit", "tool_input": {"file_path": "a.py", "edits": ["x"]}},
            {"tool_name": "MultiEdit", "tool_input": {"file_path": "a.py", "edits": None}},
            {"tool_name": "Write", "tool_input": {"file_path": 5, "content": "x"}},
            {"tool_name": "Write", "tool_input": None},
            ["not", "an", "object"],
        ]
        for event in events:
            with self.subTest(event=event):
                self.assertIsNone(run(DENSITY, event))


class CopilotPayloads(unittest.TestCase):
    def assert_flagged(self, event):
        out = run(DENSITY, event, copilot=True)
        self.assertEqual(list(out), ["additionalContext"])
        self.assertIn("lean-comments:", out["additionalContext"])

    def test_camel_case_patch_string(self):
        self.assert_flagged({"toolName": "apply_patch", "toolArgs": patch("*** Add File: A.java", PLUS_ESSAY.rstrip())})

    def test_pascal_case_patch_string(self):
        self.assert_flagged({"tool_name": "Edit", "tool_input": patch("*** Add File: A.java", PLUS_ESSAY.rstrip())})

    def test_camel_case_create_with_json_string_args(self):
        args = json.dumps({"path": "/r/A.java", "file_text": ESSAY})
        self.assert_flagged({"toolName": "create", "toolArgs": args})

    def test_pascal_case_edit_with_copilot_field_names(self):
        self.assert_flagged({"tool_name": "edit", "tool_input": {"path": "/r/A.java", "old_str": "", "new_str": ESSAY}})

    def test_view_is_ignored(self):
        self.assertIsNone(run(DENSITY, {"toolName": "view", "toolArgs": {"path": "/r/A.java"}}, copilot=True))


class SessionStart(unittest.TestCase):
    def test_claude_and_codex_get_nested_context(self):
        inner = run(SESSION_START)["hookSpecificOutput"]
        self.assertEqual(inner["hookEventName"], "SessionStart")
        self.assertIn("Default to no comment", inner["additionalContext"])

    def test_copilot_gets_top_level_context(self):
        self.assertIn("Default to no comment", run(SESSION_START, copilot=True)["additionalContext"])

    def test_off_switch_silences_rule(self):
        self.assertIsNone(run(SESSION_START, CLAUDE_LEAN_COMMENTS="off"))


class WindowsWiring(unittest.TestCase):
    def handlers(self):
        config = json.loads((ROOT / "hooks/hooks.json").read_text())
        return [h for groups in config["hooks"].values() for group in groups for h in group["hooks"]]

    def test_each_hook_launches_an_existing_script_from_both_windows_shells(self):
        launcher = '"${CLAUDE_PLUGIN_ROOT}\\hooks\\run-hook.cmd" '
        for handler in self.handlers():
            self.assertTrue(handler["commandWindows"].startswith(launcher))
            self.assertTrue(handler["powershell"].startswith("& " + launcher))
            script = handler["commandWindows"][len(launcher):].replace("\\", "/")
            self.assertTrue((ROOT / script).is_file(), script)
            self.assertTrue(handler["powershell"].endswith(handler["commandWindows"]))

    def test_unix_command_stays_on_python3(self):
        for handler in self.handlers():
            self.assertTrue(handler["command"].startswith('python3 "${CLAUDE_PLUGIN_ROOT}/'))

    def test_launcher_uses_crlf_and_tries_each_python_before_failing_visibly(self):
        raw = (ROOT / "hooks/run-hook.cmd").read_bytes()
        self.assertEqual(raw.count(b"\n"), raw.count(b"\r\n"))
        text = raw.decode()
        positions = [text.index(name + ' -c "') for name in ("py -3", "python", "python3")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("1>&2", text)
        self.assertTrue(text.rstrip().endswith("exit /b 1"))


if __name__ == "__main__":
    unittest.main()
