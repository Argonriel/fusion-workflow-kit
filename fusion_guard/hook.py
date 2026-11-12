"""Project-scoped Codex Fusion hooks. Standard-library only, Python >= 3.11.

An engineering guardrail, not a Python security sandbox. Never automatically undo.
State is serialized across this project's sessions. It does not lock the Fusion UI
or clients in other projects. Runtime reports are checks, not document backups.
"""
from __future__ import annotations

import ast
import base64
import binascii
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
import zlib

ROOT = Path(__file__).resolve().parent
POLICY_PATH = ROOT / "policy.json"
STATE_ROOT = ROOT / "state"
PREFIX = "FUSION_GUARD_V1:"
COMPRESSED_PREFIX = "FUSION_GUARD_V2:"
MAX_REPORT_RAW_BYTES = 16 * 1024 * 1024
MAX_REPORT_ENCODED_CHARS = 384 * 1024
KINDS = {"feature", "sketch", "parameters", "edit", "inspect"}
ALLOWED_IMPORTS = {"adsk", "adsk.core", "adsk.fusion", "math", "json"}
FORBIDDEN_NAMES = {
    "TemporaryBRepManager", "DirectDesignType", "BaseFeature", "BaseFeatures",
    "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr",
    "globals", "locals", "vars", "open", "input", "breakpoint", "type",
    "executeTextCommand", "executeTextCommands", "execute", "load", "loads",
    "save", "saveAs", "saveDataVersion", "saveMilestone", "close", "activate",
    "importToTarget", "importToNewDocument", "deleteMe", "deleteObject",
    "deleteEntities", "dissolve", "startEdit", "finishEdit", "rollTo", "reorder",
    "exit", "quit", "addFixed", "createByReal", "addByDefinition",
}
FEATURE_COLLECTIONS = {
    "extrudeFeatures", "revolveFeatures", "holeFeatures", "filletFeatures",
    "chamferFeatures", "shellFeatures", "sweepFeatures", "loftFeatures",
    "combineFeatures", "splitBodyFeatures", "splitFaceFeatures", "mirrorFeatures",
    "rectangularPatternFeatures", "circularPatternFeatures", "pathPatternFeatures",
    "thickenFeatures", "ribFeatures", "webFeatures", "draftFeatures",
    "offsetFeatures", "moveFeatures", "scaleFeatures", "threadFeatures",
    "embossFeatures", "boundaryFillFeatures", "constructionPlanes",
    "constructionAxes", "constructionPoints", "joints", "asBuiltJoints",
    "jointOrigins", "rigidGroups", "occurrences",
}


class PolicyError(ValueError):
    pass


def read_json(path, default=None):
    if not path.exists() and default is not None:
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


@contextlib.contextmanager
def locked_state(root):
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "gate.lock"
    stream = lock.open("a+b")
    stream.seek(0, 2)
    if stream.tell() == 0:
        stream.write(b"0")
        stream.flush()
    deadline = time.monotonic() + 5
    acquired = False
    try:
        while not acquired:
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                if time.monotonic() >= deadline:
                    raise PolicyError("Another call holds the Fusion inspection state; retry later.")
                time.sleep(0.05)
        state = read_json(root / "gate.json", {"pending": None, "probes": {}})
        yield state
        write_json(root / "gate.json", state)
    finally:
        if acquired:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
            "permissionDecision": "deny", "permissionDecisionReason": "Fusion Guard: " + reason}}


def feedback(reason, block=True):
    output = {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                     "additionalContext": "Fusion Guard: " + reason}}
    if block:
        output.update(decision="block", reason="Fusion Guard: " + reason)
    return output


def path_of(node, aliases):
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return path_of(node.value, aliases) + "." + node.attr
    if isinstance(node, ast.Call):
        return path_of(node.func, aliases) + "()"
    return "?"


