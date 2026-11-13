# Fusion Workflow Kit

Codex hooks and a practical workflow for building **editable, parametric Fusion models**: named parameters, constrained sketches, native features, and one verified change at a time.

## Get started

1. Install **Fusion, Codex and Python 3.11+ on Windows**. Enable Fusion's local MCP server and connect it to Codex as `fusion`: [setup from scratch](docs/SETUP.md).
2. Download this repository and open it as your pilot project. Run:

   ```powershell
   python -B fusion_guard/test_guard.py
   python -B -m unittest discover -s tests -v
   python -B fusion_guard/install.py
   ```

3. Review the generated hooks, then follow the [installation](docs/SETUP.md#4-run-local-tests-and-install-the-project-hooks) and [probe](docs/SETUP.md#5-trust-enable-and-prove-the-path) steps. Verify the read-only probe before modeling.
4. Fill in the [part specification](specs/PART_SPEC_TEMPLATE.md), then run the [editable-timeline pilot](docs/ACCEPTANCE.md). Optional [guarded document operations](docs/DOCUMENT_OPERATIONS.md) create disposable designs and independent working copies through the existing Fusion MCP connection.
5. Keep the original intact and continue work on one identified native copy. End **every edit round** with an accepted Fusion cloud save and confirmation of the new version; retain a source-to-copy map and [round record](specs/ROUND_RECORD_TEMPLATE.md). Follow the [cloud checkpoint procedure](docs/CLOUD_CHECKPOINTS.md) before reporting completion or handing off.

## Included

- `fusion_guard/` - complete runtime, installer, rules, probe and tests.
- `specs/` and `examples/` - part template, guarded parameter edit and [five native plate steps](examples/pilot/README.md).
- `tests/` - installer, document-lifecycle and reviewed recovery regression tests.
- `docs/` - setup, workflow, quick-start PDF, research and limitations.

All project-owned runtime code is included. Fusion, Codex and Python are external prerequisites; no additional Python packages are required for the hooks or tests.

The cloud checkpoint is a required workflow step using the qualified save path.
It is not a background autosave hook. Read-only rounds do not create new versions.

**Status:** v0.2.0-rc1; 96 local tests pass. The independent-design document lifecycle and measured plate edit/copy pilot passed on Fusion 2706.1.17 with Codex on Windows. See the [redacted live results](docs/LIVE_QUALIFICATION.md) and [validation record](VALIDATION.json). Each installation still needs its own live probe and disposable pilot. Automatic Undo/Redo and automatic parameter perturbation remain disabled; external-reference remapping is not qualified. See [limitations](docs/LIMITS.md).

Inspired by uwu's workflow prototype; see [integration decisions](docs/INTEGRATION.md) and [provenance](docs/PROVENANCE.md).
