"""Trusted fixed document operations embedded by the hook, never user scripts.

Uses the existing nonce-bound report transport. It does not recompute, activate,
close, delete, or save any source document. Exceptions are reported and re-raised.
"""


def _fgd_doc(doc):
    saved = doc.isSaved
    file = doc.dataFile if saved else None
    return {'key': file.id + '@version:' + str(file.versionNumber) if file else 'unsaved:' + doc.creationId,
            'creation_id': doc.creationId, 'file_id': file.id if file else None,
            'version': file.versionNumber if file else None, 'name': doc.name,
            'saved': saved, 'modified': doc.isModified}


def _fgd_folder(app, folder_id):
    folder = app.data.findFolderById(folder_id)
    if not folder:
        raise RuntimeError('Fusion Guard: destination folder is unavailable')
    return folder


def _fgd_file(app, file_id):
    file = app.data.findFileById(file_id)
    if not file:
        raise RuntimeError('Fusion Guard: file is unavailable')
    return file


def _fgd_file_info(file):
    if not file:
        return {'id': None, 'complete': False, 'children': None}
    identity = file.id
    # Initial saves can expose a local cache path before receiving a cloud ID.
    # Relationship properties are unavailable until cloud processing completes.
    if not identity.startswith('urn:') or not file.isComplete:
        return {'id': identity, 'complete': False, 'children': None}
    return {'id': file.id, 'version': file.versionNumber, 'version_id': file.versionId,
            'latest_version': file.latestVersionNumber, 'name': file.name,
            'folder_id': file.parentFolder.id, 'extension': file.fileExtension,
            'complete': file.isComplete,
            'children': sorted([{'id': c.id, 'version': c.versionNumber, 'version_id': c.versionId}
                                for c in _fg_items(file.childReferences)], key=lambda c: (c['id'], c['version']))}


def _fgd_folder_info(folder, children):
    result = {'id': folder.id, 'name': folder.name}
    if children == 'folders':
        result['folders'] = sorted([{'id': f.id, 'name': f.name} for f in _fg_items(folder.dataFolders)], key=lambda f: f['id'])
    else:
        result['files'] = sorted([{'id': f.id, 'name': f.name, 'version': f.versionNumber, 'version_id': f.versionId}
                                 for f in _fg_items(folder.dataFiles)], key=lambda f: f['id'])
    return result


def _fgd_snapshot(request, receipt, refresh_receipt=False):
    app = adsk.core.Application.get()
    # Fusion may enumerate the same document through both a visible tab and an
    # assembly reference. Retain multiplicity; reject conflicting aliases.
    grouped = {}
    for doc in _fg_items(app.documents):
        row = _fgd_doc(doc)
        prior = grouped.get(row['key'])
        if prior:
            if {k: v for k, v in prior.items() if k != 'aliases'} != row:
                raise RuntimeError('Fusion Guard: conflicting open aliases for the same cloud file')
            prior['aliases'] += 1
        else:
            grouped[row['key']] = dict(row, aliases=1)
    documents = sorted(grouped.values(), key=lambda d: d['key'])
    active = app.activeDocument
    snapshot = {'document_schema': 1, 'context': request, 'documents': documents,
                'active_key': _fgd_doc(active)['key'] if active else None,
                'result': dict(receipt)}
    action = request.get('action')
    if action == 'create_folder':
        snapshot['parent'] = _fgd_folder_info(_fgd_folder(app, request['parent_folder_id']), 'folders')
    if 'target_folder_id' in request:
        snapshot['target'] = _fgd_folder_info(_fgd_folder(app, request['target_folder_id']), 'files')
    source_id = request.get('source_id') or request.get('file_id')
    if source_id:
        snapshot['source'] = _fgd_file_info(_fgd_file(app, source_id))
    if active and action in {'new_document', 'save_new_document', 'save_working_document'}:
        snapshot['active_model'] = _fg_snapshot()
    if receipt.get('document_creation_id') and active and active.creationId == receipt['document_creation_id']:
        snapshot['result']['file'] = _fgd_file_info(active.dataFile if active.isSaved else None)
    elif receipt.get('file') and refresh_receipt:
        # A newly submitted cloud file can have a receipt before it is listed.
        # Keep the gate pending while the lookup is unavailable; never retry it.
        identity = receipt['file'].get('id')
        current_file = app.data.findFileById(identity) if identity and identity.startswith('urn:') else None
        if current_file:
            snapshot['result']['file'] = _fgd_file_info(current_file)
        elif receipt['file'].get('complete') is True:
            raise RuntimeError('Fusion Guard: an accepted file identity is no longer available')
    if receipt.get('document'):
        found = [d for d in documents if d['creation_id'] == receipt['document']['creation_id'] and not d['saved']]
        if len(found) == 1:
            snapshot['result']['document'] = found[0]
    if receipt.get('document_creation_id'):
        file = snapshot['result'].get('file') or {}
        active_row = next((d for d in documents if d['key'] == snapshot['active_key']), {})
        snapshot['result']['metadata_coherent'] = (active_row.get('file_id') == file.get('id')
                                                   and active_row.get('version') == file.get('version'))
    return snapshot


