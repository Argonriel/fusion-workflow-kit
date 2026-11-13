"""Local status / deliberate activation. Does not grant Codex hook trust."""
import argparse
import json
from pathlib import Path
import time

from hook import POLICY_PATH, STATE_ROOT, locked_state, read_json, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["status", "enable", "disable", "mark-interrupted", "inspect-rejection", "acknowledge-rejection"])
    parser.add_argument("--reason")
    parser.add_argument("--call-id")
    parser.add_argument("--event-log")
    parser.add_argument("--confirm-user-review", action="store_true")
    args = parser.parse_args()
    policy = read_json(POLICY_PATH)
    if args.action in {"inspect-rejection", "acknowledge-rejection"}:
        from rejected_calls import inspect_rejection, acknowledge_rejection
        if not args.call_id or not args.event_log:
            parser.error("Supply the exact call ID and original host rollout event log.")
        if args.action == "inspect-rejection":
            proof = inspect_rejection(read_json(STATE_ROOT / "gate.json"), STATE_ROOT, args.event_log, args.call_id)
            print(json.dumps({"verified_host_rejection": True, "call_id": proof["call_id"],
                              "nonce": proof["nonce"], "fusion_report_files": 0,
                              "user_acknowledgement_required": True}, indent=2))
            return
        with locked_state(STATE_ROOT) as state:
            path = acknowledge_rejection(state, STATE_ROOT, args.event_log, args.call_id,
                                         args.confirm_user_review, args.reason)
        print(json.dumps({"status": "host_rejected_before_execution", "audit_file": str(path)}, ensure_ascii=True))
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
