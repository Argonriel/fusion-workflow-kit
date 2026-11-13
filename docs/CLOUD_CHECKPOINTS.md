# Cloud checkpoint at the end of every edit round

Every round that changes a design must end with an accepted save to Fusion cloud
and confirmation of the resulting version. Local reports, exports and an API
submission alone do not complete the round. A round is one coherent requested
change or milestone, potentially containing several separately accepted modeling
steps. Close it before reporting completion, handing off, or leaving its document
for the next task. Do not defer its save until the whole project is finished.

This is a required assistant workflow. The existing hooks validate an explicitly
requested save; they do not start background saves, detect every round boundary,
or automatically save when a chat ends. A read-only round needs no new version.

## Keep one working copy and a clear lineage

Preserve the original. For each selected source revision and intended branch,
create one separately identified native working copy in the review folder.
Record the source cloud file ID, exact version and version ID, the working file
ID, destination folder, date, owner and purpose before editing. Confirm the
active document by ID, not its name alone.

Continue subsequent rounds on that same working file and save its next cloud
versions. Do not create another copy for every round. Create a new copy only for
a deliberate branch or a newly selected source revision, recording its parent
and reason. Do not silently replace a working copy with a newer original.

The two forms of history serve different purposes:

| Record | What it explains |
|---|---|
| Native parameters, sketches and feature timeline | How the shape was built and which existing operation to edit |
| Cloud file versions | The saved state of one document at successive checkpoints |
| Source-to-copy map and round records | Which source revision a branch came from, why it changed and what was verified |

A copy has a different cloud identity and its own version series. Keep the source
history available and link the exact starting revision explicitly; a copy is
not a continuation of the source's cloud version numbers. Preserve useful native
history rather than replacing the part with an STL or a newly generated solid.
Working directly in an original keeps one version series, but changes the shared
source; it is outside this source-preserving workflow without separate authority.

A copied assembly can still reference original children. The current guarded
document workflow does not authorize edits to such copies. Do not infer that
copying a parent makes every referenced component independent.

## Required closeout sequence

1. Finish the planned changes as separate accepted native modeling steps. Check
   the specified dimensions, interfaces and other acceptance criteria. No failed,
   interrupted or pending operation may be treated as an accepted result.
2. Verify the registered working file's ID, folder, current version and intended
   modifications. Save only this round's authorized work. Never save an original,
   an unrelated dirty document or another writer's work as part of closeout.
3. Submit one `save_working_document` request through the qualified
   [document workflow](DOCUMENT_OPERATIONS.md). Keep saving separate from modeling
   scripts. A new design must first have completed its empty initial save before
   any modeling begins.
4. If the save is awaiting cloud processing, run the unchanged
   `fusion_guard/document_probe.py` with `readOnly:true`. Do not resubmit the save.
   Require PostToolUse acceptance: same working identity and folder, expected
   next version, coherent complete cloud metadata, unchanged model observables
   across the save, and no remaining unsaved changes. A complete *old* version
   does not confirm the new save.
5. Record the source revision, working file ID, version before/after the save,
   change and reason, affected parameters/features, acceptance evidence and
   limitations in a local [round record](../specs/ROUND_RECORD_TEMPLATE.md).
   Record the save report reference and confirmation time. Link that record from
   the source map. Report the saved version when handing off or reporting completion.

If one authorized round affects several eligible independent working files,
finish this sequence for each file, one accepted save at a time. The round is
complete only when all are confirmed. This does not expand permission to edit
external-reference assemblies. If the round's last changes are already covered
by an accepted cloud save, verify and record that version; do not create a
duplicate version just to repeat closeout.

If saving fails, cloud confirmation is unavailable, or evidence is incomplete,
report **Cloud save unconfirmed / round incomplete**. Preserve the original
error and gate, continue only permitted read-only checks, and follow the existing
recovery procedure. Do not upload failed geometry to manufacture a checkpoint.
An interruption before closeout leaves the round incomplete; reconcile its
actual saved and unsaved state before resuming work.

If no qualified save path or destination exists, establish one before starting
an edit round. Do not silently substitute a local export. This procedure saves
CAD to the authorized Fusion cloud folder; it does not authorize publishing CAD,
private IDs or raw reports to GitHub or changing sharing permissions.

## API basis and qualification

Autodesk documents that [Document.save](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Document_save.htm)
saves a document version and that [DataFile.isComplete](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_DataFile_isComplete.htm)
confirms cloud processing after submission. The [measured pilot](LIVE_QUALIFICATION.md)
qualified the guarded save and independent-copy operations on the recorded
installation. This closeout rule uses that path; it adds no automatic save hook
or new model mutation mechanism.
