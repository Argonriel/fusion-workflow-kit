"""Prepare or install project-local Windows hooks; never grants hook trust."""
import argparse
import hashlib
import sys
from hook import ROOT, read_json, write_json

BEGIN = "<!-- BEGIN FUSION GUARD PROJECT RULES -->"
END = "<!-- END FUSION GUARD PROJECT RULES -->"
STATUS = "Fusion parametric modeling check"
LEGACY_STATUS_SHA256 = "5c9d27188fda70f01553d68828af769a27c14157cfb56021d7433a9e52145db2"


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def config():
    command = ("& { $ErrorActionPreference = 'Stop'; try { "
               "$fgPython = " + ps_quote(sys.executable) + "; "
               "$fgScript = " + ps_quote(ROOT / "hook.py") + "; "
               "if (!(Test-Path -LiteralPath $fgPython) -or !(Test-Path -LiteralPath $fgScript)) { throw 'Fusion Guard runtime missing' }; "
               "& $fgPython -X utf8 $fgScript; "
               "if ($LASTEXITCODE -ne 0) { throw 'Fusion Guard process failed' } "
               "} catch { [Console]::Error.WriteLine('Fusion Guard unavailable: ' + $_.Exception.Message); exit 2 } }")
    hooks = {}
    for event in ("PreToolUse", "PostToolUse", "Stop"):
        group = {"hooks": [{"type": "command", "command": command,
                           "commandWindows": command, "timeout": 30,
                           "statusMessage": STATUS}]}
        if event != "Stop":
            group["matcher"] = "^mcp__fusion__.*$"
        hooks[event] = [group]
    return {"description": "Fusion Guard project hooks for Windows; review trust and run the probe before modeling.", "hooks": hooks}


def rules_text(existing, rules):
    block = BEGIN + "\n" + rules.rstrip() + "\n" + END
    if BEGIN in existing or END in existing:
        if existing.count(BEGIN) != 1 or existing.count(END) != 1:
            raise ValueError("Ambiguous existing Fusion Guard rule markers; refusing replacement")
        start, end = existing.index(BEGIN), existing.index(END) + len(END)
        if end < start:
            raise ValueError("Invalid existing rule block")
        return existing[:start] + block + existing[end:]
    return (existing.rstrip() + "\n\n" if existing.strip() else "") + block + "\n"


def is_ours(entry):
    status = entry.get("statusMessage", "")
    # Preserve compatibility with the original installation marker.
    return status == STATUS or hashlib.sha256(status.encode("utf-8")).hexdigest() == LEGACY_STATUS_SHA256


def merge_config(existing, prepared):
    merged = dict(existing)
    merged["hooks"] = dict(existing.get("hooks", {}))
    for event, groups in prepared["hooks"].items():
        kept = []
        for old in merged["hooks"].get(event, []):
            entries = [entry for entry in old.get("hooks", []) if not is_ours(entry)]
            if entries or not old.get("hooks"):
                kept.append(dict(old, hooks=entries))
        merged["hooks"][event] = kept + groups
    return merged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Write this project's hooks and guarded AGENTS rule block")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("This installer targets Windows PowerShell. Other platforms require a separately qualified adapter.")
    if read_json(ROOT / "state" / "gate.json", {"pending": None}).get("pending"):
        parser.error("An operation is pending. Resolve it before changing installation files.")
    prepared = config()
    write_json(ROOT / "hooks.prepared.json", prepared)
    if not args.install:
        print("Prepared hooks.prepared.json only. Inspect it, then use --install in the intended project.")
        return
    project = ROOT.parent
    destination = project / ".codex" / "hooks.json"
    rules_path = project / "AGENTS.md"
    installed = merge_config(read_json(destination, {"hooks": {}}), prepared)
    before = rules_path.read_text(encoding="utf-8-sig") if rules_path.exists() else ""
    after = rules_text(before, (ROOT / "AGENTS.project.md").read_text(encoding="utf-8"))
    for path in (destination, rules_path):
        if path.exists():
            content = path.read_bytes()
            backup = ROOT / "installation-backups" / (path.name + "." + hashlib.sha256(content).hexdigest()[:12] + ".bak")
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                backup.write_bytes(content)
    write_json(destination, installed)
    rules_path.write_text(after, encoding="utf-8")
    print("Installed project hooks and AGENTS rules. Policy, global hooks, and trust were not changed.")


if __name__ == "__main__":
    main()
