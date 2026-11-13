"""Strict document requests and post-operation acceptance, outside Fusion.

This module never calls Fusion or changes the gate itself. The trusted hook owns
transport, serialization, and registry updates. A request is data, not user code.
"""
from __future__ import annotations

import ast
import copy
import json
import re

SENTINEL = 'Fusion Guard document handler was not injected.'
FIELDS = {
    'create_folder': {'action', 'parent_folder_id', 'name'},
    'new_document': {'action', 'target_folder_id', 'name'},
    'save_new_document': {'action', 'target_folder_id', 'creation_id', 'name'},
    'copy_file': {'action', 'target_folder_id', 'source_id', 'source_version', 'source_version_id', 'name'},
    'save_working_document': {'action', 'file_id'},
}


class DocumentPolicyError(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise DocumentPolicyError(reason)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, 'Duplicate request key: ' + key)
        result[key] = value
    return result


def request_source(request=None, inspect=False, reconcile=False):
    marker = 'document_reconcile' if reconcile else ('document_inspect' if inspect else 'document')
    payload = '' if inspect else '# fusion-document: ' + json.dumps(request, ensure_ascii=True, separators=(',', ':')) + '\n'
    return '# fusion-guard: ' + marker + '\n' + payload + 'def run(_context: str):\n    raise RuntimeError(' + repr(SENTINEL) + ')\n'


def parse_request(source, read_only):
    markers = re.findall(r'^# fusion-guard: (document|document_inspect|document_reconcile)$', source, re.M)
    _require(len(markers) == 1, 'Exactly one document operation marker is required.')
    inspect = markers[0] == 'document_inspect'
    reconcile = markers[0] == 'document_reconcile'
    _require(read_only is (inspect or reconcile), 'Document writes require readOnly:false; inspection and reconciliation require readOnly:true.')
    payloads = re.findall(r'^# fusion-document: (.+)$', source, re.M)
    _require(len(payloads) == (0 if inspect else 1), 'Exactly one write request, or no inspection payload, is required.')
    # Compare the complete AST. Imports, extra statements, callbacks, and user
    # operations cannot be smuggled into this path, even as unreachable code.
    expected = ast.parse(request_source({}, inspect, reconcile))
    _require(ast.dump(ast.parse(source), include_attributes=False) == ast.dump(expected, include_attributes=False),
             'Document requests must contain only the fail-closed sentinel entry point.')
    if inspect:
        return None
    request = json.loads(payloads[0], object_pairs_hook=_unique_object)
    _require(isinstance(request, dict), 'The document request must be an object.')
    if reconcile:
        _require(set(request) == {'action', 'operation_nonce', 'expected_file_id', 'user_confirmed', 'reason'}, 'Invalid reconciliation request fields.')
        _require(request['action'] in {'reconcile_initial_save', 'reconcile_working_save'} and request['user_confirmed'] is True, 'Save reconciliation requires explicit user confirmation.')
        _require(isinstance(request['operation_nonce'], str) and bool(re.fullmatch('[0-9a-f]{32}', request['operation_nonce'])), 'Invalid operation nonce.')
        _require(isinstance(request['expected_file_id'], str) and request['expected_file_id'].startswith('urn:'), 'A verified cloud file ID is required.')
        _require(isinstance(request['reason'], str) and 10 <= len(request['reason']) <= 1000, 'Record the user-reviewed recovery decision.')
        return request
    action = request.get('action')
    _require(isinstance(action, str) and action in FIELDS, 'Unsupported document action.')
    _require(set(request) == FIELDS[action], 'Unexpected or missing document request fields.')
    for key, value in request.items():
        if key == 'source_version':
            _require(type(value) is int and value > 0, 'A positive integer source version is required.')
        else:
            _require(isinstance(value, str) and bool(value.strip()) and len(value) <= 512, 'Invalid request value: ' + key)
    if 'name' in request:
        name = request['name']
        _require(name == name.strip() and name not in {'.', '..'} and len(name) <= 100
                 and not any(ord(c) < 32 or c in '/\\' for c in name), 'Invalid document or folder name.')
    return request


def empty_registry():
    return {'folders': {}, 'unsaved': {}, 'files': {}}


