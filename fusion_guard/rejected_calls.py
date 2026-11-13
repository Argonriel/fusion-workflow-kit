"""Explicit acknowledgement of a host rejection before Fusion execution.

This is an administrative cancellation, never model acceptance or rollback.
The caller must hold the existing state lock and obtain explicit user review.
"""
from pathlib import Path
import ast
import copy
import hashlib
import json
import time


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def inspect_rejection(state, state_root, event_log, call_id):
    pending = state.get('pending')
    require(isinstance(pending, dict) and pending.get('status') == 'pending', 'A pending, unexecuted call is required.')
    require(pending.get('kind') in {'parameters', 'sketch', 'feature', 'edit'}, 'Only model calls are supported by this recovery path.')
    require(pending.get('call_id') == call_id and bool(call_id), 'The call ID does not match the pending operation.')
    require(not pending.get('before') and not pending.get('after'), 'Fusion evidence exists; use normal model recovery.')
    require(not state.get('probes'), 'A read-only probe is still running.')
    directory = Path(pending['transport_dir']).resolve()
    expected = (Path(state_root) / 'transport' / pending['nonce']).resolve()
    require(directory == expected and directory.is_dir(), 'The registered transport directory is invalid.')
    require(not any(directory.iterdir()), 'Execution report files exist; cancellation is not permitted.')
    log_path = Path(event_log).resolve()
    require(log_path.name.startswith('rollout-') and log_path.name.endswith(pending['session_id'] + '.jsonl'),
            'Use the original host rollout log for this session.')
    matches = []
    with log_path.open(encoding='utf-8-sig') as stream:
        for line in stream:
            event = json.loads(line)
            payload = event.get('payload', {})
            item = payload.get('item', {})
            if (event.get('type') == 'event_msg' and payload.get('type') == 'item_completed'
                    and item.get('id') == call_id and item.get('type') == 'McpToolCall'):
                matches.append((event, hashlib.sha256(line.encode('utf-8')).hexdigest()))
    require(len(matches) == 1, 'Exactly one original completed host event must match this call.')
    event, event_hash = matches[0]
    payload, item = event['payload'], event['payload']['item']
    require(payload.get('thread_id') == pending['session_id'], 'The host session does not match.')
    require(item.get('server') == 'fusion' and item.get('tool') == 'fusion_mcp_execute', 'Unexpected host tool identity.')
    require(item.get('status') == 'failed' and not item.get('result'), 'The event is not a host rejection without a tool result.')
    error = item.get('error', {}).get('message', '')
    require(error.startswith('This action was rejected due to unacceptable risk.\nReason: ')
            and 'Do not bypass this rejection' in error, 'The event is not the supported explicit host approval rejection.')
    start, end = payload.get('started_at_ms'), payload.get('completed_at_ms')
    require(type(start) is int and type(end) is int and end >= start
            and abs(start / 1000 - pending['created_at']) < 10, 'The recorded call timing does not match.')
    args = item.get('arguments', {})
    require(args.get('featureType') == 'script' and args.get('object', {}).get('readOnly') is not True, 'Unexpected rejected request type.')
    script = args.get('object', {}).get('script')
    require(isinstance(script, str), 'The original injected request is missing.')
    tree = ast.parse(script)
    directories = [n.value.value for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == '_fg_report_directory' for t in n.targets)
                   and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)]
    require(len(directories) == 1 and Path(directories[0]).resolve() == directory, 'The host request uses a different report directory.')
    require(any(isinstance(n, ast.Constant) and n.value == pending['nonce'] for n in ast.walk(tree)), 'The host request nonce does not match.')
    return {'host_event_sha256': event_hash, 'host_event_log': str(log_path),
            'host_error': error, 'completed_at_ms': end,
            'injected_source_sha256': hashlib.sha256(script.encode()).hexdigest(),
            'call_id': call_id, 'nonce': pending['nonce'], 'fusion_report_files': 0}


def acknowledge_rejection(state, state_root, event_log, call_id, user_confirmed, reason):
    require(user_confirmed is True and isinstance(reason, str) and len(reason.strip()) >= 10,
            'Explicit user acknowledgement and a recorded reason are required.')
    proof = inspect_rejection(state, state_root, event_log, call_id)
    pending = copy.deepcopy(state['pending'])
    audit = {'status': 'host_rejected_before_execution', 'time': time.time(),
             'operation': pending, 'proof': proof, 'user_review': reason,
             'model_acceptance': False, 'automatic_undo': False}
    directory = Path(state_root) / 'rejected_calls'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (pending['nonce'] + '.json')
    # Exclusive creation preserves earlier audits. A crash before the gate is
    # committed leaves the gate in place and requires review; it never retries.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(audit, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    state['pending'] = None
    return path
