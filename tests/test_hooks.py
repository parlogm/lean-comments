import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DENSITY = "post-tool-use"
SESSION_START = "session-start"
TURN_START = "user-prompt-submit"
TURN_END = "stop"
HOST_ENV = ("COPILOT_CLI", "LEAN_COMMENTS", "CLAUDE_LEAN_COMMENTS", "PLUGIN_DATA", "CLAUDE_PLUGIN_DATA")
BINARY = os.environ.get("LEAN_COMMENTS_BIN")
ESSAY = "// one\n// two\n// three\nint x = 1;\n"
PLUS_ESSAY = "+// one\n+// two\n+// three\n+int x = 1;\n"
CLEAN = "// The vendor returns 200 for unknown ids.\nint x = 1;\n"


def run(script, event=None, copilot=False, **env_extra):
    env = {k: v for k, v in os.environ.items() if k not in HOST_ENV}
    env.update(env_extra)
    if copilot:
        env["COPILOT_CLI"] = "1"
    payload = json.dumps(event if event is not None else {}).encode()
    launcher = [BINARY] if BINARY else ["sh", str(ROOT / "hooks/run")]
    done = subprocess.run([*launcher, script], input=payload, capture_output=True, env=env, check=True)
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
        self.assertIsNone(run(DENSITY, event, LEAN_COMMENTS="off"))

    def test_legacy_off_switch_still_silences_hook(self):
        event = {"tool_name": "Write", "tool_input": {"file_path": "/r/A.java", "content": ESSAY}}
        self.assertIsNone(run(DENSITY, event, CLAUDE_LEAN_COMMENTS="OFF"))

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
        self.assertIsNone(run(SESSION_START, LEAN_COMMENTS="off"))
        self.assertIsNone(run(SESSION_START, CLAUDE_LEAN_COMMENTS="off"))


def git(repo, *args, **env_extra):
    env = {**os.environ, **env_extra}
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def new_repo(root):
    repo = pathlib.Path(root, "repo")
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    for key, value in (("user.name", "Test"), ("user.email", "test@example.com"), ("core.autocrlf", "false")):
        git(repo, "config", key, value)
    (repo / "Base.java").write_text("class Base {}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base", GIT_COMMITTER_DATE="2001-01-01T00:00:00Z")
    return repo


