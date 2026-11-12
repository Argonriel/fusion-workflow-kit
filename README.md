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
4. Fill in the [part specification](specs/PART_SPEC_TEMPLATE.md), then run the [editable-timeline pilot](docs/ACCEPTANCE.md).

## Included

- `fusion_guard/` - complete runtime, installer, rules, probe and tests.
- `specs/` and `examples/` - part template and a guarded parameter edit.
- `tests/` - installer regression tests.
- `docs/` - setup, workflow, quick-start PDF, research and limitations.

All project-owned runtime code is included. Fusion, Codex and Python are external prerequisites; no additional Python packages are required for the hooks or tests.

**Status:** candidate release; 50 local tests pass. Each installation still needs a live probe and disposable-design pilot. Automatic Undo/Redo and parameter perturbation are disabled. See [limitations](docs/LIMITS.md) and [validation](VALIDATION.json).

Inspired by uwu's workflow prototype; see [integration decisions](docs/INTEGRATION.md) and [provenance](docs/PROVENANCE.md).