def validate_policy(policy):
    _require(isinstance(policy, dict) and policy.get('version') == 1, 'Unsupported document policy version.')
    _require(type(policy.get('enabled')) is bool, 'Document enabled must be a boolean.')
    for key in ('allowed_parent_folder_ids', 'name_prefixes'):
        _require(isinstance(policy.get(key), list) and all(isinstance(x, str) and x for x in policy[key]), 'Invalid document policy: ' + key)
    _require(isinstance(policy.get('allowed_source_versions'), list), 'An explicit source-version list is required.')
    for entry in policy['allowed_source_versions']:
        _require(isinstance(entry, dict) and set(entry) == {'id', 'version', 'version_id'}, 'Invalid allowed source version.')
        _require(isinstance(entry['id'], str) and bool(entry['id']) and type(entry['version']) is int
                 and entry['version'] > 0 and isinstance(entry['version_id'], str) and bool(entry['version_id']), 'Invalid source identity.')
    if policy['enabled']:
        _require(bool(policy['allowed_parent_folder_ids']) and bool(policy['name_prefixes']), 'Enabled document operations need a folder scope and name prefixes.')


def authorize(request, policy, registry, session):
    validate_policy(policy)
    _require(policy['enabled'], 'Document operations are disabled in document_policy.json.')
    action = request['action']
    if 'name' in request:
        _require(any(request['name'].startswith(p) for p in policy['name_prefixes']), 'The name is outside the configured prefixes.')
    if action == 'create_folder':
        _require(request['parent_folder_id'] in policy['allowed_parent_folder_ids'], 'The parent folder is not authorized.')
    elif 'target_folder_id' in request:
        _require(request['target_folder_id'] in registry['folders'], 'The destination must be a folder created and accepted by this workflow.')
    if action == 'save_new_document':
        owned = registry['unsaved'].get(request['creation_id'])
        _require(owned is not None and owned['session_id'] == session, 'The unsaved document was not created by this session.')
        _require(owned['target_folder_id'] == request['target_folder_id'] and owned['name'] == request['name'], 'Initial save must use the registered destination and name.')
    if action == 'save_working_document':
        owned = registry['files'].get(request['file_id'])
        _require(owned is not None and owned.get('editable') is True, 'Only a registered independent working file may be saved.')
    if action == 'copy_file':
        owned = registry['files'].get(request['source_id'])
        allowed = any(e == {'id': request['source_id'], 'version': request['source_version'], 'version_id': request['source_version_id']}
                      for e in policy['allowed_source_versions'])
        _require(owned is not None or allowed, 'The source ID and version are not authorized for copying.')


def validate_snapshot(snapshot):
    _require(isinstance(snapshot, dict) and snapshot.get('document_schema') == 1, 'Invalid document report schema.')
    _require(isinstance(snapshot.get('documents'), list) and isinstance(snapshot.get('context'), dict), 'Incomplete document report.')
    keys = []
    for doc in snapshot['documents']:
        _require(isinstance(doc, dict) and isinstance(doc.get('key'), str) and doc['key'], 'Invalid open-document identity.')
        _require(type(doc.get('modified')) is bool and type(doc.get('saved')) is bool, 'Invalid open-document state.')
        keys.append(doc['key'])
    _require(len(keys) == len(set(keys)), 'Open-document identities are ambiguous.')
    _require(snapshot.get('active_key') is None or snapshot['active_key'] in keys, 'The active document is missing from the report.')
    _require(isinstance(snapshot.get('result'), dict), 'The operation receipt is missing.')


def _files(folder):
    return {f['id']: f for f in folder.get('files', [])}


def _file_key(file):
    return str(file.get('id')) + '@version:' + str(file.get('version'))


def save_model_observables(model, request, before=False):
    """Normalize only document identity and the first-save root name transition."""
    result = copy.deepcopy(model)
    _require(isinstance(result, dict), 'The save geometry report is missing.')
    result.pop('document', None)
    if request['action'] == 'save_new_document':
        _require(not result.get('timeline_count') and not result.get('bodies')
                 and not result.get('sketches') and not result.get('user_parameters'),
                 'Initial save is restricted to an empty new document.')
        components = result.get('components')
        _require(isinstance(components, list) and len(components) == 1 and components[0].get('body_count') == 0,
                 'Initial save requires exactly one empty root component.')
        root = components[0]
        _require(root.get('key') == '0:' + root.get('name', ''), 'The root component identity is invalid.')
        if before:
            root['name'] = request['name']
            root['key'] = '0:' + request['name']
        else:
            _require(root.get('name') == request['name'], 'Initial save assigned an unexpected root component name.')
    return result


