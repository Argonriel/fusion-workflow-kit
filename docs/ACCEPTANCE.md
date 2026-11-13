# Qualification and editability pilot

Status: reusable acceptance procedure. This release completed [one measured live run](LIVE_QUALIFICATION.md); automated release tests do not replace qualification of another installation.

## 1. Verify the connection

Use a new, disposable parametric design. Stop other writers. Confirm the exact execute-tool name and schema, installed synchronous hooks, policy, and access to local reports. When using the [document workflow](DOCUMENT_OPERATIONS.md), create and complete the initial save of the empty registered design before modeling. Run the unchanged standard probe with `readOnly: true`. Record its accepted inspection report. No model geometry is needed for this check.

## 2. Build a small plate through native features

Create named user parameters with units and comments:

| Parameter | Initial expression | Purpose |
|---|---|---|
| plate_length | 80 mm | Overall X length |
| plate_width | 50 mm | Overall Y width |
| plate_thickness | 4 mm | Extrusion distance |
| edge_offset | 10 mm | Hole center distance from each outer edge |
| hole_diameter | 5 mm | Through-hole diameter |

Use a centered fully constrained rectangular sketch, one native extrusion, a fully constrained four-circle sketch and one through cut. Perform parameters, each sketch, and each feature as separate accepted calls. Reference the named parameters in model dimensions. A single feature may consume multiple profiles.

[Numbered example scripts](../examples/pilot/README.md) reproduce these steps.

Expected starting geometry: one solid; outer size 80 x 50 x 4 mm; four 5 mm through-holes at X = +/-30 mm, Y = +/-15 mm. Keep a named saved baseline before the edit trial using the qualified document workflow. A report is not a saved design backup.

For the MCP workflow, close this build round with the qualified guarded save and
confirm the new Fusion cloud version. Apply the [cloud checkpoint procedure](CLOUD_CHECKPOINTS.md)
to each later edit round as well; record its version and acceptance evidence.

## 3. Test an intentional edit

Change only `plate_length` from `80 mm` to `96 mm` in one parameters step. The example script assumes the baseline exists and changes this value; do not run it on a work model without checking the target document.

Require all of the following:

- No added or deleted timeline items; same intended feature sequence.
- Outer size becomes 96 x 50 x 4 mm.
- Hole centers become X = +/-38 mm, Y = +/-15 mm, retaining the 10 mm edge offset.
- Hole diameter remains 5 mm; one solid remains.
- New or changed sketches remain fully constrained; no new warnings or errors.
- Dimensions retain their expressions; no duplicate replacement geometry.

Use a stated measurement tolerance, for example 0.01 mm for this simple test. Fusion API lengths use internal centimeters: convert measurement reports to millimeters explicitly. Record both the actual measurements and the feature-health report.

Save the accepted 96 mm result and confirm its new cloud version before closing
this edit round. Treat restoration as the next deliberate round with its own
measurements and confirmed save, so both states remain traceable.

Then manually restore `plate_length` to `80 mm` through another deliberate, separately accepted edit and repeat the geometry measurements. This is a planned test sequence in a disposable design, not automatic recovery after a failed operation. If any step fails, stop and follow the guard's recovery process.

For document-workflow qualification, save the restored baseline, copy its pinned
latest version into a separate accepted folder, and require a distinct cloud file
ID. Open that copy using the dedicated document tool, verify its identity, change
only the copy to 96 mm, and save it. Measure both open designs without changing
the source: the source must remain 80 mm, the copy must be 96 mm, and both must be
clean saved documents with their native history intact.

## 4. Validate real interfaces

For a production part, replace the plate assertions with named interface checks. A servo holder must attach to its intended structure; a spool needs a defined tendon anchor and any required thread; mating parts need a stated attachment and clearance. Add interference checks and a physical fit coupon where appropriate. Timeline checks cannot supply these requirements.

## Evidence to retain locally

Record: release version; client/Fusion versions; tool schema; policy hash; probe result; baseline design version; before/after parameter expressions; timeline count; changed feature names; warning/error deltas; actual geometry measurements; human review; unresolved limitations. Share only a redacted summary.

Do not claim live qualification until this procedure has actually been run and its measurements recorded.
