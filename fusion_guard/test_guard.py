import ast
import base64
from concurrent.futures import ThreadPoolExecutor
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS, ModuleType
import unittest
from unittest.mock import patch

import hook
import install

POLICY = dict(hook.read_json(hook.POLICY_PATH), enabled=True)
FEATURE = '''# fusion-guard: feature
import adsk.core, adsk.fusion
def run(_context: str):
    design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    root = design.rootComponent
    extrudes = root.features.extrudeFeatures
    feature_input = extrudes.createInput(root.sketches.item(0).profiles.item(0), adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    distance = adsk.core.ValueInput.createByString("thickness")
    extent = adsk.fusion.DistanceExtentDefinition.create(distance)
    feature_input.setOneSideExtent(extent, adsk.fusion.ExtentDirections.PositiveExtentDirection)
    result = extrudes.add(feature_input)
    result.name = "Plate"
'''
PARAMETERS = '''# fusion-guard: parameters
import adsk.core, adsk.fusion
def run(_context: str):
    design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    design.userParameters.add("thickness", adsk.core.ValueInput.createByString("3 mm"), "mm", "Plate thickness")
'''
PROBE = (hook.ROOT / "probe.py").read_text(encoding="utf-8")


def snapshot():
    row = {"key": "0", "name": "Profile", "type": "adsk::fusion::Sketch",
           "health": "HealthyFeatureHealthState", "message": "", "suppressed": False, "rolled_back": False}
    sketch = {"key": "0:Root/0", "name": "Profile", "timeline_index": 0,
              "fully_constrained": True, "compute_deferred": False,
              "curves": 4, "points": 4, "dimensions": 2, "constraints": 8,
              "point_positions": [[0, 0, 0]], "dimension_expressions": []}
    return {"document": {"creation_id": "document-A", "name": "Test", "file_id": None},
            "parametric": True, "timeline_count": 1, "marker_position": 1,
            "timeline": [row], "newest": row.copy(), "base_feature_count": 0,
            "components": [], "bodies": [],
            "parameters": [{"name": "thickness", "expression": "3 mm", "unit": "mm", "type": "UserParameter"}],
            "user_parameters": ["thickness"], "sketches": [sketch], "latest_sketch": sketch.copy()}


def after_feature(before):
    after = copy.deepcopy(before)
    row = dict(after["timeline"][0], key="1", name="Plate", type="adsk::fusion::ExtrudeFeature")
    after["timeline"].append(row)
    after.update(timeline_count=2, marker_position=2, newest=row)
    after["parameters"].append({"name": "d3", "expression": "thickness", "unit": "mm", "type": "ModelParameter"})
    return after


def pre(source=FEATURE, session="session-A", call="call-1", readonly=False):
    return {"hook_event_name": "PreToolUse", "session_id": session, "tool_use_id": call,
            "tool_name": "mcp__fusion__fusion_mcp_execute",
            "tool_input": {"featureType": "script", "object": {"script": source, "readOnly": readonly}}}


def line(nonce, phase, snap, completed=True):
    return hook.PREFIX + nonce + ":" + json.dumps({"phase": phase, "snapshot": snap, "completed": completed})


def inspector_transport():
    # Exercise the real emitter without requiring an Autodesk installation.
    tree = ast.parse((hook.ROOT / "inspect_model.py").read_text(encoding="utf-8"))
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.Import) and any(a.name.startswith("adsk") for a in node.names))]
    namespace = {}
    exec(compile(tree, "inspector_transport", "exec"), namespace)
    return namespace


def compressed_line(nonce, phase, snap, completed=True):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        inspector_transport()["_fg_emit"](nonce, phase, snap, completed)
    return output.getvalue()


