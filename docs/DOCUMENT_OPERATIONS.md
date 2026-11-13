# Guarded document operations

This opt-in extension provides fixed document operations through the existing
Fusion MCP script endpoint. It supports creation and copying without accepting
general document-management Python from the caller. Existing model checks remain
in place. No Computer Use or automatic Undo/Redo is required.

Complete the [cloud checkpoint](CLOUD_CHECKPOINTS.md) at the end of every edit
round: reuse the identified working copy, save once after acceptance, confirm
the expected new cloud version, and retain the source lineage and round record.
Do not finish with accepted but unsaved model changes. The hooks validate a
requested save; they do not initiate saves automatically when a round ends.

## Scope and setup

1. Finish other writes and confirm the shared gate has no pending operation.
2. Install the complete updated runtime. Preserve `policy.json`, `state/`, the
   existing hook configuration and trust records. Do not replace an active policy
   with the disabled distribution policy.
3. Run the unchanged `fusion_guard/probe.py` through the real MCP connection and
   require an accepted report. Review hook trust again if the client requests it.
4. Copy `fusion_guard/document_policy.example.json` to
   `fusion_guard/document_policy.json`. With the user's authorization, enter the
   exact allowed parent-folder IDs, selected source IDs/versions, and naming
   prefixes, then enable this separate policy. Keep it local; it is ignored by Git.
5. Start in disposable folders and designs. Finish the document lifecycle and
   [plate pilot](ACCEPTANCE.md) before using the workflow for production copies.

The source list uses objects with `id`, integer `version`, and `version_id`.
Files created and accepted by this workflow are also eligible copy sources.
The current copy operation requires the complete latest native F3D version;
historical-version copying is not qualified.

## Request format

The caller sends one action through `fusion_mcp_execute`, `featureType: "script"`,
with `object.readOnly: false`. The script is a declarative request:

```python
# fusion-guard: document
# fusion-document: {"action":"create_folder","parent_folder_id":"PARENT_FOLDER_ID","name":"FG_Pilot_Source"}
def run(_context: str):
    raise RuntimeError('Fusion Guard document handler was not injected.')
```

The sentinel must remain unchanged. If injection is unavailable, the request
fails before any caller-supplied mutation. The hook validates the entire entry
point, parses the JSON strictly, checks scope, and injects a fixed implementation.
`document_ops.request_source(request)` generates this format for local tooling.

| Action | Required fields beyond `action` | Acceptance |
|---|---|---|
| `create_folder` | `parent_folder_id`, `name` | One new child under an allowed parent; existing children unchanged |
| `new_document` | `target_folder_id`, `name` | One new empty parametric document; existing documents unchanged |
| `save_new_document` | `target_folder_id`, `creation_id`, `name` | First save of this session's registered empty document to its registered destination |
| `copy_file` | `target_folder_id`, `source_id`, `source_version`, `source_version_id`, `name` | Distinct new cloud ID; pinned source unchanged; reference identities recorded |
| `save_working_document` | `file_id` | Registered active independent working file; exactly one new version; model observables unchanged by saving |

Create separate source and copy folders for the pilot. `DataFile.copy` initially
uses the source filename, so the destination must contain neither that name nor
the requested final copy name. Existing-name collisions are rejected, never
treated as permission to overwrite or reuse an unknown file.

Initial save is restricted to an empty document created by the current guarded
session. Save and accept it before adding model geometry or parameters.
After it is saved, its accepted cloud ID can be used by later sessions in the same
project. A cloud ID, not a display name or `creationId` alone, identifies a saved
working file. Open-document keys include cloud ID and version: multiple versions
of the same file can be open simultaneously. Identical aliases retain their count;
conflicting aliases fail inspection.

Live first-save observations included a changed `creationId`, a temporary local
cache ID before cloud assignment, and the root component changing from its
unsaved label to the requested document name. The trusted receipt records the
pre-save and post-save creation IDs. Initial-save acceptance permits only that
specified root-name transition on a single empty root component. Other model
observables must remain equal.

## Model edits and references

When document scope is enabled, model mutations are restricted to the registered
new/working documents. Generic save and save-on-close calls are rejected; use the
scoped save requests. Dedicated opening and non-saving closing retain their own
authorization and are blocked while an operation is pending.

