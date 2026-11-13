# Reproduce the native plate pilot

These five separate scripts reproduce the geometry used in the measured pilot.
Run them only on a new disposable design. They do not create or save a document.

1. Configure the optional [document workflow](../../docs/DOCUMENT_OPERATIONS.md).
   Create a dedicated folder and new empty design, then complete its initial save.
2. Replace `REPLACE_WITH_REGISTERED_WORKING_FILE_ID` in every script with that
   accepted working file's exact cloud ID. Confirm it is the active document.
3. Run the unchanged standard read-only probe through the real Fusion MCP path.
4. Send each complete script through `fusion_mcp_execute`, `featureType:"script"`,
   `object.readOnly:false`, in numbered order. Require accepted PostToolUse
   completion before sending the next file. Do not concatenate the scripts.
5. Follow [the editability procedure](../../docs/ACCEPTANCE.md) for the saved
   baseline, 80-to-96 mm edit, deliberate restoration, measurement and copy test.

The rectangle uses explicit horizontal/vertical constraints. The hole sketch
uses a centered construction rectangle and reuses its fully constrained corner
points as circle centers. Dimension expressions retain the named parameters;
numeric coordinates and radii are only initial geometry seeds.

These are synthetic dimensional examples. They do not validate a production
part, material, load, servo or manufacturing process.
