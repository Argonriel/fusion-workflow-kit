# What acceptance proves

The guard records document identity, parametric mode, timeline count and end marker, feature health/messages, Base Feature count, parameter expressions, sketch summaries and basic body geometry. It traverses timeline groups and handles items without represented entities.

It checks the permitted step delta, changed sketches, new or changed warnings/errors, and whether relevant expressions appear in changed model parameters. It rejects interrupted or missing reports. These checks reduce common workflow errors.

## What acceptance does not prove

- A useful dependency graph, all intended dimensions linked correctly, complete topology preservation, mechanical function, printability, fit or collision clearance.
- A complete transaction rollback. Snapshot values are rounded and some external/custom data are outside the report.
- That all original warnings or underconstrained sketches have been fixed. The runtime reports baseline issues and blocks regressions instead of rewriting legacy models.
- That every `readOnly: true` script is semantically read-only. Static analysis is restricted but not a general proof or security boundary; label calls honestly.
- That every Fusion route is guarded. Non-script execute operations and dedicated read/update paths have different handling; GUI, alternate tool names and clients are not covered by full before/after inspection.
- That hook files being installed proves this session loaded them. Only the live read-only probe and its accepted report demonstrate that path.

## Timeline boundaries

`feature` means exactly one added item. Operations that naturally create multiple items may be rejected even if the Fusion operation is valid. Grouping and timeline marker edits are blocked by this version. Use expression edits that the guard supports; do not bypass it to reach unsupported setters.

`edit` requires zero net timeline growth, but it is not a semantic whitelist of the entities the user intended to change. Compare expected and observed geometry separately. Healthy features and unchanged counts are necessary evidence, not sufficient proof of a successful design edit.

`computeAll()` succeeding means recomputation completed; feature health must still be checked. A fully constrained sketch can still encode the wrong mechanical intent.

## Recovery and confidentiality

Retain the original error and pending gate. After a person restores the model, run the standard probe. Matching observables permit gate clearance for failed/interrupted operations; pending operations are never cleared by a timeout alone. Marking an interruption requires confirming the original call ended and recording the user's decision.

Reports can contain document IDs, names, dimensions and model details. Keep `state/`, installation backups and generated hook commands local. They are excluded from the release archive.

The optional [document workflow](DOCUMENT_OPERATIONS.md) adds separately checked
identity transitions and exact destination/source checks. It supports complete,
pinned latest native F3D files. A copied parent can still reference original
children; such copies are recorded but are not eligible for model edits. External
reference remapping, historical-version copying and general cloud file management
are not qualified.

Cloud submission is not completion. Initial saves can expose temporary local IDs,
and later saves can temporarily expose the previous complete revision. The gate
waits for coherent expected metadata without retrying writes. Failed saves require
explicit user-reviewed read-only reconciliation. A separate narrow administrative
path handles verified host approval rejections before Fusion execution; neither
path constitutes automatic rollback or bypasses a rejected action.

The [end-of-round cloud checkpoint](CLOUD_CHECKPOINTS.md) is a mandatory assistant
procedure, not a background autosave service. The current Stop hook checks
unaccepted operations; it does not detect every accepted-but-unsaved edit or
automatically save on chat termination. Complete and verify the explicit save
before declaring a round complete. Human edits and interruptions still require
checking the actual document and cloud state.