def write_transport(operation, phase, snap, completed=True):
    namespace = inspector_transport()
    namespace["_fg_report_directory"] = operation["transport_dir"]
    namespace["_fg_emit"](operation["nonce"], phase, snap, completed)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=hook.ROOT, prefix="test-state-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_event(self, event):
        return hook.process(event, POLICY, self.root)

    def begin(self):
        event = pre()
        result = self.run_event(event)
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "allow")
        pending = hook.read_json(self.root / "gate.json")["pending"]
        return event, pending

    def finish(self, event, pending, before=None, after=None, complete=True, extra=None):
        before = before or snapshot()
        after = after or after_feature(before)
        text = line(pending["nonce"], "before", before, False) + "\n" + line(pending["nonce"], "after", after, complete)
        write_transport(pending, "before", before, False)
        write_transport(pending, "after", after, complete)
        response = {"content": [{"type": "text", "text": json.dumps({"stdout": text})}]}
        if extra:
            response.update(extra)
        return self.run_event(dict(event, hook_event_name="PostToolUse", tool_response=response))

    def probe_result(self, snap, call="inspect-1"):
        event = pre(PROBE, call=call, readonly=True)
        result = self.run_event(event)
        self.assertIn("updatedInput", result["hookSpecificOutput"])
        operation = hook.read_json(self.root / "gate.json")["probes"][call]
        nonce = operation["nonce"]
        write_transport(operation, "inspect", snap)
        return self.run_event(dict(event, hook_event_name="PostToolUse", tool_response={"output": line(nonce, "inspect", snap)}))

    def test_disabled_policy_does_nothing(self):
        result = hook.process(pre(), dict(POLICY, enabled=False), self.root)
        self.assertEqual(result, {})
        self.assertFalse((self.root / "gate.json").exists())

    def test_native_feature_lints(self):
        tree, kind, expressions = hook.lint(FEATURE, False, POLICY)
        self.assertEqual((kind, expressions), ("feature", ["thickness"]))
        rewritten = hook.wrap_source(tree, "nonce", kind, expressions)
        ast.parse(rewritten)
        self.assertIn("finally:", rewritten)
        self.assertIn("computeAll", rewritten)

    def test_parameter_creation_separate_step(self):
        self.assertEqual(hook.lint(PARAMETERS, False, POLICY)[1], "parameters")

    def test_forbidden_patterns(self):
        changes = {
            "temporary brep": "adsk.fusion.TemporaryBRepManager.get()",
            "direct mode": "design.designType = adsk.fusion.DesignTypes.DirectDesignType",
            "base feature": "root.features.baseFeatures.add()",
            "dynamic code": "exec('anything')",
            "dynamic attribute": "getattr(root, 'features')",
            "external module": "import os",
            "dynamic loading": "__import__('os')",
            "raw numeric value": "adsk.core.ValueInput.createByReal(0.3)",
            "raw body": "root.bRepBodies.add(body)",
            "fixed sketch": "sketch.isFixed = True",
            "raw dimensions": "distance.value = 0.3",
            "text command": "adsk.core.Application.get().executeTextCommand('Undo')",
            "hidden method alias": "add = extrudes.add",
            "swallowed exception": "try:\n        print('x')\n    except Exception:\n        pass",
            "looped feature": "for i in range(2):\n        extrudes.add(feature_input)",
            "second feature": "extrudes.add(feature_input)",
            "reserved state": "print(_fg_before)",
            "parameter smuggling": "design.userParameters.add('fake', distance, 'mm', '')",
        }
        for label, code in changes.items():
            with self.subTest(label=label):
                with self.assertRaises(hook.PolicyError):
                    hook.lint(FEATURE + "    " + code + "\n", False, POLICY)

    def test_top_level_execution_is_rejected(self):
        with self.assertRaises(hook.PolicyError):
            hook.lint(FEATURE + "print('side effect')\n", False, POLICY)

    def test_unclassified_write_rejected(self):
        with self.assertRaises(hook.PolicyError):
            hook.lint(FEATURE.replace("# fusion-guard: feature", ""), False, POLICY)

    def test_readonly_query_allowed_during_pending_write(self):
        self.begin()
        result = self.run_event(pre("def run(_context: str):\n    print('read only')", readonly=True, call="r"))
        self.assertEqual(result, {})

    def test_inspect_replaces_the_whole_script(self):
        event = pre("# fusion-guard: inspect\nTHIS IS NOT PYTHON", readonly=True)
        # Syntax must still be valid; a malformed request is denied.
        with self.assertRaises(hook.PolicyError):
            self.run_event(event)
        result = self.run_event(pre(PROBE, readonly=True))
        source = result["hookSpecificOutput"]["updatedInput"]["object"]["script"]
        self.assertNotIn("inspection was not injected", source)
        self.assertIn("_fg_snapshot()", source)

    def test_success_clears_pending_and_saves_report(self):
        event, pending = self.begin()
        result = self.finish(event, pending)
        self.assertNotIn("decision", result)
        self.assertIsNone(hook.read_json(self.root / "gate.json")["pending"])
        self.assertEqual(len(list((self.root / "reports").glob("*.json"))), 1)

    def test_missing_report_stops_next_write(self):
        event, pending = self.begin()
        result = self.run_event(dict(event, hook_event_name="PostToolUse", tool_response={"success": True}))
        self.assertEqual(result["decision"], "block")
        self.assertEqual(self.run_event(pre(call="next"))["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_failed_probe_keeps_original_response_and_pending_gate(self):
        _, pending = self.begin()
        event = pre(PROBE, call="failed-probe", readonly=True)
        self.run_event(event)
        response = {"content": [{"type": "text", "text": json.dumps({
            "success": False, "error": "Original Fusion failure"})}]}
        result = self.run_event(dict(event, hook_event_name="PostToolUse", tool_response=response))
        self.assertEqual(result["decision"], "block")
        self.assertIn("The Fusion tool returned an error", result["reason"])
        state = hook.read_json(self.root / "gate.json")
        self.assertEqual(state["pending"], pending)
        self.assertNotIn("failed-probe", state["probes"])
        reports = [hook.read_json(p) for p in (self.root / "reports").glob("*.json")]
        failed = next(r for r in reports if r["status"] == "inspection_failed")
        self.assertEqual(failed["tool_response"], response)
        self.assertEqual(failed["reports"], {})

    def test_partial_failure_keeps_gate(self):
        event, pending = self.begin()
        result = self.finish(event, pending, complete=False)
        self.assertEqual(result["decision"], "block")
        self.assertEqual(hook.read_json(self.root / "gate.json")["pending"]["status"], "failed")

    def test_tool_error_never_becomes_success(self):
        event, pending = self.begin()
        self.assertEqual(self.finish(event, pending, extra={"isError": True})["decision"], "block")

    def test_failed_model_report_preserves_original_tool_error(self):
        event, pending = self.begin()
        error = {"isError": True, "message": "Native sketch solver rejected the dimension"}
        self.assertEqual(self.finish(event, pending, extra=error)["decision"], "block")
        report = hook.read_json(next((self.root / "reports").glob("*.json")))
        self.assertEqual(report["tool_response"]["message"], error["message"])
        self.assertTrue(report["tool_response"]["isError"])

    def test_cross_session_writes_are_serialized(self):
        self.begin()
        result = self.run_event(pre(session="session-B", call="call-2"))
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_wrong_call_response_cannot_unlock(self):
        self.begin()
        result = self.run_event(dict(pre(call="wrong"), hook_event_name="PostToolUse", tool_response={}))
        self.assertEqual(result, {})
        self.assertIsNotNone(hook.read_json(self.root / "gate.json")["pending"])

    def test_unknown_nonce_cannot_unlock(self):
        event, pending = self.begin()
        result = self.run_event(dict(event, hook_event_name="PostToolUse", tool_response=line("wrong", "after", snapshot())))
        self.assertEqual(result["decision"], "block")

    def test_recovery_requires_same_document_and_baseline(self):
        event, pending = self.begin()
        before = snapshot()
        self.finish(event, pending, complete=False)
        wrong = copy.deepcopy(before)
        wrong["document"]["creation_id"] = "document-B"
        self.assertEqual(self.probe_result(wrong)["decision"], "block")
        self.assertIsNotNone(hook.read_json(self.root / "gate.json")["pending"])
        self.assertNotIn("decision", self.probe_result(before, "inspect-2"))
        self.assertIsNone(hook.read_json(self.root / "gate.json")["pending"])

    def test_model_recovery_keeps_original_failure_report_unchanged(self):
        event, pending = self.begin()
        self.finish(event, pending, complete=False, extra={"isError": True, "message": "Original native failure"})
        original = next((self.root / "reports").glob("*.json"))
        original_bytes = original.read_bytes()
        self.assertNotIn("decision", self.probe_result(snapshot(), "recovery-inspection"))
        self.assertEqual(original.read_bytes(), original_bytes)
        recovered = [hook.read_json(p) for p in (self.root / "reports").glob("*.json")
                     if hook.read_json(p)["status"] == "baseline_observables_restored"]
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["operation"]["reconciles_call_id"], pending["call_id"])

    def test_probe_cannot_unlock_still_running_write(self):
        event, pending = self.begin()
        with hook.locked_state(self.root) as state:
            state["pending"]["before"] = snapshot()
        self.assertEqual(self.probe_result(snapshot())["decision"], "block")
        self.assertEqual(hook.read_json(self.root / "gate.json")["pending"]["status"], "pending")

    def test_stop_is_bounded_and_session_scoped(self):
        self.begin()
        stop = {"hook_event_name": "Stop", "session_id": "session-A", "stop_hook_active": False}
        self.assertEqual(self.run_event(stop)["decision"], "block")
        self.assertNotIn("decision", self.run_event(dict(stop, stop_hook_active=True)))
        self.assertEqual(self.run_event(dict(stop, session_id="session-B")), {})

    def test_undo_and_document_switch_blocked_during_pending(self):
        self.begin()
        undo = dict(pre(), tool_name="mcp__fusion__fusion_mcp_update", tool_input={"featureType": "undo"})
        switch = dict(pre(), tool_input={"featureType": "document", "object": {"operation": "open"}})
        for event in (undo, switch):
            self.assertEqual(self.run_event(event)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_assessment_detects_regressions(self):
        before = snapshot()
        def mutate(s, label):
            if label == "base": s["base_feature_count"] = 1
            elif label == "direct": s["parametric"] = False
            elif label == "batch": s["timeline_count"] = 3
            elif label == "warning": s["timeline"][-1]["health"] = "WarningFeatureHealthState"
            elif label == "unconstrained": s["sketches"][0]["fully_constrained"] = False
            elif label == "deferred": s["sketches"][0]["compute_deferred"] = True
            elif label == "reordered": s["timeline"][0]["name"] = "Changed"
            elif label == "expression": s["parameters"][-1]["expression"] = "3 mm"
        for label in ("base", "direct", "batch", "warning", "unconstrained", "deferred", "reordered", "expression"):
            with self.subTest(label=label):
                after = after_feature(before)
                mutate(after, label)
                self.assertTrue(hook.assess(before, after, "feature", POLICY, ["thickness"]))

    def test_existing_warning_is_reported_not_new_failure(self):
        before = snapshot()
        before["timeline"][0]["health"] = "WarningFeatureHealthState"
        after = after_feature(before)
        after["timeline"][-1]["health"] = "HealthyFeatureHealthState"
        self.assertEqual(hook.assess(before, after, "feature", POLICY, ["thickness"]), [])

    def test_parameter_mode_cannot_hardcode_model_dimensions(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after["parameters"].append({"name": "d4", "expression": "2 mm", "unit": "mm", "type": "adsk::fusion::ModelParameter"})
        self.assertTrue(hook.assess(before, after, "parameters", POLICY))
        after["parameters"][-1]["type"] = "adsk::fusion::UserParameter"
        self.assertEqual(hook.assess(before, after, "parameters", POLICY), [])

    def test_reports_parse_common_mcp_envelopes(self):
        text = line("n", "inspect", snapshot())
        for response in (text, {"output": text}, {"content": [{"type": "text", "text": text}]},
                         {"content": [{"type": "text", "text": json.dumps({"stdout": text})}]},
                         {"structuredContent": {"result": {"output": text}}}):
            self.assertIn("inspect", hook.records_from(response, "n"))

    def test_conflicting_reports_rejected(self):
        with self.assertRaises(hook.PolicyError):
            hook.records_from(line("n", "inspect", snapshot()) + "\n" + line("n", "inspect", after_feature(snapshot())), "n")

    def test_full_large_report_survives_fusion_stdout_limit_losslessly(self):
        large = snapshot()
        large["sketches"][0]["point_positions"] = [[1.23456789, 2.34567891, 3.45678912]] * 60000
        self.assertGreater(len(line("n", "inspect", large)), 1024 * 1024)
        text = compressed_line("n", "inspect", large)
        wrapped = {"content": [{"type": "text", "text": json.dumps({"success": True, "message": text})}]}
        self.assertLess(len(json.dumps(wrapped)), 1024 * 1024)
        self.assertEqual(hook.records_from(wrapped, "n")["inspect"]["snapshot"], large)
        self.assertEqual(hook.records_from(wrapped, "wrong"), {})

    def test_compressed_pre_and_post_reports_follow_normal_acceptance(self):
        event, pending = self.begin()
        before = snapshot()
        text = (compressed_line(pending["nonce"], "before", before, False)
                + compressed_line(pending["nonce"], "after", after_feature(before)))
        write_transport(pending, "before", before, False)
        write_transport(pending, "after", after_feature(before))
        response = {"content": [{"type": "text", "text": json.dumps({"message": text, "success": True})}]}
        result = self.run_event(dict(event, hook_event_name="PostToolUse", tool_response=response))
        self.assertNotIn("decision", result)
        self.assertIsNone(hook.read_json(self.root / "gate.json")["pending"])

    def test_registered_file_report_does_not_depend_on_stdout(self):
        event = pre(PROBE, call="local-report", readonly=True)
        self.run_event(event)
        operation = hook.read_json(self.root / "gate.json")["probes"]["local-report"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            write_transport(operation, "inspect", snapshot())
        self.assertEqual(output.getvalue(), "")
        response = {"content": [{"type": "text", "text": json.dumps({
            "message": "[output truncated: exceeded 1 MiB]", "success": True})}]}
        result = self.run_event(dict(event, hook_event_name="PostToolUse", tool_response=response))
        self.assertNotIn("decision", result)
        report = next(hook.read_json(p) for p in (self.root / "reports").glob("*.json"))
        self.assertEqual(report["reports"]["inspect"]["snapshot"], snapshot())

    def test_file_transport_rejects_replay_corruption_and_wrong_phase(self):
        event = pre(PROBE, call="file-check", readonly=True)
        self.run_event(event)
        operation = hook.read_json(self.root / "gate.json")["probes"]["file-check"]
        write_transport(operation, "inspect", snapshot())
        file = Path(operation["transport_dir"]) / "inspect.json"
        original = hook.read_json(file)
        for change in ("nonce", "digest", "phase", "directory"):
            transport = copy.deepcopy(original)
            candidate = dict(operation)
            if change == "nonce":
                transport["nonce"] = "0" * 32
            elif change == "digest":
                transport["envelope"]["sha256"] = "0" * 64
            elif change == "phase":
                transport["envelope"] = json.loads(compressed_line(operation["nonce"], "after", snapshot()).split(":", 2)[2])
            else:
                candidate["transport_dir"] = str(self.root)
            hook.write_json(file, transport)
            with self.subTest(change=change), self.assertRaises(hook.PolicyError):
                hook.operation_records({}, candidate, self.root)

    def test_partial_file_and_stdout_cannot_substitute_registered_report(self):
        event = pre(PROBE, call="partial-file", readonly=True)
        self.run_event(event)
        operation = hook.read_json(self.root / "gate.json")["probes"]["partial-file"]
        write_transport(operation, "inspect", snapshot())
        file = Path(operation["transport_dir"]) / "inspect.json"
        file.rename(file.with_suffix(".json.tmp"))
        response = {"output": compressed_line(operation["nonce"], "inspect", snapshot())}
        result = self.run_event(dict(event, hook_event_name="PostToolUse", tool_response=response))
        self.assertEqual(result["decision"], "block")

    def test_compressed_reports_reject_damage_and_false_length(self):
        envelope = json.loads(compressed_line("n", "inspect", snapshot()).split(":", 2)[2])
        truncated = base64.b64decode(envelope["data"])[:-3]
        appended = base64.b64decode(envelope["data"]) + b"unexpected trailer"
        for change in ({"sha256": "0" * 64}, {"raw_bytes": envelope["raw_bytes"] - 1},
                       {"raw_bytes": hook.MAX_REPORT_RAW_BYTES + 1}, {"data": "!"},
                       {"data": base64.b64encode(truncated).decode("ascii")},
                       {"data": base64.b64encode(appended).decode("ascii")}):
            with self.subTest(change=next(iter(change))):
                text = hook.COMPRESSED_PREFIX + "n:" + json.dumps(dict(envelope, **change))
                with self.assertRaises(hook.PolicyError):
                    hook.records_from(text, "n")

    def test_compressed_emitter_never_silently_discards_fields(self):
        namespace = inspector_transport()
        self.assertEqual(namespace["_fg_MAX_REPORT_RAW_BYTES"], hook.MAX_REPORT_RAW_BYTES)
        self.assertEqual(namespace["_fg_MAX_REPORT_ENCODED_CHARS"], hook.MAX_REPORT_ENCODED_CHARS)
        for limit in ("_fg_MAX_REPORT_RAW_BYTES", "_fg_MAX_REPORT_ENCODED_CHARS"):
            original = namespace[limit]
            namespace[limit] = 10
            output = io.StringIO()
            with contextlib.redirect_stdout(output), self.assertRaisesRegex(RuntimeError, "size limit"):
                namespace["_fg_emit"]("n", "inspect", snapshot(), True)
            self.assertEqual(output.getvalue(), "")
            namespace[limit] = original

    def test_wrapper_preserves_original_exception_and_reports_partial_state(self):
        source = "# fusion-guard: parameters\ndef run(_context: str):\n    raise RuntimeError('original')\n"
        tree, kind, expressions = hook.lint(source, False, POLICY)
        wrapped = ast.parse(hook.wrap_source(tree, "nonce", kind, expressions))
        emitted = []
        def fail(_):
            raise RuntimeError("original")
        namespace = {"_fg_snapshot": snapshot, "_fg_baseline_check": lambda _: None,
                     "_fg_emit": lambda *a: emitted.append(a), "_fg_user_run": fail}
        module = ast.Module(body=[wrapped.body[-1]], type_ignores=[])
        exec(compile(module, "wrapper", "exec"), namespace)
        with self.assertRaisesRegex(RuntimeError, "original"):
            namespace["run"]("")
        self.assertEqual([a[1] for a in emitted], ["before", "after"])
        self.assertFalse(emitted[-1][-1])

    def test_wrapper_rejects_literal_dimension_before_mutation(self):
        source = FEATURE.replace('"thickness"', '"3 mm"')
        tree, kind, expressions = hook.lint(source, False, POLICY)
        wrapped = ast.parse(hook.wrap_source(tree, "nonce", kind, expressions))
        namespace = {"_fg_snapshot": snapshot, "_fg_baseline_check": lambda _: None,
                     "_fg_emit": lambda *a: None, "_fg_re": __import__("re"),
                     "_fg_user_run": lambda _: self.fail("must not execute")}
        exec(compile(ast.Module(body=[wrapped.body[-1]], type_ignores=[]), "wrapper", "exec"), namespace)
        with self.assertRaisesRegex(RuntimeError, "must reference"):
            namespace["run"]("")

    def test_install_preserves_existing_rules(self):
        rules = install.rules_text("User's existing rules\n", "Fusion rules\n")
        self.assertTrue(rules.startswith("User's existing rules"))
        self.assertEqual(install.rules_text(rules, "New fusion rules").count(install.BEGIN), 1)
        with self.assertRaises(ValueError):
            install.rules_text(install.BEGIN, "rules")

    def test_config_is_project_scoped_and_synchronous(self):
        config = install.config()
        self.assertEqual(set(config["hooks"]), {"PreToolUse", "PostToolUse", "Stop"})
        for phase, groups in config["hooks"].items():
            if phase != "Stop":
                self.assertEqual(groups[0]["matcher"], "^mcp__fusion__.*$")
            self.assertNotIn("async", groups[0]["hooks"][0])
            self.assertIn("exit 2", groups[0]["hooks"][0]["commandWindows"])

    def test_real_hook_process_denies_invalid_input_and_concurrent_write(self):
        for name in ("hook.py", "inspect_model.py", "document_ops.py", "inspect_documents.py"):
            (self.root / name).write_bytes((hook.ROOT / name).read_bytes())
        hook.write_json(self.root / "policy.json", POLICY)
        def invoke(event):
            result = subprocess.run([sys.executable, "-X", "utf8", str(self.root / "hook.py")],
                                    input=json.dumps(event), text=True, encoding="utf-8", capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        invalid = invoke(pre("def run(_context):\n    pass"))
        self.assertEqual(invalid["hookSpecificOutput"]["permissionDecision"], "deny")
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(invoke, [pre(call="concurrent-1"), pre(call="concurrent-2", session="other")]))
        self.assertEqual(sorted(r["hookSpecificOutput"]["permissionDecision"] for r in results), ["allow", "deny"])


class Collection:
    def __init__(self, items):
        self.items = items
        self.count = len(items)
    def item(self, i):
        return self.items[i]


class InspectorTests(unittest.TestCase):
    def test_real_inspector_source_handles_null_entities_and_groups_readonly(self):
        core, fusion, adsk = ModuleType("adsk.core"), ModuleType("adsk.fusion"), ModuleType("adsk")
        adsk.core, adsk.fusion = core, fusion
        leaf = NS(isGroup=False, entity=None, name="Unknown item", healthState=0,
                  errorOrWarningMessage="", isSuppressed=False, isRolledBack=False)
        group = Collection([leaf])
        group.isGroup = True
        timeline = Collection([group])
        timeline.markerPosition = 1
        class ExternalSketch:
            name = "Referenced sketch"
            isFullyConstrained = True
            isComputeDeferred = False
            sketchCurves = Collection([])
            sketchPoints = Collection([])
            sketchDimensions = Collection([])
            geometricConstraints = Collection([])
            @property
            def timelineObject(self):
                raise RuntimeError("external timeline index is not valid in this design")
        component = NS(name="Root", features=NS(baseFeatures=Collection([])),
                       bRepBodies=Collection([]), sketches=Collection([ExternalSketch()]))
        design = NS(timeline=timeline, allComponents=Collection([component]), allParameters=Collection([]),
                    userParameters=Collection([]), designType=1)
        doc = NS(creationId="doc", name="Mock", isSaved=False)
        app = NS(activeDocument=doc, activeProduct=design)
        core.Application = NS(get=lambda: app)
        fusion.Design = NS(cast=lambda value: value)
        fusion.DesignTypes = NS(ParametricDesignType=1)
        fusion.FeatureHealthStates = NS(HealthyFeatureHealthState=0)
        fusion.TimelineGroup = NS(cast=lambda value: value)
        with patch.dict(sys.modules, {"adsk": adsk, "adsk.core": core, "adsk.fusion": fusion}):
            namespace = {}
            exec((hook.ROOT / "inspect_model.py").read_text(encoding="utf-8"), namespace)
            report = namespace["_fg_snapshot"]()
        self.assertEqual(report["timeline"][0]["type"], "unrepresented")
        self.assertEqual(report["timeline"][0]["health"], "HealthyFeatureHealthState")
        self.assertEqual(report["timeline_count"], 1)
        self.assertIsNone(report["latest_sketch"])
        self.assertEqual(report["sketches"][0]["timeline_index"], -1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
