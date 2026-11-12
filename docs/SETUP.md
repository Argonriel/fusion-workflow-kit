# Set up a new Windows computer

This repository contains the guard runtime, installer, project rules, templates, examples, tests and acceptance procedure. It does not depend on another person's project directory. Generated paths and state are created on your own computer.

## 1. Install the external prerequisites

| Prerequisite | What to obtain |
|---|---|
| Autodesk Fusion | A desktop installation with access to the local Fusion MCP Server. Install and sign in through Autodesk. |
| Local Codex client | A current client supporting Streamable HTTP MCP and the synchronous hooks used here. Sign in with your own account. |
| Python 3.11 or later | A stable local installation, available as `python` in PowerShell. The guard and its tests use only the Python standard library. |
| Git (optional) | Clone the repository, or download and extract its ZIP without Git. |

Fusion, Codex and Python are separately installed products, not repository payloads. There is no `pip install adsk` step: the `adsk` API is supplied inside Fusion, where model scripts run. The local Python interpreter runs the hooks and tests only.

Check the local Python before continuing:

```powershell
python --version
python -c "import sys; print(sys.executable)"
```

Keep that interpreter and the project at stable locations. The installer records their absolute paths when it generates hook commands.

## 2. Enable the local Fusion server

Start Fusion. In **Preferences > General > API**, enable **Fusion MCP Server**. The documented default endpoint is `http://127.0.0.1:27182/mcp`; use the configured port if different. Keep Fusion running. If the option is unavailable, resolve the Fusion version/access requirement before continuing. See [Autodesk's connection guide](https://help.autodesk.com/cloudhelp/ENU/ADSKMCP-FusionDesktopMcp/files/ADSKMCP_FusionDesktopMcp_connecting_to_the_fusion_mcp_server_html.html).

## 3. Connect Codex and verify the tool contract

In the desktop client's **Settings > MCP servers**, add a Streamable HTTP server named **fusion**, enter the local URL, save and restart the connection. Alternatively, use the Codex CLI:

```powershell
codex mcp add fusion --url http://127.0.0.1:27182/mcp
```

For manual configuration, merge this entry into the appropriate Codex `config.toml` without replacing existing entries:

```toml
[mcp_servers.fusion]
url = "http://127.0.0.1:27182/mcp"
```

Use one configuration method. See the [official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp).

Inspect the connected tool list and schemas before modifying a design. This runtime expects:

| Field | Required contract |
|---|---|
| Codex tool name | `mcp__fusion__fusion_mcp_execute` |
| Execution type | `featureType: "script"` |
| Script field | `object.script` |
| Read-only flag | `object.readOnly` |
| Python entry point | `def run(_context: str):` |

The endpoint alone does not prove this contract matches your installed version. If names or argument shapes differ, stop here and qualify an adapter; do not rename a matcher and assume coverage. A cloud Fusion Data server is a different connection and does not meet this local runtime's requirements.

## 4. Run local tests and install the project hooks

Open PowerShell in the downloaded repository folder. Use this folder as a new pilot project. It contains every project-owned runtime file needed for the steps below.

```powershell
python -B fusion_guard/test_guard.py
python -B -m unittest discover -s tests -v
python -B fusion_guard/install.py
```

Review `fusion_guard/hooks.prepared.json`, then install:

```powershell
python -B fusion_guard/install.py --install
```

The installer creates the project's `.codex/hooks.json` and a marked Fusion rule block in `AGENTS.md`. It preserves unrelated hook entries, backs up replaced files, and leaves policy and global configuration unchanged. It does not install a Fusion server or grant trust.

To use the guard in a different new modeling project, copy `fusion_guard/` and the relevant `specs/` and `docs/` files there, then generate and install hooks from that destination. Do not copy generated hooks from another computer. Do not overwrite an existing guard, policy or state; upgrades need a reviewed migration while no model operation is running.

## 5. Trust, enable and prove the path

Open the project in local Codex. Review the project configuration and the three hooks: **PreToolUse**, **PostToolUse** and **Stop**. In the desktop client, use **Review hooks** or **Settings > Hooks**; the CLI provides `/hooks`. Changed hook definitions require another review. See [official Codex hook documentation](https://learn.chatgpt.com/docs/hooks).

The distributed policy starts disabled. After all other Fusion writers have stopped, enable it for the pilot:

```powershell
python -B fusion_guard/manage.py enable --reason "Qualify this installation in a disposable design"
```

Open a new disposable parametric design in Fusion. Ask Codex:

> Read the project Fusion rules and policy. Pass the complete, unchanged contents of fusion_guard/probe.py to the Fusion execute tool with featureType set to script and object.readOnly set to true. Preserve the original tool return and confirm that PostToolUse accepts the matching local inspection report. Do not modify the model.

Require both inspection feedback and the matching `inspection` report under `fusion_guard/state/reports`. The probe intentionally raises an error if hooks have not injected inspection. Installed files, trusted settings and `enabled: true` do not by themselves demonstrate that this session is protected.

If the probe fails, preserve the error and inspect connection, schema, trust and path access. If necessary, finish outstanding calls, restart the client and repeat the unchanged probe. Do not remove the probe's exception or create geometry to test activation.

## 6. Qualify a real edit

Complete [the mounting-plate pilot](ACCEPTANCE.md), then fill in [the part specification](../specs/PART_SPEC_TEMPLATE.md) for real work. Record measured geometry changes, feature health and the actual client/Fusion versions. Local unit tests are not evidence of live Fusion qualification.

Automatic parameter perturbation and automatic rollback remain disabled. See [limits and recovery](LIMITS.md) before modeling. Keep generated state, model reports, CAD files and installation backups out of commits.