def _fgd_preflight(request, before, registry, session):
    app = adsk.core.Application.get()
    action = request['action']
    for doc in before['documents']:
        intended_save = (action == 'save_new_document' and doc['creation_id'] == request['creation_id'] and not doc['saved']
                         or action == 'save_working_document' and doc['file_id'] == request['file_id'])
        if doc['modified'] and not intended_save:
            raise RuntimeError('Fusion Guard: an unrelated document has unsaved work')
        if not doc['saved'] and not intended_save:
            raise RuntimeError('Fusion Guard: save the registered new document before another document operation')
    if action == 'create_folder':
        if any(f['name'] == request['name'] for f in before['parent']['folders']):
            raise RuntimeError('Fusion Guard: the folder name already exists; refusing duplicate creation')
    if action in {'new_document', 'save_new_document', 'copy_file'}:
        if any(f['name'] == request['name'] for f in before['target']['files']):
            raise RuntimeError('Fusion Guard: the target filename already exists; refusing overwrite')
    if action == 'new_document':
        if any(d['name'] == request['name'] for d in before['documents']):
            raise RuntimeError('Fusion Guard: a document with that name is already open')
    if action == 'save_new_document':
        doc = app.activeDocument
        if not doc or doc.isSaved or doc.creationId != request['creation_id']:
            raise RuntimeError('Fusion Guard: initial save requires the registered unsaved active document')
        model = before['active_model']
        if (model['timeline_count'] or model['bodies'] or model['sketches'] or model['user_parameters']
                or len(model['components']) != 1 or model['components'][0]['body_count']):
            raise RuntimeError('Fusion Guard: save the empty new document before modeling')
    if action == 'save_working_document':
        doc = app.activeDocument
        if not doc or not doc.isSaved or doc.dataFile.id != request['file_id'] or not doc.isModified:
            raise RuntimeError('Fusion Guard: save requires the registered modified active working file')
        if before['source']['children']:
            raise RuntimeError('Fusion Guard: externally referenced designs require a separately reviewed workflow')
    if action == 'copy_file':
        source = before['source']
        if (not source['complete'] or source['version'] != request['source_version'] or source['version_id'] != request['source_version_id']
                or source['latest_version'] != request['source_version'] or source['extension'] != 'f3d'):
            raise RuntimeError('Fusion Guard: source must be the complete pinned latest native-design version')
        if any(f['name'] == source['name'] for f in before['target']['files']):
            raise RuntimeError('Fusion Guard: the copy intermediate filename already exists; use a separate destination')


def _fgd_run(request, registry, session, nonce):
    receipt = {}
    before = _fgd_snapshot(request, receipt)
    _fg_emit(nonce, 'before', before, False)
    completed = False
    try:
        _fgd_preflight(request, before, registry, session)
        app = adsk.core.Application.get()
        action = request['action']
        if action == 'create_folder':
            folder = _fgd_folder(app, request['parent_folder_id']).dataFolders.add(request['name'])
            if not folder:
                raise RuntimeError('Fusion Guard: folder creation returned no result')
            receipt['folder'] = {'id': folder.id, 'name': folder.name, 'parent_id': folder.parentFolder.id}
        elif action == 'new_document':
            doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
            if not doc:
                raise RuntimeError('Fusion Guard: document creation returned no result')
            doc.name = request['name']
            receipt['document'] = _fgd_doc(doc)
        elif action == 'save_new_document':
            doc = app.activeDocument
            receipt['initial_creation_id'] = doc.creationId
            if not doc.saveAs(request['name'], _fgd_folder(app, request['target_folder_id']), 'Disposable guarded workflow document', ''):
                raise RuntimeError('Fusion Guard: initial save failed')
            receipt['document_creation_id'] = doc.creationId
            receipt['file'] = _fgd_file_info(doc.dataFile)
        elif action == 'copy_file':
            file = _fgd_file(app, request['source_id']).copy(_fgd_folder(app, request['target_folder_id']))
            if not file:
                raise RuntimeError('Fusion Guard: copy returned no result')
            if file.id == request['source_id']:
                raise RuntimeError('Fusion Guard: copy returned the source identity')
            # Only the newly returned file is renamed, never the source.
            receipt['file'] = _fgd_file_info(file)
            file.name = request['name']
            receipt['file'] = _fgd_file_info(file)
        elif action == 'save_working_document':
            doc = app.activeDocument
            receipt['initial_creation_id'] = doc.creationId
            if not doc.save('Guarded working-copy revision'):
                raise RuntimeError('Fusion Guard: working-copy save failed')
            receipt['document_creation_id'] = doc.creationId
            receipt['file'] = _fgd_file_info(doc.dataFile)
        completed = True
    except BaseException as exc:
        receipt['exception'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        _fg_emit(nonce, 'after', _fgd_snapshot(request, receipt), completed)


def _fgd_inspect(request, receipt, nonce):
    _fg_emit(nonce, 'inspect', _fgd_snapshot(request, receipt, True), True)


def _fgd_require_model_target(authorization):
    app = adsk.core.Application.get()
    doc = app.activeDocument
    if not doc:
        raise RuntimeError('Fusion Guard: there is no active working document')
    if doc.isSaved:
        if doc.dataFile.id not in authorization['file_ids']:
            raise RuntimeError('Fusion Guard: model edits are restricted to registered independent working files')
        if doc.dataFile.hasChildReferences:
            raise RuntimeError('Fusion Guard: external references need explicit copy and remapping review before edits')
    elif doc.creationId not in authorization['creation_ids']:
        raise RuntimeError('Fusion Guard: this unsaved document was not created by the current guarded session')
