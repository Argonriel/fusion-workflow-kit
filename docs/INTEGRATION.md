# Integration decisions

The requirement is an editable native design history: when a dimension or feature is wrong, revise the existing model instead of regenerating the whole part. The supplied prototype's communications note supports this interpretation; it is a discussion summary, not a verified transcript.

## What came from each input

| Input | Contribution | Treatment |
|---|---|---|
| uwu's prototype | Part specification; interfaces; critical dimensions; stepwise verification; editability as an acceptance goal | Adapted into templates and a measurable pilot |
| Existing Fusion Guard | Restricted script lint; before/after inspection; project gate; document identity; full reports with nonce and hash verification | Retained in an isolated distribution copy |
| Web/API research | Timeline health semantics, expression-based dimensions, native edit limitations, tool comparisons, AutoTimeline | Linked reference material; capabilities distinguished from implemented support |
| Release integration | Portable runtime copy and installer generation; mixed-hook preservation; isolated tests and packaging | New distribution work, not installed over an active project |

## Why the two hook packages are not stacked

The prototype registers Claude Code hooks, uses a different script/output protocol, and contains an unconfigured execute-tool placeholder. Its pre-hook does not reserve the project gate before mutation, and the first mutation has no timeline baseline. Its timeline test only bounds positive growth. It reads stdout reports, and its reset command drops verification state without proving restoration.

The retained runtime reserves a pending operation before execution, injects snapshots around the change, verifies the expected timeline delta, and checks reports bound to the current call. These are the stronger foundations for the Codex route.

Two overlapping hook stacks would add competing gates and recovery rules. This release installs one Codex stack only. Official Codex documentation also states that matching command hooks may run concurrently; hook ordering must not be used as a coordination mechanism.

## What is intentionally deferred

- **Automatic flex testing:** the prototype changes parameter expressions to 95% and 105%. This is a model mutation, not a read-only check. Its absence-of-new-errors criterion does not prove that the intended geometry moved. Failed restoration also needs stronger handling. The kit supplies a human-controlled pilot with geometric assertions instead.
- **Automatic rollback:** no automatic Undo/Redo, state reset, or delete-last-feature recovery.
- **Generic timeline editing:** the retained guard blocks marker movement, `rollTo`, reordering and timeline grouping in modifying scripts. Native setters requiring marker rollback need a separately reviewed extension.
- **Claude adapter and cloud execution:** not included in this Codex-first release.
- **Semantic change allowlists:** the specification states expected changes, but the guard does not yet enforce a complete allowed-parameter/entity list.

## AutoTimeline's role

AutoTimeline is useful for trying to reconstruct a plausible feature history from an existing solid. It does not establish that the recovered sequence is the original design intent. New AI-created parts should use native parameterized sketches and features from the start.

AutoTimeline is not required to use this kit and is not invoked by its hooks. Availability depends on Autodesk's current preview and entitlement requirements. See the research guide and [official Generate Timeline help](https://help.autodesk.com/cloudhelp/ENU/Fusion-Designs/files/ASM-GENERATE-TIMELINE.htm).