class TurnCheck(unittest.TestCase):
    """Files changed outside the edit tools, as a shell command or script would, checked at the end of the turn."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = new_repo(self.tmp.name)
        self.data = pathlib.Path(self.tmp.name, "data")
        self.session = {"session_id": "s1", "cwd": str(self.repo)}

    def hook(self, script, event=None, **env_extra):
        return run(script, {**self.session, **(event or {})}, PLUGIN_DATA=str(self.data), **env_extra)

    def prompt(self, **env_extra):
        self.assertIsNone(self.hook(TURN_START, {"prompt": "go"}, **env_extra))

    def stop(self, active=False, **env_extra):
        return self.hook(TURN_END, {"stop_hook_active": active}, **env_extra)

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_file_written_by_a_script_is_flagged(self):
        self.prompt()
        self.write("src/A.java", ESSAY)
        out = self.stop()
        self.assertEqual(out["decision"], "block")
        self.assertTrue(out["reason"].startswith("lean-comments: end-of-turn check"))
        self.assertIn("A.java has comments to trim", out["reason"])
        self.assertIn("3-line comment paragraph: // one", out["reason"])

    def test_change_to_a_tracked_file_is_flagged(self):
        self.prompt()
        self.write("Base.java", "class Base {}\n" + ESSAY)
        self.assertEqual(self.stop()["decision"], "block")

    def test_clean_change_is_silent(self):
        self.prompt()
        self.write("A.java", CLEAN)
        self.assertIsNone(self.stop())

    def test_changes_made_before_the_prompt_are_ignored(self):
        self.write("A.java", ESSAY)
        self.prompt()
        self.write("B.java", CLEAN)
        self.assertIsNone(self.stop())

    def test_existing_essay_kept_by_the_turn_is_not_flagged(self):
        self.write("A.java", ESSAY)
        self.prompt()
        self.write("A.java", ESSAY + "int y = 2;\n")
        self.assertIsNone(self.stop())

    def test_deleted_file_is_ignored(self):
        self.write("A.java", ESSAY)
        self.prompt()
        (self.repo / "A.java").unlink()
        self.assertIsNone(self.stop())

    def test_continuation_it_forced_lets_the_turn_end(self):
        self.prompt()
        self.write("A.java", ESSAY)
        self.assertEqual(self.stop()["decision"], "block")
        self.write("B.java", ESSAY)
        self.assertIsNone(self.stop(active=True))

    def test_continuation_forced_by_another_hook_is_still_checked(self):
        self.prompt()
        self.write("A.java", CLEAN)
        self.assertIsNone(self.stop())
        self.write("B.java", ESSAY)
        out = self.stop(active=True)
        self.assertIn("B.java", out["reason"])
        self.assertNotIn("A.java", out["reason"])

    def test_turn_started_without_a_prompt_is_not_checked(self):
        self.prompt()
        self.assertIsNone(self.stop())
        self.write("A.java", ESSAY)
        self.assertIsNone(self.stop())
        self.assertIsNone(self.stop(active=True))

    def test_script_comments_in_a_file_later_edited_are_still_flagged(self):
        self.prompt()
        path = self.write("A.java", ESSAY)
        edit = {"tool_name": "Edit", "tool_input": {"file_path": str(path), "old_string": "int x = 1;", "new_string": "int x = 2;"}}
        path.write_text(ESSAY.replace("int x = 1;", "int x = 2;"))
        self.assertIsNone(self.hook(DENSITY, edit))
        self.assertEqual(self.stop()["decision"], "block")

    def test_reformatting_a_checked_edit_does_not_report_it_again(self):
        self.prompt()
        path = self.write("A.java", ESSAY)
        self.hook(DENSITY, {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": ESSAY}})
        path.write_text("    " + ESSAY.replace("\n", "\n    ") + "int y = 2;\n")
        self.assertIsNone(self.stop())

    def test_renamed_file_keeps_its_old_comments(self):
        self.write("A.java", ESSAY)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "a")
        self.prompt()
        git(self.repo, "mv", "A.java", "B.java")
        self.assertIsNone(self.stop())

    def test_file_moved_without_git_keeps_its_old_comments(self):
        self.write("A.java", ESSAY)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "a")
        self.prompt()
        (self.repo / "A.java").rename(self.repo / "B.java")
        self.assertIsNone(self.stop())

    def test_file_name_with_a_space_is_checked(self):
        self.prompt()
        self.write("my notes.java", ESSAY)
        self.assertIn("my notes.java has comments", self.stop()["reason"])

    def test_turn_during_a_merge_conflict_is_checked(self):
        self.write("README.md", "base\n")
        self.write("C.java", "class C {}\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "c")
        git(self.repo, "switch", "-q", "-c", "other")
        self.write("README.md", "other\n")
        self.write("C.java", "class C { int other; }\n")
        git(self.repo, "commit", "-q", "-am", "other")
        git(self.repo, "switch", "-q", "main")
        self.write("README.md", "main\n")
        self.write("C.java", "class C { int main; }\n")
        git(self.repo, "commit", "-q", "-am", "main")
        subprocess.run(["git", "-C", str(self.repo), "merge", "-q", "other"], capture_output=True)
        self.prompt()
        self.write("New.java", ESSAY)
        self.assertIn("New.java", self.stop()["reason"])

    def test_amended_commit_is_still_checked(self):
        self.write("A.java", CLEAN)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "a")
        self.prompt()
        self.write("A.java", CLEAN + ESSAY)
        git(self.repo, "commit", "-q", "-a", "--amend", "--no-edit")
        self.assertEqual(self.stop()["decision"], "block")

    def test_reset_to_an_older_commit_is_skipped(self):
        self.write("A.java", ESSAY)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "a")
        git(self.repo, "rm", "-q", "A.java")
        git(self.repo, "commit", "-q", "-m", "drop a")
        self.prompt()
        git(self.repo, "reset", "-q", "--hard", "HEAD~1")
        self.assertIsNone(self.stop())

    def test_entity_with_generated_ids_is_still_checked(self):
        self.prompt()
        self.write("Order.java", "@Entity\nclass Order {\n  @Id @GeneratedValue Long id;\n  boolean isAutoGenerated;\n" + ESSAY + "}\n")
        self.assertEqual(self.stop()["decision"], "block")

    def test_each_turn_is_reported_once(self):
        self.prompt()
        self.write("A.java", ESSAY)
        self.assertEqual(self.stop()["decision"], "block")
        self.assertIsNone(self.stop())

    def test_stop_without_a_prompt_snapshot_is_silent(self):
        self.write("A.java", ESSAY)
        self.assertIsNone(self.stop())

    def test_file_already_checked_by_the_edit_hook_is_not_reported_again(self):
        self.prompt()
        path = self.write("A.java", ESSAY)
        edit = {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": ESSAY}}
        self.assertEqual(self.hook(DENSITY, edit)["decision"], "block")
        self.assertIsNone(self.stop())

    def test_script_change_after_a_checked_edit_is_still_flagged(self):
        self.prompt()
        path = self.write("A.java", CLEAN)
        self.assertIsNone(self.hook(DENSITY, {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": CLEAN}}))
        self.write("A.java", CLEAN + ESSAY)
        self.assertEqual(self.stop()["decision"], "block")

    def test_commit_made_during_the_turn_is_still_checked(self):
        self.prompt()
        self.write("A.java", ESSAY)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "add A")
        self.assertEqual(self.stop()["decision"], "block")

    def test_switching_to_an_existing_branch_is_skipped(self):
        git(self.repo, "switch", "-q", "-c", "other")
        self.write("A.java", ESSAY)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "teammate", GIT_COMMITTER_DATE="2001-01-02T00:00:00Z")
        git(self.repo, "switch", "-q", "main")
        self.prompt()
        git(self.repo, "switch", "-q", "other")
        self.assertIsNone(self.stop())

    def test_generated_file_is_skipped(self):
        self.prompt()
        self.write("Gen.java", "// Code generated by protoc-gen-go. DO NOT EDIT.\n" + ESSAY)
        self.assertIsNone(self.stop())

    def test_ignored_file_is_skipped(self):
        self.write(".gitignore", "out/\n")
        self.prompt()
        self.write("out/A.java", ESSAY)
        self.assertIsNone(self.stop())

    def test_mass_change_is_skipped(self):
        self.prompt()
        for i in range(41):
            self.write(f"pkg/m{i}/A.java", ESSAY)
        self.assertIsNone(self.stop())

    def test_large_file_is_left_out_of_the_snapshot(self):
        self.prompt()
        self.write("dump.sql", "-- one\n-- two\n-- three\n" + "insert into t values (1);\n" * 90000)
        self.assertIsNone(self.stop())

    def test_files_checked_by_the_edit_hook_do_not_count_toward_the_mass_change_limit(self):
        self.prompt()
        for i in range(40):
            path = self.write(f"pkg/m{i}/A.java", CLEAN)
            self.hook(DENSITY, {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": CLEAN}})
        self.write("B.java", ESSAY)
        self.assertIn("B.java", self.stop()["reason"])

    def test_several_files_are_named_by_repo_path(self):
        self.prompt()
        self.write("a/Main.java", ESSAY)
        self.write("b/Main.java", ESSAY)
        reason = self.stop()["reason"]
        self.assertIn("lean-comments: a/Main.java has comments", reason)
        self.assertIn("lean-comments: b/Main.java has comments", reason)

    def test_user_index_is_left_alone(self):
        self.prompt()
        self.write("A.java", ESSAY)
        self.stop()
        status = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"], capture_output=True, text=True)
        self.assertEqual(status.stdout, "?? A.java\n")

    def test_abandoned_snapshot_skips_the_turn(self):
        self.prompt()
        pending = self.data / "turns" / "s1" / "pending"
        pending.write_text("")
        os.utime(pending, (0, 0))
        self.write("A.java", ESSAY)
        self.assertIsNone(self.stop())

    def test_outside_a_git_repo_nothing_happens(self):
        plain = pathlib.Path(self.tmp.name, "plain")
        plain.mkdir()
        self.session["cwd"] = str(plain)
        self.prompt()
        (plain / "A.java").write_text(ESSAY)
        self.assertIsNone(self.stop())

    def test_off_switch_silences_the_check(self):
        self.prompt()
        self.write("A.java", ESSAY)
        self.assertIsNone(self.stop(LEAN_COMMENTS="off"))

    def test_copilot_camel_case_session_gets_a_block_decision(self):
        self.session = {"sessionId": "s2", "cwd": str(self.repo)}
        self.assertIsNone(self.hook(TURN_START, {"prompt": "go"}, COPILOT_CLI="1"))
        self.write("A.java", ESSAY)
        out = self.hook(TURN_END, {"stop_hook_active": False}, COPILOT_CLI="1")
        self.assertEqual(out["decision"], "block")


class HookWiring(unittest.TestCase):
    EDIT = json.dumps({"tool_name": "Write", "tool_input": {"file_path": "/r/A.java", "content": ESSAY}}).encode()

    def handlers(self):
        config = json.loads((ROOT / "hooks/hooks.json").read_text())
        return {name: groups[0]["hooks"][0] for name, groups in config["hooks"].items()}

    def launch(self, argv):
        env = {k: v for k, v in os.environ.items() if k not in HOST_ENV}
        results = {}
        for name, payload in (("SessionStart", b"{}"), ("PostToolUse", self.EDIT)):
            done = subprocess.run(argv(self.handlers()[name]), input=payload, capture_output=True, env=env, check=True)
            results[name] = json.loads(done.stdout)
        self.assertIn("Default to no comment", results["SessionStart"]["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(results["PostToolUse"]["decision"], "block")

    def filled(self, command):
        return command.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT))

    def test_posix_command_runs_through_sh(self):
        self.launch(lambda handler: ["sh", "-c", self.filled(handler["command"])])

    def test_turn_check_runs_through_sh(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = new_repo(tmp)
            env = {k: v for k, v in os.environ.items() if k not in HOST_ENV}
            env["PLUGIN_DATA"] = str(pathlib.Path(tmp, "data"))
            session = {"session_id": "w1", "cwd": str(repo)}

            def call(name, extra):
                argv = ["sh", "-c", self.filled(self.handlers()[name]["command"])]
                payload = json.dumps({**session, **extra}).encode()
                return subprocess.run(argv, input=payload, capture_output=True, env=env, check=True).stdout

            self.assertEqual(call("UserPromptSubmit", {"prompt": "go"}), b"")
            (repo / "A.java").write_text(ESSAY)
            self.assertEqual(json.loads(call("Stop", {"stop_hook_active": False}))["decision"], "block")

    @unittest.skipUnless(sys.platform == "win32", "Windows shells")
    def test_codex_command_runs_through_cmd_the_way_codex_starts_it(self):
        self.launch(lambda handler: f'cmd.exe /C "{self.filled(handler["commandWindows"])}"')

    @unittest.skipUnless(sys.platform == "win32", "Windows shells")
    def test_copilot_command_runs_through_powershell(self):
        self.launch(lambda handler: ["powershell", "-NoProfile", "-Command", self.filled(handler["powershell"])])

    @unittest.skipIf(sys.platform == "win32", "needs a fake uname on PATH")
    def test_unknown_platform_reports_the_failure(self):
        with tempfile.TemporaryDirectory() as fake_bin:
            uname = pathlib.Path(fake_bin, "uname")
            uname.write_text("#!/bin/sh\necho Plan9\n")
            uname.chmod(0o755)
            env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"}
            done = subprocess.run(["sh", str(ROOT / "hooks/run"), "session-start"], capture_output=True, env=env)
        self.assertEqual(done.returncode, 1)
        self.assertIn(b"no build for Plan9", done.stderr)

    def test_unknown_command_reports_the_failure(self):
        launcher = [BINARY] if BINARY else ["sh", str(ROOT / "hooks/run")]
        done = subprocess.run([*launcher, "nope"], capture_output=True)
        self.assertEqual(done.returncode, 1)
        self.assertIn(b"unknown command", done.stderr)


if __name__ == "__main__":
    unittest.main()
