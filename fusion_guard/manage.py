"""Local status / deliberate activation. Does not grant Codex hook trust."""
import argparse
import json
from pathlib import Path
import time

from hook import POLICY_PATH, STATE_ROOT, locked_state, read_json, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "enable", "disable", "mark-interrupted"])
    parser.add_argument("--reason")
    args = parser.parse_args()
    policy = read_json(POLICY_PATH)
    if args.action in {"enable", "disable"}:
        if not args.reason:
            parser.error("Enabling or disabling requires --reason; this deliberate configuration action does not grant hook trust.")
        policy["enabled"] = args.action == "enable"
        write_json(POLICY_PATH, policy)
    if args.action == "mark-interrupted":
        if not args.reason:
            parser.error("Confirm that the original tool call has ended and provide the evidence with --reason; this action does not release the gate.")
        with locked_state(STATE_ROOT) as state:
            if state["pending"]:
                state["pending"]["status"] = "interrupted"
                state["pending"]["interruption_reason"] = args.reason
    if args.action != "status":
        STATE_ROOT.mkdir(parents=True, exist_ok=True)
        with (STATE_ROOT / "management.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": time.time(), "action": args.action,
                                     "reason": args.reason}, ensure_ascii=False) + "\n")
    state = read_json(STATE_ROOT / "gate.json", {"pending": None})
    pending = state["pending"]
    print(json.dumps({"enabled": policy["enabled"], "auto_undo": policy["auto_undo"],
                      "pending": None if not pending else {k: pending.get(k) for k in
                          ("session_id", "call_id", "kind", "status", "errors")},
                      "hook_trust": "Review and trust the hooks in the Codex UI; this program does not change trust records."},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
