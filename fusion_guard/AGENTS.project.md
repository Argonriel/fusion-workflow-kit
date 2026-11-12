# Fusion modeling rules

These rules apply only to Fusion operations in this project. They do not restrict unrelated research, file work or programming.

## Activation and coordination

- Read `fusion_guard/policy.json` first. `enabled: false` means installed but inactive. Do not switch policy during a modeling step that is already running.
- When `enabled: true`, read this file and `fusion_guard/README.md` before a new Fusion work session. Use the read-only probe to confirm that hooks are actually loaded. Do not claim protection is active until confirmed.
- Allow only one conversation to modify a Fusion document at a time. The gate coordinates calls that load these hooks in this project. It cannot lock human UI actions, other projects or conversations that have not loaded the hooks.
- Do not independently disable hooks, weaken rules, clear gate state, rewrite inspection reports or bypass the inspection path. Explain the specific reason to the user before a policy change is considered.

## Modeling method

- Use native Fusion parametric sketches, constraints, extrusions, revolves, holes, chamfers, patterns, assemblies and other features. Code may call the native API.
- Do not use `TemporaryBRepManager`, switch to `DirectDesignType`, create or edit a `BaseFeature`, or add BRep bodies directly as substitutes for parametric modeling. Existing imported bodies and Base Features may be inspected read-only; do not automatically rebuild the user's old models.
- Establish critical dimensions as named user parameters with units and descriptions first. For feature or sketch dimensions, use `ValueInput.createByString("parameter_name_or_expression")` or `parameter.expression = "parameter_name_or_expression"`. Do not evaluate expressions to floating-point values and write those values back as dimensions.
- Each mutation call must perform one verifiable step. Create parameters, create and constrain one sketch, create one feature, and edit an existing parameter or feature in separate calls. One sketch step may contain several curves and constraints. Do not create timeline features in loops.
- Fully constrain new or modified sketches before the step ends. Express design intent through dimensions and geometric relationships. Do not fix every entity merely to make the sketch appear fully constrained.
- Do not catch and hide Fusion exceptions, dynamically load external scripts, or switch, save or close documents inside scripts. Use dedicated document tools under the user's authorization. New documents may be created through the Fusion UI.

## Tool-call protocol

- Set `object.readOnly: true` for read-only scripts, and only for scripts that do not modify the document. Omit `readOnly` or set it to false for mutation scripts.
- Start each mutation script with one of these comments: `# fusion-guard: parameters`, `# fusion-guard: sketch`, `# fusion-guard: feature` or `# fusion-guard: edit`.
- A script may contain only imports, optional docstrings and one `def run(_context: str):` entry point. This version rejects additional functions, classes, dynamic execution, external imports and aliases for creation methods. Only `adsk`, `adsk.core`, `adsk.fusion`, `math` and `json` imports are supported.
- Ordinary queries may use normal read-only scripts. For the standard inspection, set `readOnly: true` and pass the full contents of `fusion_guard/probe.py` directly as `object.script`. Do not load it using `exec` or `open`.
- Hooks inject before/after inspections, recomputation and reports with random identifiers. Do not manually write or fabricate these reports. Reports include timeline count, newest item name/type, per-item health, Base Feature count, parameter expressions, sketch constraints and geometry summaries. The inspector atomically writes local reports into the state/transport directory registered for this call, and PostToolUse verifies integrity. Report writing does not modify the Fusion document and does not depend on potentially truncated stdout.
- Proceed to the next step only after acceptance passes. Even if the tool returns geometry, wait for PostToolUse acceptance.
- Reports can be large. When orchestrating tools in code, preserve the original tool result for hook inspection and print only a short summary to the conversation. Read complete data from the local reports instead of repeatedly printing the full model.

## Failure and completion

- If inspection fails, reports are missing or an operation completes only partially, stop further mutations, preserve the original error and run a read-only inspection. Moving the timeline marker back or deleting the newest feature is not complete recovery.
- Automatic Undo/Redo is disabled in this version. Ask the user to inspect and restore the model in Fusion, then run the standard read-only inspection. The gate releases automatically only when the inspection summary matches the pre-change summary. This does not constitute a full document backup or prove that every topology relationship is identical.
- If a call was interrupted and the gate remains pending, first confirm that the original call is no longer running. The user must then decide whether to mark it interrupted. Do not clear locks automatically because of a timeout.
- The Stop check reports an unaccepted state once to avoid an infinite loop. If unresolved issues remain, the final response must explicitly state **Unaccepted / recovery pending**.
- Parameter perturbation and automatic rollback require separate future qualification. Do not enable them until they have been validated in an independent test document. Do not perform destructive experiments on an existing working model.

These checks are engineering constraints that reduce accidental mistakes. They are not a complete Python security sandbox and do not prove mechanical design intent, manufacturability or correctness for every parameter combination.