def assess(before, after, request):
    """Return errors and whether a successful cloud write is still processing."""
    validate_snapshot(before)
    validate_snapshot(after)
    errors = []
    action = request['action']
    if before['context'] != after['context'] or after['context'] != request:
        errors.append('The report request does not match the authorized operation.')
    old_docs = {d['key']: d for d in before['documents']}
    new_docs = {d['key']: d for d in after['documents']}
    result = after['result']
    if action in {'copy_file', 'save_new_document', 'save_working_document'} and not isinstance(result.get('file'), dict):
        errors.append('The cloud operation receipt is missing.')
    waiting = bool(action in {'copy_file', 'save_new_document', 'save_working_document'}
                   and ((result.get('file') or {}).get('complete') is not True or result.get('metadata_coherent') is False))
    if action == 'save_working_document':
        saved, prior = result.get('file') or {}, before.get('source') or {}
        # save() can return while the old, already-complete DataFile is still
        # visible. Completion of that old revision does not confirm this save.
        if (saved.get('id') == request['file_id'] and saved.get('version') == prior.get('version')
                and saved.get('version_id') == prior.get('version_id')):
            waiting = True
    target_creation = request.get('creation_id')
    target_file = request.get('file_id')
    for key, doc in old_docs.items():
        intended_save = (action == 'save_new_document' and doc['creation_id'] == target_creation
                         or action == 'save_working_document' and key == before['active_key'])
        if not intended_save and new_docs.get(key) != doc:
            errors.append('An existing open document changed: ' + key)
    removed = set(old_docs) - set(new_docs)
    added = set(new_docs) - set(old_docs)
    if action == 'new_document':
        created = result.get('document') or {}
        if removed or len(added) != 1 or created.get('key') not in added or after['active_key'] != created.get('key'):
            errors.append('Exactly one new active document was expected.')
        if created.get('saved') is not False or created.get('name') != request['name'] or created.get('creation_id') in {d['creation_id'] for d in old_docs.values()}:
            errors.append('The new document identity or name is invalid.')
        model = after.get('active_model') or {}
        if not model.get('parametric') or model.get('timeline_count') != 0 or model.get('bodies') or model.get('sketches'):
            errors.append('The new document must be an empty parametric design.')
    elif action == 'save_new_document':
        old_key = 'unsaved:' + str(target_creation)
        saved = result.get('file') or {}
        new_key = _file_key(saved)
        if not waiting and (removed != {old_key} or added != {new_key} or after['active_key'] != new_key):
            errors.append('Initial save changed an unexpected document.')
        if waiting and (not removed.issubset({old_key}) or not added.issubset({after['active_key']})):
            errors.append('Initial save changed unrelated open-document identities.')
        saved_doc = new_docs.get(after['active_key'], {})
        # Some live Fusion builds replace the creation ID during the first save.
        # The trusted receipt binds the original object to its post-save ID;
        # names alone never establish identity.
        if (result.get('initial_creation_id') != target_creation
                or not result.get('document_creation_id')
                or saved_doc.get('creation_id') != result.get('document_creation_id')
                or saved_doc.get('name') != request['name']
                or saved_doc.get('aliases') != old_docs.get(old_key, {}).get('aliases')
                or (not waiting and (saved_doc.get('modified') is not False or saved_doc.get('saved') is not True))):
            errors.append('Initial save did not preserve the recorded identity transition or clean state.')
    elif action == 'save_working_document':
        saved = result.get('file') or {}
        expected_key = _file_key(saved)
        if not waiting and (removed != {before['active_key']} or added != {expected_key} or after['active_key'] != expected_key):
            errors.append('Saving must advance only the active working document version.')
        if waiting and (not removed.issubset({before['active_key']}) or not added.issubset({after['active_key']})):
            errors.append('Saving changed unrelated open-document identities.')
    else:
        if removed or added or before['active_key'] != after['active_key']:
            errors.append('This operation must not open, close, or switch documents.')
    if action in {'save_new_document', 'save_working_document'}:
        try:
            prior_model = save_model_observables(before.get('active_model'), request, before=True)
            saved_model = save_model_observables(after.get('active_model'), request)
            if prior_model != saved_model:
                errors.append('Saving changed model geometry, parameters, or timeline observables.')
        except (ValueError, TypeError, KeyError) as exc:
            errors.append('Invalid save geometry evidence: ' + str(exc))
    if action == 'save_working_document':
        saved_doc = new_docs.get(after['active_key'], {})
        old_doc = old_docs.get(before['active_key'], {})
        if not waiting and (saved_doc.get('modified') is not False or saved_doc.get('saved') is not True):
            errors.append('The working document was not saved cleanly.')
        if (any(saved_doc.get(k) != old_doc.get(k) for k in ('file_id', 'name', 'aliases'))
                or result.get('initial_creation_id') != old_doc.get('creation_id')
                or not result.get('document_creation_id')
                or result.get('document_creation_id') != saved_doc.get('creation_id')):
            errors.append('The working document identity changed unexpectedly during saving.')
        prior = before.get('source') or {}
        saved = result.get('file') or {}
        if not waiting and (saved.get('id') != target_file or saved.get('version') != prior.get('version', 0) + 1):
            errors.append('The working file did not advance by exactly one version.')
        if not waiting and (saved.get('name') != prior.get('name') or saved.get('folder_id') != prior.get('folder_id')):
            errors.append('Saving moved or renamed the working file.')
    if action == 'create_folder':
        bp, ap = before.get('parent') or {}, after.get('parent') or {}
        old = {f['id']: f for f in bp.get('folders', [])}
        new = {f['id']: f for f in ap.get('folders', [])}
        folder = result.get('folder') or {}
        if bp.get('id') != request['parent_folder_id'] or ap.get('id') != bp.get('id'):
            errors.append('The parent folder changed.')
        if any(new.get(k) != v for k, v in old.items()) or set(new) - set(old) != {folder.get('id')}:
            errors.append('Folder creation changed unexpected children.')
        if not folder.get('id') or folder.get('name') != request['name'] or folder.get('parent_id') != request['parent_folder_id']:
            errors.append('The created folder does not match the request.')
    if action in {'copy_file', 'save_new_document'}:
        bt, at = before.get('target') or {}, after.get('target') or {}
        old, new = _files(bt), _files(at)
        saved = result.get('file') or {}
        if bt.get('id') != request['target_folder_id'] or at.get('id') != bt.get('id'):
            errors.append('The destination folder changed.')
        additions = set(new) - set(old)
        expected_additions = {saved.get('id')}
        pending_additions_valid = len(additions) <= 1 and all(new[k]['name'] == request['name'] for k in additions)
        if any(new.get(k) != v for k, v in old.items()) or not (additions == expected_additions or waiting and pending_additions_valid):
            errors.append('The operation changed unexpected destination files.')
        if not waiting and (not saved.get('id', '').startswith('urn:') or saved.get('folder_id') != request['target_folder_id'] or saved.get('name') != request['name']):
            errors.append('The created file does not match the requested destination or name.')
        if not waiting and saved.get('version') != 1:
            errors.append('A new independent file at version 1 was expected.')
    if action == 'copy_file':
        source, current = before.get('source') or {}, after.get('source') or {}
        saved = result.get('file') or {}
        if source != current:
            errors.append('The source file identity, version, metadata, or references changed.')
        if source.get('id') != request['source_id'] or source.get('version') != request['source_version'] or source.get('version_id') != request['source_version_id']:
            errors.append('The copied source version does not match the pinned request.')
        if saved.get('id') == request['source_id']:
            errors.append('The copy must have a different cloud file ID.')
        if not waiting and saved.get('children') != source.get('children'):
            errors.append('The copy references differ and require explicit review.')
    return errors, waiting


def register(registry, request, after, session, nonce):
    updated = copy.deepcopy(registry)
    result = after['result']
    action = request['action']
    if action == 'create_folder':
        folder = result['folder']
        updated['folders'][folder['id']] = dict(folder, accepted_operation=nonce)
    elif action == 'new_document':
        doc = result['document']
        updated['unsaved'][doc['creation_id']] = {'name': request['name'], 'target_folder_id': request['target_folder_id'],
                                                'session_id': session, 'accepted_operation': nonce}
    else:
        file = result['file']
        entry = dict(file, editable=not file['children'], accepted_operation=nonce)
        if action == 'copy_file':
            entry.update(source_id=request['source_id'], source_version=request['source_version'], source_version_id=request['source_version_id'])
        elif action == 'save_new_document':
            updated['unsaved'].pop(request['creation_id'])
        else:
            entry.update({k: v for k, v in updated['files'][file['id']].items() if k.startswith('source_')})
        updated['files'][file['id']] = entry
    return updated


def model_authorization(registry, session):
    return {'file_ids': sorted(k for k, v in registry['files'].items() if v.get('editable') is True),
            'creation_ids': sorted(k for k, v in registry['unsaved'].items() if v['session_id'] == session)}
