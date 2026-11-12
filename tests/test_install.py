"""Installer regression tests. Every installation runs in a disposable project."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


KIT = Path(__file__).resolve().parents[1]
RUNTIME = KIT / "fusion_guard"
sys.path.insert(0, str(RUNTIME))
import install as installer


def legacy_status():
    return "Fusion " + "".join(chr(n) for n in (21442, 25968, 21270, 24314, 27169, 26816, 26597))


def unrelated_hook():
    return {"type": "command", "command": "echo keep-me", "statusMessage": "Unrelated hook"}


class MergeTests(unittest.TestCase):
    def test_shell_quotes_preserve_spaces_and_apostrophes(self):
        self.assertEqual(installer.ps_quote("C:/project's files/hook.py"), "'C:/project''s files/hook.py'")

    def test_generated_hooks_are_synchronous_and_project_scoped(self):
        prepared = installer.config()
        self.assertEqual(set(prepared["hooks"]), {"PreToolUse", "PostToolUse", "Stop"})
        for event, groups in prepared["hooks"].items():
            self.assertEqual(len(groups), 1)
            group = groups[0]
            if event != "Stop":
                self.assertEqual(group["matcher"], "^mcp__fusion__.*$")
            else:
                self.assertNotIn("matcher", group)
            hook = group["hooks"][0]
            self.assertFalse(hook.get("async", False))
            self.assertIn(installer.ps_quote(RUNTIME / "hook.py"), hook["command"])
            self.assertIn(installer.ps_quote(sys.executable), hook["command"])
            self.assertEqual(hook["command"], hook["commandWindows"])
            self.assertIn("exit 2", hook["command"])

    def test_merge_preserves_unrelated_hook_inside_same_group(self):
        keep = unrelated_hook()
        existing = {"metadata": {"owner": "someone-else"}, "hooks": {
            "PreToolUse": [{"matcher": ".*", "groupMetadata": "retain", "hooks": [
                {"statusMessage": installer.STATUS, "command": "old guard"}, keep]}],
            "SessionStart": [{"hooks": [keep]}],
        }}
        original = copy.deepcopy(existing)
        merged = installer.merge_config(existing, installer.config())
        self.assertEqual(existing, original)
        self.assertEqual(merged["metadata"], original["metadata"])
        self.assertEqual(merged["hooks"]["SessionStart"], original["hooks"]["SessionStart"])
        preserved = merged["hooks"]["PreToolUse"][0]
        self.assertEqual(preserved, {"matcher": ".*", "groupMetadata": "retain", "hooks": [keep]})
        self.assertEqual(len(merged["hooks"]["PreToolUse"]), 2)

    def test_merge_is_idempotent_and_drops_only_guard_entries(self):
        prepared = installer.config()
        existing = {"hooks": {"PreToolUse": [{"matcher": "other", "hooks": [unrelated_hook()]}]}}
        first = installer.merge_config(existing, prepared)
        second = installer.merge_config(first, prepared)
        self.assertEqual(first, second)
        for event in prepared["hooks"]:
            owned = [h for g in second["hooks"][event] for h in g["hooks"] if installer.is_ours(h)]
            self.assertEqual(len(owned), 1)

    def test_legacy_localized_status_is_replaced_without_duplicates(self):
        old = {"statusMessage": legacy_status(), "command": "legacy guard"}
        self.assertTrue(installer.is_ours(old))
        self.assertFalse(installer.is_ours(unrelated_hook()))
        existing = {"hooks": {"PostToolUse": [{"matcher": ".*", "hooks": [old, unrelated_hook()]}]}}
        merged = installer.merge_config(existing, installer.config())
        self.assertEqual(merged["hooks"]["PostToolUse"][0]["hooks"], [unrelated_hook()])
        self.assertEqual(len(merged["hooks"]["PostToolUse"]), 2)

    def test_rules_replacement_preserves_surrounding_content(self):
        before = "Owner rules\n\n" + installer.BEGIN + "\nold\n" + installer.END + "\nTail rules\n"
        expected = "Owner rules\n\n" + installer.BEGIN + "\nnew\n" + installer.END + "\nTail rules\n"
        self.assertEqual(installer.rules_text(before, "new\n"), expected)
        self.assertEqual(installer.rules_text(expected, "new\n"), expected)

    def test_rules_append_when_markers_are_absent(self):
        result = installer.rules_text("Owner rules\n", "new")
        self.assertTrue(result.startswith("Owner rules\n\n" + installer.BEGIN))
        self.assertTrue(result.endswith(installer.END + "\n"))

    def test_malformed_rule_markers_are_rejected(self):
        malformed = [installer.BEGIN, installer.END,
                     installer.END + "\nold\n" + installer.BEGIN,
                     installer.BEGIN + installer.BEGIN + installer.END,
                     installer.BEGIN + installer.END + installer.END]
        for text in malformed:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    installer.rules_text(text, "new")


@unittest.skipUnless(sys.platform == "win32", "Installer integration targets Windows PowerShell")
class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent, prefix="installer-test-")
        self.sandbox = Path(self.temp.name)
        self.project = self.sandbox / "project's files"
        self.guard = self.project / "fusion_guard"
        self.guard.mkdir(parents=True)
        for name in ("hook.py", "install.py", "inspect_model.py", "policy.json", "AGENTS.project.md"):
            shutil.copy2(RUNTIME / name, self.guard / name)
        self.policy_before = (self.guard / "policy.json").read_bytes()
        self.assertFalse(json.loads(self.policy_before)["enabled"])
        self.hooks_path = self.project / ".codex" / "hooks.json"
        self.hooks_path.parent.mkdir()
        existing = {"keep": "root metadata", "hooks": {"PreToolUse": [{"matcher": ".*", "hooks": [
            {"statusMessage": legacy_status(), "command": "legacy guard"}, unrelated_hook()]}]}}
        self.hooks_path.write_text(json.dumps(existing, ensure_ascii=True), encoding="utf-8")
        self.rules_path = self.project / "AGENTS.md"
        self.rules_path.write_text("User rules must survive.\n", encoding="utf-8")
        self.original_hooks = self.hooks_path.read_bytes()
        self.original_rules = self.rules_path.read_bytes()
        self.global_dir = self.sandbox / "unrelated-user-config"
        self.global_dir.mkdir()
        for name in ("hooks.json", "config.toml", "hook-trust.json"):
            (self.global_dir / name).write_text("sentinel:" + name, encoding="utf-8")
        self.project_trust = self.project / ".codex" / "hook-trust.json"
        self.project_trust.write_text("project-trust-sentinel", encoding="utf-8")
        self.protected_before = {p: p.read_bytes() for p in self.global_dir.iterdir()}
        self.protected_before[self.project_trust] = self.project_trust.read_bytes()

    def tearDown(self):
        self.assertEqual(self.sandbox.resolve().parent, Path(__file__).resolve().parent)
        self.temp.cleanup()

    def run_installer(self, *args):
        # Override the config location only in this disposable child process.
        environment = dict(os.environ, CODEX_HOME=str(self.global_dir), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, "-B", "-X", "utf8", str(self.guard / "install.py"), *args],
                                cwd=self.project, env=environment, text=True, capture_output=True, timeout=20)
        self.assertEqual((self.guard / "policy.json").read_bytes(), self.policy_before)
        for path, expected in self.protected_before.items():
            self.assertEqual(path.read_bytes(), expected)
        self.assertEqual(set(self.global_dir.iterdir()), set(self.protected_before) - {self.project_trust})
        return result

    def test_prepare_does_not_install(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.guard / "hooks.prepared.json").exists())
        self.assertEqual(self.hooks_path.read_bytes(), self.original_hooks)
        self.assertEqual(self.rules_path.read_bytes(), self.original_rules)
        self.assertFalse((self.guard / "installation-backups").exists())

    def test_install_preserves_policy_backups_trust_and_other_hooks(self):
        first = self.run_installer("--install")
        self.assertEqual(first.returncode, 0, first.stderr)
        installed = json.loads(self.hooks_path.read_text(encoding="utf-8"))
        self.assertEqual(installed["keep"], "root metadata")
        self.assertEqual(installed["hooks"]["PreToolUse"][0]["hooks"], [unrelated_hook()])
        self.assertTrue(self.rules_path.read_text(encoding="utf-8").startswith("User rules must survive."))
        backups = self.guard / "installation-backups"
        for name, content in (("hooks.json", self.original_hooks), ("AGENTS.md", self.original_rules)):
            expected = backups / (name + "." + hashlib.sha256(content).hexdigest()[:12] + ".bak")
            self.assertEqual(expected.read_bytes(), content)
        saved_backups = {p.name: p.read_bytes() for p in backups.iterdir()}
        hooks_after_first = self.hooks_path.read_bytes()
        rules_after_first = self.rules_path.read_bytes()
        second = self.run_installer("--install")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.hooks_path.read_bytes(), hooks_after_first)
        self.assertEqual(self.rules_path.read_bytes(), rules_after_first)
        for name, content in saved_backups.items():
            self.assertEqual((backups / name).read_bytes(), content)

    def test_pending_operation_blocks_install_before_any_config_write(self):
        state = self.guard / "state"
        state.mkdir()
        gate_path = state / "gate.json"
        gate_path.write_text(json.dumps({"pending": {"status": "pending"}}), encoding="utf-8")
        gate_before = gate_path.read_bytes()
        result = self.run_installer("--install")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("operation is pending", result.stderr)
        self.assertEqual(gate_path.read_bytes(), gate_before)
        self.assertEqual(self.hooks_path.read_bytes(), self.original_hooks)
        self.assertEqual(self.rules_path.read_bytes(), self.original_rules)
        self.assertFalse((self.guard / "hooks.prepared.json").exists())

    def test_malformed_rules_preserve_existing_installation(self):
        self.rules_path.write_text("Owner rules\n" + installer.BEGIN, encoding="utf-8")
        malformed = self.rules_path.read_bytes()
        result = self.run_installer("--install")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.hooks_path.read_bytes(), self.original_hooks)
        self.assertEqual(self.rules_path.read_bytes(), malformed)
        self.assertFalse((self.guard / "installation-backups").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
