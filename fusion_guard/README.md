# Fusion Guard runtime

Project-local Codex guard for native parametric Fusion operations. This release targets Windows and the `mcp__fusion__fusion_mcp_execute` script contract. Use the kit's main README for installation and `docs/ACCEPTANCE.md` for live qualification.

## Before modeling

Read `policy.json` and the project's `AGENTS.md`. An enabled policy is not proof that hooks are loaded. Pass the complete contents of `probe.py` to the Fusion execute tool as `object.script`, with `featureType: "script"` and `object.readOnly: true`. Require accepted inspection feedback and its matching local report. The unwrapped probe intentionally raises an error. Do not remove that error or inject the inspector yourself.

## Enforcement

Each mutation uses one parameters, sketch, feature or edit step. The pre-hook lints supported Python, reserves the project gate, and injects before/after inspection. The post-hook checks call-bound reports, recomputation, expected timeline delta, new warnings/errors, changed sketch constraints and parameter expressions. Reports are written atomically to local files to avoid truncated tool stdout. The Stop hook gives a bounded reminder for unresolved operations.

This is not a Python sandbox or a complete enforcement boundary. It cannot lock the Fusion UI, other projects or other clients. Ordinary read-only queries and non-script tools do not all receive the same full inspection. The current runtime blocks timeline marker edits, rollback setters and grouping operations in scripts.

## Failure

Stop mutations and preserve errors. Read-only inspection remains available. A person restores the design and then the unchanged probe verifies the recorded baseline observables. Automatic Undo/Redo, parameter perturbation and state reset are not supported. A pending operation must not be cleared because of a timeout. Only after the original call has ended and the user decides to mark it interrupted may `manage.py mark-interrupted --reason "..."` be used; this does not itself clear the gate.

Keep state and reports private. They may contain document identifiers and model details. A report is not a complete design backup.

## Local checks

Run `python -B fusion_guard/test_guard.py` from the project root. Tests use isolated fixtures and do not call Fusion. `python -B fusion_guard/manage.py status` reports the local policy and gate, not current hook trust. Never enable, disable or replace policy during an active modeling operation.
