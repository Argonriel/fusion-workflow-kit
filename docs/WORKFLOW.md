# Fusion Workflow Kit

Version 0.2.0-rc1 | 12 November 2026 | Codex on Windows

Build a native, editable Fusion timeline one accepted step at a time. Start with a part specification, use named parameters and constrained sketches, and verify that later edits produce the intended geometry.

This kit combines the specification-first workflow suggested by uwu's supplied prototype with the existing project Fusion Guard implementation. The runtime is a review candidate, not a certified or universally compatible Fusion integration.

## Start here

1. Read `docs/Quick_Start.pdf` for the workflow and installation checklist.
2. Read `docs/INTEGRATION.md` for what was retained, adapted, and deferred.
3. Fill in `specs/PART_SPEC_TEMPLATE.md` before building a part.
4. Run the local tests and install into a separate pilot project as described below.
5. Verify the real hook path with `fusion_guard/probe.py`, then use `docs/ACCEPTANCE.md` in a disposable test design.

`docs/Research_Guide.pdf` provides the earlier web research and 22 primary sources. This integration guide sets the implementation scope: native timeline construction is the primary workflow; AutoTimeline is an optional imported-solid recovery experiment.

## Compatibility

- Windows, PowerShell, Python 3.11 or later, local Codex, and local Fusion on the same computer.
- The supported tool contract is `mcp__fusion__fusion_mcp_execute` with `featureType: "script"`, `object.script`, and `object.readOnly`. The server namespace must be `fusion`.
- Scripts use one `def run(_context: str):` entry point. The tool must accept the rewritten script provided by the pre-hook.
- Fusion and Codex must both be able to read and write the project's local report path.
- The installer is Windows-specific. Claude Code, another MCP schema, cloud Fusion, and macOS require separate adapters and qualification.

This is an engineering guardrail, not a Python security sandbox or a complete control boundary. Some non-script tool calls pass through without full model inspection. GUI changes, other clients, other tool namespaces, and cloud sessions are outside this guard.

## Install in a pilot project

Use a stable Python installation that you control. Verify `python --version` and its executable path. Run both test commands below from the extracted kit root before copying the runtime into a project. Installation commands run from the destination project root.

```powershell
python -B fusion_guard/test_guard.py
python -B -m unittest discover -s tests -v
```

For a new project, copy `fusion_guard/`, `specs/`, and the relevant documentation into the project. Do not overwrite an existing Fusion Guard installation, its policy, or its state with this release. Existing installations need a reviewed migration after all Fusion operations have finished.

```powershell
python -B fusion_guard/install.py
```

Review the generated `fusion_guard/hooks.prepared.json`. It contains paths resolved on your own computer. Then:

```powershell
python -B fusion_guard/install.py --install
```

The installer merges this project's hook entries and the marked Fusion block in `AGENTS.md`, preserving unrelated entries and making local backups. It does not change global hooks, hook trust, or policy. Keep the folder and Python location stable; if either moves, regenerate and review the hooks while no Fusion operation is running.

In Codex, review the project configuration and all three hooks: PreToolUse, PostToolUse, and Stop. Hook trust is separate from the policy switch. The distribution policy starts disabled so copying files does not activate it.

After all other Fusion writers have stopped, explicitly enable the pilot policy:

```powershell
python -B fusion_guard/manage.py enable --reason "Start qualification in a disposable Fusion design"
```

Open the pilot design in Fusion. Ask Codex to pass the complete, unchanged contents of `fusion_guard/probe.py` as `object.script` with `featureType: "script"` and `object.readOnly: true`. Do not execute the probe through the local Python interpreter.

Require both the tool's inspection feedback and a matching local `inspection` report under `fusion_guard/state/reports`. The probe deliberately fails if the hook has not injected inspection. Files on disk, an enabled policy, or trusted settings alone are not proof. If necessary, restart the client after outstanding operations finish and repeat the read-only probe. Never edit the probe to make it pass.

## Daily workflow

**Specify -> inspect -> identify working copy -> native steps -> accept and measure -> save to Fusion cloud -> confirm version -> record and hand off.**

Preserve the original and record its exact revision when creating a native working
copy. Reuse that working file across subsequent rounds so its cloud versions form
one continuous sequence. Preserve its editable sketches, parameters and feature
history. Create another copy only for an explicitly recorded branch or new source
revision, not for every save.

Every edit round must finish the [cloud checkpoint procedure](CLOUD_CHECKPOINTS.md)
before completion or handoff. A round can contain several accepted modeling
steps; each step still needs its own acceptance. Save the authorized working file
through the qualified document path, wait for the expected cloud version and a
clean document, and retain a [round record](../specs/ROUND_RECORD_TEMPLATE.md).
An accepted model edit or a local report alone does not complete the round.
Read-only work does not require another version. This is an assistant closeout
requirement, not an automatic save performed by the Stop hook.

Each modifying call starts with exactly one mode comment:

| Mode | Intended step | Accepted timeline delta |
|---|---|---|
| `# fusion-guard: parameters` | Create or adjust named user parameters | 0 |
| `# fusion-guard: sketch` | Create or edit one sketch and fully constrain it | 0 or 1 |
| `# fusion-guard: feature` | Create one native feature | 1 |
| `# fusion-guard: edit` | Edit existing feature/model parameter expressions | 0 |

Use `ValueInput.createByString("parameter_name")` or a parameter expression. Parameter creation values include units and explanatory comments. Fixing every sketch entity is not an acceptable substitute for dimensions and geometric relations. Wait for post-hook acceptance before the next change.

If inspection fails, stop modifying. Preserve the error and use read-only inspection. A person checks and restores the model; the standard probe can clear a failed/interrupted gate only when recorded observables match the baseline. This is not a full-document rollback guarantee. Do not delete state, reset the gate, auto-undo, or delete the last feature to manufacture acceptance.

## Validation and release status

See [VALIDATION.json](../VALIDATION.json) for the exact tests completed for this release. Automated
tests use local fixtures or disposable filesystem copies. The separate
[live qualification](LIVE_QUALIFICATION.md) used newly created synthetic designs
and verified initial save, versioned saves, a measured edit/restoration and an
independent cloud copy. Recipient-specific hook loading and the geometry pilot
remain required.

The optional [document workflow](DOCUMENT_OPERATIONS.md) uses fixed requests,
scoped folders, registered working identities and read-only confirmation of cloud
completion. It does not permit arbitrary document-management code in model scripts.

Known limits, including unsupported timeline rollback setters and the distinction between health and intent, are in [LIMITS.md](LIMITS.md). Automatic parameter perturbation and automatic Undo/Redo are not included.

## Share and maintain

Send the versioned ZIP and the quick-start PDF to teammates. The ZIP is ready to become a source repository; use versioned releases and record validation per release. Do not share generated state, report transports, backups, prepared hooks, or project CAD. `SHARE_MESSAGE.txt` contains a short announcement you can copy.

## Sources and attribution

Workflow concepts were informed by uwu's `fusion-cad-hooks` prototype supplied for review. This release does not bundle that prototype or its discussion logs. See `docs/PROVENANCE.md` for source boundaries and checksums. No third-party license is invented or granted by this package.

Official references: [Codex hooks](https://learn.chatgpt.com/docs/hooks), [Fusion TimelineObject](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_TimelineObject.htm), [Fusion computeAll](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_Design_computeAll.htm).
