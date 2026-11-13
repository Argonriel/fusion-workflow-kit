# Measured independent-design pilot

Release: 0.2.0-rc1. Run date: 12 November 2026 (America/Los_Angeles).
Environment: Fusion 2706.1.17, Codex desktop on Windows, local Fusion MCP and
genuine project PreToolUse/PostToolUse hooks. This summary contains synthetic
test dimensions; private cloud identities and raw reports remain local.

## Results

| Check | Observed result |
|---|---|
| Scoped document lifecycle | Folder creation, new document and first save accepted; cloud completion confirmed read-only |
| Native baseline | One solid, four timeline items, two fully constrained sketches, zero Base Features and zero warnings/errors |
| Baseline geometry | 80 x 50 x 4 mm; four 5 mm holes at (+/-30, +/-15) mm |
| Deliberate length edit | 96 x 50 x 4 mm; hole centers moved to (+/-38, +/-15) mm; hole diameters remained 5 mm |
| Deliberate restoration | Returned to the baseline dimensions, centers and volume without adding timeline items |
| Versioned saves | New revisions accepted only after coherent next-version metadata became available |
| Independent cloud copy | Distinct cloud ID; pinned source version and native history retained; no child references |
| Copy-only edit | Saved source remained 80 mm while the saved copy became 96 mm; both ended clean |
| Source preservation | Inventoried pre-existing open-document IDs, versions, names and modification flags remained unchanged |
| Final gate | No pending operation |

The geometry tolerance was 0.01 mm. The maximum measured dimensional deviation
across six retained measurement stages was below 0.000001 mm. Baseline/restored
volume was 15685.840734641 mm3; the 96 mm plate volume was 18885.840734641 mm3.
Both agree with rectangular volume minus four cylindrical through-holes.

## Behavior exercised and corrected

- Initial saves can expose a temporary cache path before the cloud ID exists.
  Relationship properties must wait for cloud completion.
- This Fusion build changed the new document's creation ID and empty root name
  during first save. The receipt records the exact identity transition; cloud ID
  and version identify the saved file.
- A subsequent save can initially return the previous revision with
  `isComplete:true`. The guard waits for the expected next revision.
- Native rectangle creation required explicit horizontal/vertical constraints.
  A shared construction layout avoided redundant hole-center constraints.
- User-reviewed initial/working-save reconciliation retained the original failed
  reports and verified the expected result read-only. Host rejection recovery
  retained a separate audit for a call that never executed in Fusion.

The accepted scripts are in [examples/pilot](../examples/pilot/README.md).
There are 96 passing local regression tests, including failure-report retention,
nonce-bound reports, cloud waiting, source/destination scope and reviewed recovery.
Local tests are distinct from the live measurements above.

## Scope

This qualifies the recorded independent native-design workflow on one installation.
It does not qualify external-reference remapping, historical-version copying,
automatic Undo/Redo, automatic parameter perturbation, or another client/tool
schema. It does not establish production load capacity, actuator suitability,
material properties, fit, fatigue life or manufacturing accuracy. Every recipient
still needs the unchanged live probe and a disposable measured pilot.