def lint(source, read_only, policy):
    if not isinstance(source, str) or len(source.encode("utf-8")) > policy["max_source_bytes"]:
        raise PolicyError("The script is missing or too long; split it into a single step.")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise PolicyError("Python syntax error: " + str(exc)) from exc
    matches = re.findall(r"^\s*#\s*fusion-guard:\s*(\w+)\s*$", source, re.M)
    kind = matches[0] if len(matches) == 1 else None
    if not read_only and kind not in KINDS - {"inspect"}:
        raise PolicyError("A mutation script needs a # fusion-guard: feature / sketch / parameters / edit line.")
    if kind == "inspect" and not read_only:
        raise PolicyError("inspect requires readOnly: true.")
    if kind == "inspect":
        return tree, kind, []  # This entire input is replaced by the trusted read-only inspector.
    aliases, expressions, creations = {}, [], []
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if len(functions) != 1 or functions[0].name != "run":
        raise PolicyError("Only one top-level run(_context) function is allowed; put the step inside it.")
    run = functions[0]
    if (len(run.args.args) != 1 or run.args.posonlyargs or run.args.kwonlyargs
            or run.args.vararg or run.args.kwarg or run.args.defaults or run.decorator_list):
        raise PolicyError("run must have exactly one ordinary argument, with no defaults or decorators.")
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)):
            if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)):
                raise PolicyError("Only imports, docstrings and the run function are allowed at the top level.")
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    # Source-order alias tracking covers ordinary collection aliases; dynamic dispatch is refused.
    for node in sorted(ast.walk(tree), key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0))):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            if getattr(node, "level", 0) or any(n not in ALLOWED_IMPORTS for n in names):
                raise PolicyError("Only adsk.core, adsk.fusion, math and json imports are allowed; no external scripts or dynamic loading.")
            if isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names):
                raise PolicyError("Wildcard imports are not allowed.")
            for alias in node.names:
                if alias.name in FORBIDDEN_NAMES:
                    raise PolicyError("Forbidden import: " + alias.name)
        if isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef, ast.Lambda, ast.Global,
                             ast.Nonlocal, ast.Try, ast.TryStar, ast.With, ast.AsyncWith)):
            raise PolicyError("This checker rejects classes, dynamic callbacks and exception handlers; use a direct, inspectable single-step script.")
        if isinstance(node, ast.FunctionDef) and node is not run:
            raise PolicyError("Inline helper functions for this step so that multiple modeling operations cannot be hidden.")
        name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None
        if name and (name.startswith("_fg_") or name.startswith("__") or name in FORBIDDEN_NAMES):
            raise PolicyError("This name or operation is not allowed: " + name)
        if isinstance(node, ast.Attribute) and not read_only and node.attr in {"baseFeatures", "targetBaseFeature", "timelineGroups"}:
            raise PolicyError("Creating or editing a Base Feature, or reorganizing the timeline in this step, is not allowed.")
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            for target in targets:
                if isinstance(target, ast.Name) and value is not None:
                    resolved = path_of(value, aliases)
                    if isinstance(value, ast.Attribute) and (value.attr.startswith("add") or value.attr in {"createByString"}):
                        raise PolicyError("Do not alias creation methods; call the collection method directly.")
                    aliases[target.id] = resolved
                if isinstance(target, ast.Attribute):
                    if kind == "parameters" and target.attr != "expression":
                        raise PolicyError("A parameters step may only assign parameter expressions.")
                    if target.attr in {"designType", "isFixed", "value", "markerPosition", "transform", "transform2"}:
                        raise PolicyError("Direct assignment is not allowed for " + target.attr + "; use named parameter expressions or native features.")
                    if target.attr == "expression" and not read_only:
                        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                            raise PolicyError("Parameter expressions must use inspectable string literals.")
                        expressions.append(value.value)
        if isinstance(node, ast.Call):
            path = path_of(node.func, aliases)
            pieces = path.split(".")
            leaf = pieces[-1]
            if kind == "parameters" and not read_only and leaf.startswith(("add", "set", "create", "remove", "copy", "move")):
                if not (leaf == "createByString" or path.endswith("userParameters.add")):
                    raise PolicyError("A parameters step may only add user parameters or modify parameter expressions.")
            if leaf in {"add", "addNewComponent", "addSimple"}:
                receiver = pieces[-2] if len(pieces) > 1 else ""
                if not read_only and receiver == "userParameters" and kind != "parameters":
                    raise PolicyError("Create user parameters in a separate parameters step.")
                if receiver == "bRepBodies":
                    raise PolicyError("Do not add BRep bodies directly; use native parametric features.")
                if receiver in FEATURE_COLLECTIONS or receiver == "sketches":
                    creations.append("sketch" if receiver == "sketches" else "feature")
                    ancestor = parents.get(node)
                    while ancestor is not None:
                        if isinstance(ancestor, (ast.For, ast.While, ast.comprehension, ast.ListComp,
                                                 ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                            raise PolicyError("Do not create timeline features in loops; split them into individual calls.")
                        ancestor = parents.get(ancestor)
            if leaf == "createByString" and not read_only:
                if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    raise PolicyError("ValueInput.createByString requires an inspectable string expression.")
                expressions.append(node.args[0].value)
    if not read_only:
        if kind == "feature" and creations != ["feature"]:
            raise PolicyError("A feature step must create exactly one native feature; prepare sketches and parameters separately.")
        if kind == "sketch" and (len(creations) > 1 or "feature" in creations):
            raise PolicyError("A sketch step may create at most one sketch and may not also create solid features.")
        if kind in {"parameters", "edit"} and creations:
            raise PolicyError("A parameters or edit step may not create new timeline features.")
    return tree, kind, expressions


def wrap_source(tree, nonce, kind, expressions, report_directory=None):
    inspector = (ROOT / "inspect_model.py").read_text(encoding="utf-8")
    if report_directory is not None:
        inspector += "\n_fg_report_directory = " + repr(str(report_directory)) + "\n"
    if kind == "inspect":
        return inspector + "\n\ndef run(_context: str):\n    _fg_emit(" + repr(nonce) + ", 'inspect', _fg_snapshot(), True)\n"
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "run":
            node.name = "_fg_user_run"
    source = ast.unparse(tree)
    validation = ""
    if kind != "parameters" and expressions:
        validation = (
            "    _fg_names = set(_fg_before['user_parameters'])\n"
            "    for _fg_expr in " + repr(expressions) + ":\n"
            "        if not any(_fg_re.search(r'(?<![\\w])' + _fg_re.escape(n) + r'(?![\\w])', _fg_expr) for n in _fg_names):\n"
            "            raise RuntimeError('Fusion Guard: dimensional expression must reference an existing named user parameter: ' + _fg_expr)\n"
        )
    return inspector + "\nimport re as _fg_re\n" + source + "\n\ndef run(_context: str):\n" + (
        "    _fg_before = _fg_snapshot()\n"
        "    _fg_emit(" + repr(nonce) + ", 'before', _fg_before)\n"
        "    _fg_baseline_check(_fg_before)\n"
    ) + validation + (
        "    _fg_completed = False\n"
        "    try:\n"
        "        _fg_user_run(_context)\n"
        "        _fg_design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)\n"
        "        if not _fg_design.computeAll():\n"
        "            raise RuntimeError('Fusion Guard: computeAll failed')\n"
        "        _fg_completed = True\n"
        "    finally:\n"
        "        _fg_emit(" + repr(nonce) + ", 'after', _fg_snapshot(), _fg_completed)\n"
    )


def decode_compressed_report(envelope):
    if not isinstance(envelope, dict) or envelope.get("encoding") != "zlib+base64":
        raise PolicyError("Invalid compressed inspection report format.")
    size, data, digest = (envelope.get(k) for k in ("raw_bytes", "data", "sha256"))
    if (type(size) is not int or not 0 < size <= MAX_REPORT_RAW_BYTES
            or not isinstance(data, str) or len(data) > MAX_REPORT_ENCODED_CHARS
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
        raise PolicyError("Invalid compressed inspection report length or checksum metadata.")
    try:
        compressed = base64.b64decode(data, validate=True)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, size + 1)
    except (ValueError, binascii.Error, zlib.error) as exc:
        raise PolicyError("The compressed inspection report is damaged or truncated.") from exc
    if (len(raw) != size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
            or hashlib.sha256(raw).hexdigest() != digest):
        raise PolicyError("The compressed inspection report failed its integrity check.")
    try:
        record = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise PolicyError("The decompressed inspection report is not valid JSON.") from exc
    if not isinstance(record, dict):
        raise PolicyError("The decompressed inspection report is not an object.")
    return record


def records_from(response, nonce):
    records = []
    markers = ((PREFIX + nonce + ":", False), (COMPRESSED_PREFIX + nonce + ":", True))
    decoder = json.JSONDecoder()

    def visit(value, depth=0):
        if depth > 30:
            raise PolicyError("Tool report nesting is too deep to verify acceptance.")
        if isinstance(value, dict):
            for item in value.values():
                visit(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                visit(item, depth + 1)
        elif isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith(("{", "[")):
                try:
                    nested = json.loads(stripped)
                except ValueError:
                    pass
                else:
                    visit(nested, depth + 1)
                    return
            for marker, compressed in markers:
                for match in re.finditer(re.escape(marker), value):
                    try:
                        record, _ = decoder.raw_decode(value[match.end():])
                    except ValueError:
                        continue
                    if compressed:
                        record = decode_compressed_report(record)
                    if isinstance(record, dict):
                        records.append(record)
    visit(response)
    unique = {}
    for record in records:
        phase = record.get("phase")
        if phase in unique and unique[phase] != record:
            raise PolicyError("Conflicting acceptance reports were received.")
        unique[phase] = record
    return unique


def tool_failed(value):
    if isinstance(value, dict):
        if value.get("isError") is True or value.get("success") is False:
            return True
        return any(tool_failed(v) for v in value.values())
    if isinstance(value, list):
        return any(tool_failed(v) for v in value)
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            return tool_failed(json.loads(value))
        except ValueError:
            return False
    return False


def operation_records(response, operation, state_root):
    directory = operation.get("transport_dir")
    if directory is None:
        return records_from(response, operation["nonce"])
    nonce = operation["nonce"]
    if not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise PolicyError("Invalid local report nonce.")
    expected = (state_root / "transport" / nonce).absolute()
    path = Path(directory)
    if path != expected or path.is_symlink() or path.resolve() != expected:
        raise PolicyError("The local report directory does not match this call.")
    records = {}
    for phase in ("before", "after", "inspect"):
        file = path / (phase + ".json")
        if not file.exists():
            continue
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_REPORT_ENCODED_CHARS + 4096:
            raise PolicyError("Invalid local report file type or size.")
        try:
            transport = read_json(file)
        except (ValueError, UnicodeError) as exc:
            raise PolicyError("The local report file is damaged.") from exc
        if not isinstance(transport, dict) or transport.get("nonce") != nonce:
            raise PolicyError("The local report does not belong to this call.")
        record = decode_compressed_report(transport.get("envelope"))
        if record.get("phase") != phase:
            raise PolicyError("The local report phase does not match.")
        records[phase] = record
    return records


def validate_snapshot(s):
    required = {"document", "parametric", "timeline_count", "marker_position", "timeline",
                "base_feature_count", "parameters", "user_parameters", "sketches", "bodies", "components"}
    if not isinstance(s, dict) or not required.issubset(s):
        raise PolicyError("The acceptance report is missing required fields.")
    if not isinstance(s["document"], dict) or not s["document"].get("creation_id"):
        raise PolicyError("Cannot identify the inspected Fusion document.")
    if any(not isinstance(s[k], list) for k in ("timeline", "parameters", "user_parameters", "sketches", "bodies", "components")):
        raise PolicyError("Invalid acceptance report collection format.")


def assess(before, after, kind, policy, expressions=()):
    validate_snapshot(before)
    validate_snapshot(after)
    errors = []
    if before["document"] != after["document"]:
        errors.append("The document identity changed during the operation")
    if not after["parametric"]:
        errors.append("The design is no longer parametric")
    if after["base_feature_count"] != before["base_feature_count"]:
        errors.append("The Base Feature count changed")
    delta = after["timeline_count"] - before["timeline_count"]
    permitted = {"feature": {1}, "sketch": {0, 1}, "parameters": {0}, "edit": {0}}[kind]
    if delta not in permitted:
        errors.append("The timeline delta violates the single-step rule: " + str(delta))
    if after["marker_position"] != after["timeline_count"]:
        errors.append("The timeline marker did not return to the end")
    old_rows = {r["key"]: r for r in before["timeline"]}
    for row in after["timeline"]:
        old = old_rows.get(row["key"])
        bad = "Error" in row["health"] or (policy["reject_new_warnings"] and "Warning" in row["health"])
        if bad and (old is None or (old["health"], old["message"]) != (row["health"], row["message"])):
            errors.append("New or changed feature error/warning: " + row["name"] + " " + row["message"])
    if kind in {"feature", "sketch"}:
        old_signature = [(r["key"], r["name"], r["type"], r["suppressed"]) for r in before["timeline"]]
        prefix = [(r["key"], r["name"], r["type"], r["suppressed"]) for r in after["timeline"][:len(old_signature)]]
        if old_signature != prefix:
            errors.append("The new step also changed the existing timeline structure")
    old_sketches = {s["key"]: s for s in before["sketches"]}
    for sketch in after["sketches"]:
        if sketch["compute_deferred"]:
            errors.append("A sketch is still in deferred computation: " + sketch["name"])
        changed = old_sketches.get(sketch["key"]) != sketch
        # For a sketch-edit operation, also inspect the latest sketch even if counts are unchanged.
        latest_key = (after.get("latest_sketch") or {}).get("key")
        if (changed or (kind == "sketch" and sketch["key"] == latest_key)) and policy["require_changed_sketches_constrained"] and not sketch["fully_constrained"]:
            errors.append("A new or modified sketch is not fully constrained: " + sketch["name"])
    if kind == "parameters" and (before["timeline"] != after["timeline"]):
        # Parameter changes can update health; this check excludes non-health structural changes.
        fields = ("key", "name", "type", "suppressed", "rolled_back")
        if [[r[k] for k in fields] for r in before["timeline"]] != [[r[k] for k in fields] for r in after["timeline"]]:
            errors.append("The parameters step changed the timeline structure")
    old_parameters = {p["name"]: p for p in before["parameters"]}
    changed_parameters = [p for p in after["parameters"] if old_parameters.get(p["name"]) != p]
    if kind == "parameters" and any(not p["type"].endswith("UserParameter") for p in changed_parameters):
        errors.append("A parameters step may only create or modify user parameters; use edit with named parameter references for model dimensions")
    if kind != "parameters" and expressions:
        actual = {re.sub(r"\s+", "", p["expression"]) for p in changed_parameters}
        for expression in expressions:
            if re.sub(r"\s+", "", expression) not in actual:
                errors.append("An input expression is absent from the new or modified model parameters: " + expression)
    return errors


def summary(snapshot):
    newest = snapshot.get("newest") or {}
    sketch = snapshot.get("latest_sketch")
    bad = [r["name"] for r in snapshot["timeline"] if "Warning" in r["health"] or "Error" in r["health"]]
    return (f"Timeline: {snapshot['timeline_count']} items; newest: {newest.get('type', 'none')} / {newest.get('name', 'none')}; "
            f"Base Features: {snapshot['base_feature_count']}; warnings/errors: {len(bad)}; "
            + (f"Latest sketch: {sketch['name']}, fully constrained={sketch['fully_constrained']}." if sketch else "No sketches."))


def archive(root, pending, status, records, errors, tool_response=None):
    name = hashlib.sha256(pending["call_id"].encode()).hexdigest()[:24]
    report = {"status": status, "operation": pending, "reports": records, "errors": errors}
    if tool_response is not None:
        report["tool_response"] = tool_response
    path = root / "reports" / (name + ".json")
    write_json(path, report)
    return path


def process(event, policy, state_root):
    if not policy.get("enabled", False):
        return {}
    if policy.get("auto_undo") is not False:
        raise PolicyError("Automatic undo has not been validated in this version; auto_undo must be false.")
    phase = event.get("hook_event_name")
    session = event.get("session_id", "")
    call_id = event.get("tool_use_id", "")
    tool = event.get("tool_name", "")
    if phase == "Stop":
        with locked_state(state_root) as state:
            pending = state["pending"]
            if not pending or pending["session_id"] != session:
                return {}
            message = ("The Fusion change has not been accepted or recovered. Only read-only inspection is allowed; do not continue modeling or claim completion. "
                       "Run an inspection with readOnly:true and # fusion-guard: inspect as the first script line, then report the status to the user. "
                       "This version does not undo automatically. State record: " + str(state_root / "gate.json"))
            if event.get("stop_hook_active"):
                return {"systemMessage": message}  # Do not create an endless continuation loop.
            return {"decision": "block", "reason": message}
    if not re.match(r"^mcp__fusion__", tool):
        return {}
    args = event.get("tool_input", {})
    if not isinstance(args, dict):
        raise PolicyError("Tool input is not a JSON object.")
    if phase == "PreToolUse":
        with locked_state(state_root) as state:
            if tool in {"mcp__fusion__fusion_mcp_read", "mcp__fusion__fusion_mcp_electronics_read"}:
                return {}
            pending = state["pending"]
            if tool == "mcp__fusion__fusion_mcp_update":
                return deny("Undo boundaries have not been tested live; automatic undo/redo remains disabled. Inspect and recover manually in Fusion, then run a read-only inspection.")
            if tool != "mcp__fusion__fusion_mcp_execute":
                return deny("Unrecognized Fusion mutation tool; inspect its behavior first.")
            if args.get("featureType") != "script":
                if pending and args.get("featureType") == "document":
                    return deny("An unaccepted change exists; inspect or recover it first. Do not switch, close or save the document.")
                return {}  # Purchase, rendering and normal document actions retain their own authorization.
            obj = args.get("object", {})
            read_only = obj.get("readOnly") is True
            source = obj.get("script")
            tree, kind, expressions = lint(source, read_only, policy)
            if read_only and kind != "inspect":
                return {}
            if not call_id or not session:
                return deny("Missing session_id or tool_use_id; acceptance cannot be correlated reliably.")
            if not read_only and pending:
                return deny("The previous change has not passed acceptance/recovery (" + pending["status"] + "). Read-only inspection is allowed; further changes are paused.")
            nonce = uuid.uuid4().hex
            report_directory = (state_root / "transport" / nonce).absolute()
            report_directory.mkdir(parents=True, exist_ok=False)
            rewritten = wrap_source(tree, nonce, kind, expressions, report_directory)
            updated = dict(args)
            updated["object"] = dict(obj, script=rewritten)
            entry = {"session_id": session, "call_id": call_id, "nonce": nonce,
                     "kind": kind, "status": "pending", "created_at": time.time(),
                     "transport_dir": str(report_directory),
                     "expressions": expressions,
                     "source_sha256": hashlib.sha256(source.encode()).hexdigest()}
            if read_only:
                # Keep bounded stale probes without ever expiring the mutation gate automatically.
                state["probes"] = {k: v for k, v in state["probes"].items() if time.time() - v["created_at"] < 3600}
                state["probes"][call_id] = entry
            else:
                state["pending"] = entry
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                    "permissionDecision": "allow", "updatedInput": updated}}
    if phase == "PostToolUse":
        with locked_state(state_root) as state:
            probe = state["probes"].pop(call_id, None)
            pending = state["pending"]
            if probe:
                parse_errors = []
                try:
                    records = operation_records(event.get("tool_response"), probe, state_root)
                except PolicyError as exc:
                    records = {}
                    parse_errors.append(str(exc))
                record = records.get("inspect")
                if not record or not record.get("completed") or tool_failed(event.get("tool_response")):
                    errors = parse_errors
                    if not record:
                        errors.append("No complete inspect report was found for this call")
                    elif not record.get("completed"):
                        errors.append("The inspect report is not marked complete")
                    if tool_failed(event.get("tool_response")):
                        errors.append("The Fusion tool returned an error")
                    path = archive(state_root, probe, "inspection_failed", records, errors,
                                   tool_response=event.get("tool_response"))
                    return feedback("Read-only inspection did not return a complete report; the existing gate is unchanged. "
                                    + "; ".join(errors) + ". The original response was preserved: " + str(path))
                snapshot = record["snapshot"]
                validate_snapshot(snapshot)
                archive(state_root, probe, "inspection", records, [])
                if pending and pending.get("before"):
                    if pending["status"] in {"failed", "interrupted"} and snapshot == pending["before"]:
                        archive(state_root, pending, "baseline_observables_restored", {"inspect": record}, [])
                        state["pending"] = None
                        return feedback("The inspected document, timeline, parameters and geometry summary match the baseline; the gate is released. " + summary(snapshot), False)
                    return feedback("Inspection completed, but recovery to the pre-change state is not confirmed; the gate remains. " + summary(snapshot))
                return feedback("Read-only inspection completed. " + summary(snapshot), False)
            if not pending or pending["call_id"] != call_id:
                return {}
            errors = []
            try:
                records = operation_records(event.get("tool_response"), pending, state_root)
            except PolicyError as exc:
                records = {}
                errors.append(str(exc))
            before_rec, after_rec = records.get("before"), records.get("after")
            if before_rec:
                validate_snapshot(before_rec.get("snapshot"))
                pending["before"] = before_rec["snapshot"]
            if not before_rec or not after_rec:
                errors.append("A complete before or after inspection report is missing")
            elif not after_rec.get("completed"):
                errors.append("The script did not complete normally; partial changes may exist")
            else:
                errors.extend(assess(before_rec["snapshot"], after_rec["snapshot"], pending["kind"], policy, pending.get("expressions", [])))
            if tool_failed(event.get("tool_response")):
                errors.append("The Fusion tool returned an error")
            if errors:
                pending["status"] = "failed"
                pending["errors"] = errors
                if after_rec:
                    pending["after"] = after_rec.get("snapshot")
                archive(state_root, pending, "failed", records, errors)
                return feedback("; ".join(errors) + ". The next change is blocked; no automatic undo occurred. Inspect and recover before continuing.")
            archive(state_root, pending, "passed", records, [])
            state["pending"] = None
            return feedback("Acceptance passed. " + summary(after_rec["snapshot"]), False)
    return {}


def main():
    event = {}
    try:
        raw = sys.stdin.buffer.read()
        event = json.loads(raw.decode("utf-8-sig"))
        policy = read_json(POLICY_PATH)
        result = process(event, policy, STATE_ROOT)
    except Exception as exc:
        reason = "The checker failed and cannot confirm safe execution: " + type(exc).__name__ + ": " + str(exc)
        phase = event.get("hook_event_name") if isinstance(event, dict) else None
        if phase == "PreToolUse":
            result = deny(reason)
        elif phase == "Stop":
            result = {"systemMessage": reason} if event.get("stop_hook_active") else {"decision": "block", "reason": reason}
        else:
            result = {"decision": "block", "reason": reason}
        # Explicit denial is required: a generic crash may otherwise fail open in the host.
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=True) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