A copied assembly may still reference original child documents. The first
release records those reference IDs and versions but does not remap or break
links. Such copies are not registered as editable. Read-only review is allowed.
Do not attempt to make them editable by changing registry files or by rebuilding
imported geometry. Reference isolation needs a separate qualified extension.

## Asynchronous completion and failures

Every write shares the existing single-writer gate and nonce-bound local report
transport. An accepted API submission is not complete while cloud processing is
pending. Run the exact `fusion_guard/document_probe.py` contents with
`readOnly: true`; the probe can confirm completion without repeating the write.
There is no timeout-based unlock and no automatic cleanup or retry.

Cloud relationship properties are read only after `isComplete` is true and the
file has a cloud ID. A local cache ID or inconsistent metadata snapshot keeps
the operation pending. Follow-up inspection resolves the saved file through the
recorded document identity; it does not repeat `saveAs`.

For a later save, Fusion may temporarily return the previous revision with
`isComplete:true`. That flag describes the old revision, not the new save. The
gate waits while the pinned old revision is still visible and accepts only the
expected next revision with coherent, complete metadata.

Errors, partial operations, source changes, or missing reports preserve the gate
and original response. A failed document operation requires explicit review of
both the open-document and cloud changes. Do not clear state manually or use the
model-only probe as proof that a cloud write was undone.

### User-reviewed save reconciliation

The candidate provides a narrow recovery path when a requested save occurred
but subsequent reporting failed. This path requires the user to inspect the
saved document and explicitly approve retaining that result. It is not automatic
rollback and does not turn the failed invocation into a passing invocation.

Send `document_ops.request_source(request, reconcile=True)` with `readOnly:true`.
The request must contain exactly:

- `action`: `reconcile_initial_save` or `reconcile_working_save`, matching the failed save;
- `operation_nonce`: the exact recorded failed operation nonce;
- `expected_file_id`: the user-reviewed cloud file ID;
- `user_confirmed`: `true`, only after actual explicit user confirmation;
- `reason`: the recorded review decision.

The hook requires a failed or interrupted save, its original before and
after reports, and the original registered ownership. It compares the current
read-only evidence with the requested save postconditions, including the saved
identity, name, destination, version, model observables and unchanged original
documents. An initial save must still be an empty model at version 1; a working
save must advance the same registered file by exactly one version.
A mismatch, missing evidence or incomplete cloud processing leaves the gate in
place. On success, a new reconciliation report links to the original operation;
the original failure report remains unchanged. No model or cloud write occurs.

A fixed implementation must still pass a fresh save trial after recovery.
Reconciliation alone is not evidence that the original defect has been fixed.
Other failed document operations require their own reviewed recovery procedure.

### Host approval rejection before execution

Some Codex execution paths run PreToolUse before host approval, then omit
PostToolUse when approval rejects the request. This can leave a pending model
call even though Fusion never received it. Do not retry the rejected script or
clear the gate manually.

`manage.py inspect-rejection --call-id CALL_ID --event-log ORIGINAL_ROLLOUT_LOG`
performs read-only validation. It requires one completed original host event for
the same session, call ID, injected nonce and report directory, the specific
approval-rejection result, no native before/after snapshot, and an entirely empty
registered transport directory. Native API errors and missing execution reports
are not substitutes for explicit host-rejection evidence.

After the user explicitly approves cancellation of that unexecuted call,
`manage.py acknowledge-rejection` accepts the same arguments plus
`--confirm-user-review --reason "RECORDED USER DECISION"`. It revalidates under the
normal state lock, exclusively creates a separate audit containing the original
operation and rejection evidence, then releases only that pending call. Existing
reports, working-file registrations and policies are preserved. This is neither
model acceptance nor rollback and does not authorize the rejected operation.
Review the revised action and obtain any needed approval before continuing.

This branch is qualified only for the recorded Codex rollout-event shape; other
clients or event formats fail closed. Local host logs are operational evidence,
not a cryptographic attestation against arbitrary local file tampering.

The snapshots check specified observables and fixed operations. They are not a
full backup, a general Python security boundary, or a lock against human actions
and clients outside this project's hooks.

## API basis

The fixed implementation uses Autodesk's documented
[folder creation](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_DataFolders_add.htm),
[document creation](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Documents_add.htm),
[initial save](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Document_saveAs.htm),
and [file copy](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_DataFile_copy.htm)
operations. Document creation and saving cannot run inside a Fusion command
transaction, so each installed MCP execution path needs its own live pilot.
