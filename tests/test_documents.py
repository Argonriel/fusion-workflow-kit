"""Document lifecycle tests use disposable state and an in-memory Fusion adapter."""
from pathlib import Path
import copy
import json
import sys
import tempfile
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / 'fusion_guard'
sys.path.insert(0, str(RUNTIME))
import document_ops as ops
import hook
import test_guard as legacy


class Items:
    def __init__(self, values=()):
        self.values = list(values)
    @property
    def count(self):
        return len(self.values)
    def item(self, index):
        return self.values[index]


class Folder:
    def __init__(self, app, identity, name, parent=None):
        self.id, self.name, self.parentFolder = identity, name, parent
        self.dataFiles = Items()
        self.dataFolders = Items()
        self.dataFolders.add = lambda name: app.folder(name, self)


class File:
    def __init__(self, app, folder, name):
        self.app, self.parentFolder, self.name = app, folder, name
        self.id = 'urn:test:file-' + str(app.next_id())
        self.versionNumber = self.latestVersionNumber = 1
        self.versionId = self.id + ':1'
        self.fileExtension = 'f3d'
        self.isComplete = not app.async_next
        app.async_next = False
        self.childReferences = Items()
        self.hasChildReferences = False
        app.files[self.id] = self
        folder.dataFiles.values.append(self)
    @property
    def childReferences(self):
        if not self.isComplete:
            raise RuntimeError('relationships are not ready')
        return self._children
    @childReferences.setter
    def childReferences(self, value):
        self._children = value
    def copy(self, folder):
        self.app.calls.append(('copy', self.id, folder.id))
        result = File(self.app, folder, self.name)
        result.childReferences = Items(self.childReferences.values)
        result.hasChildReferences = bool(result._children.count)
        if self.app.copy_callback:
            self.app.copy_callback()
        return result


class Document:
    def __init__(self, app, file=None):
        self.app, self.dataFile = app, file
        self.creationId = 'creation-' + str(app.next_id())
        self.name = file.name if file else 'Untitled'
        self.isModified = False
        self.payload = []
    @property
    def isSaved(self):
        return self.dataFile is not None
    def saveAs(self, name, folder, description, tag):
        if self.isSaved:
            raise RuntimeError('Unexpected Save As on an original')
        self.app.calls.append(('saveAs', self.creationId, folder.id))
        self.dataFile = File(self.app, folder, name)
        self.creationId = 'creation-' + str(self.app.next_id())
        self.name, self.isModified = name, False
        if self.app.save_callback:
            self.app.save_callback(self)
        return True
    def save(self, description):
        self.app.calls.append(('save', self.dataFile.id))
        file = self.dataFile
        if self.app.delayed_revision:
            self.isModified = False
            return True
        file.versionNumber += 1
        file.latestVersionNumber = file.versionNumber
        file.versionId = file.id + ':' + str(file.versionNumber)
        file.isComplete = not self.app.async_next
        self.app.async_next = False
        self.isModified = False
        if self.app.save_callback:
            self.app.save_callback(self)
        return True


class Application:
    def __init__(self):
        self.sequence = 0
        self.calls, self.files, self.folders = [], {}, {}
        self.async_next = False
        self.copy_callback = None
        self.save_callback = None
        self.delayed_revision = False
        self.data = NS(findFileById=lambda key: self.files.get(key), findFolderById=lambda key: self.folders.get(key))
        self.documents = Items()
        self.documents.add = self.add_document
        self.activeDocument = None
        self.root = self.folder('Original project', None)
        original = File(self, self.root, 'Original')
        self.original_doc = Document(self, original)
        self.documents.values.append(self.original_doc)
        self.activeDocument = self.original_doc
        self.calls.clear()
    def next_id(self):
        self.sequence += 1
        return self.sequence
    def folder(self, name, parent):
        folder = Folder(self, 'folder-' + str(self.next_id()), name, parent)
        self.folders[folder.id] = folder
        if parent:
            self.calls.append(('folder', parent.id, name))
            parent.dataFolders.values.append(folder)
        return folder
    def add_document(self, kind):
        self.calls.append(('new_document', kind))
        doc = Document(self)
        self.documents.values.append(doc)
        self.activeDocument = doc
        return doc
    def model(self):
        doc = self.activeDocument
        root_name = doc.name if doc.isSaved else '(Unsaved)'
        return {'document': {'creation_id': doc.creationId, 'name': doc.name, 'file_id': doc.dataFile.id if doc.isSaved else None},
                'parametric': True, 'timeline_count': len(doc.payload), 'marker_position': len(doc.payload),
                'timeline': copy.deepcopy(doc.payload), 'newest': None, 'base_feature_count': 0,
                'components': [{'key': '0:' + root_name, 'name': root_name, 'body_count': 0}],
                'bodies': [], 'parameters': [], 'user_parameters': [], 'sketches': [], 'latest_sketch': None}


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent, prefix='document-test-')
        assert Path(self.temp.name).resolve().is_relative_to(Path(__file__).resolve().parent)
        self.state = Path(self.temp.name) / 'state'
        self.app = Application()
        self.policy = {'version': 1, 'enabled': True, 'allowed_parent_folder_ids': [self.app.root.id],
                       'allowed_source_versions': [], 'name_prefixes': ['FG_Pilot_', 'RC_']}
        self.patch_policy = patch.object(hook, 'document_policy', lambda: self.policy)
        self.patch_policy.start()
        self.addCleanup(self.patch_policy.stop)
        self.addCleanup(self.temp.cleanup)
        self.sequence = 0
        adsk, core, fusion = ModuleType('adsk'), ModuleType('adsk.core'), ModuleType('adsk.fusion')
        adsk.core, adsk.fusion = core, fusion
        core.Application = NS(get=lambda: self.app)
        core.DocumentTypes = NS(FusionDesignDocumentType='design')
        self.modules = {'adsk': adsk, 'adsk.core': core, 'adsk.fusion': fusion}

    def event(self, source, readonly=False):
        self.sequence += 1
        return legacy.pre(source, session='test-session', call='document-call-' + str(self.sequence), readonly=readonly)

    def invoke(self, request=None, inspect=False, raw=None, reconcile=False):
        source = raw or ops.request_source(request, inspect, reconcile)
        event = self.event(source, inspect or reconcile)
        pre = hook.process(event, legacy.POLICY, self.state)
        if pre['hookSpecificOutput']['permissionDecision'] == 'deny':
            return pre
        rewritten = pre['hookSpecificOutput']['updatedInput']['object']['script']
        namespace = {}
        response = {'success': True}
        with patch.dict(sys.modules, self.modules):
            exec(compile(rewritten, '<guarded-document-test>', 'exec'), namespace)
            namespace['_fg_snapshot'] = self.app.model
            try:
                namespace['run']('')
            except Exception as exc:
                response = {'isError': True, 'message': type(exc).__name__ + ': ' + str(exc)}
        return hook.process(dict(event, hook_event_name='PostToolUse', tool_response=response), legacy.POLICY, self.state)

    def gate(self):
        return hook.read_json(self.state / 'gate.json')

    def folder(self):
        result = self.invoke({'action': 'create_folder', 'parent_folder_id': self.app.root.id, 'name': 'FG_Pilot_Review'})
        self.assertNotIn('decision', result)
        return next(iter(self.gate()['document_registry']['folders']))

    def saved_document(self):
        folder = self.folder()
        self.assertNotIn('decision', self.invoke({'action': 'new_document', 'target_folder_id': folder, 'name': 'FG_Pilot_Plate'}))
        creation = self.app.activeDocument.creationId
        self.assertNotIn('decision', self.invoke({'action': 'save_new_document', 'target_folder_id': folder, 'creation_id': creation, 'name': 'FG_Pilot_Plate'}))
        return folder, self.app.activeDocument.dataFile

    def copy_request(self, folder, source):
        return {'action': 'copy_file', 'target_folder_id': folder, 'source_id': source.id, 'source_version': source.versionNumber,
                'source_version_id': source.versionId, 'name': 'RC_Plate'}

    def failed_initial_save(self):
        folder = self.folder()
        self.invoke({'action': 'new_document', 'target_folder_id': folder, 'name': 'FG_Pilot_Plate'})
        creation = self.app.activeDocument.creationId
        def fail_after_save(doc):
            raise RuntimeError('Saved successfully; metadata was unavailable')
        self.app.save_callback = fail_after_save
        result = self.invoke({'action': 'save_new_document', 'target_folder_id': folder, 'creation_id': creation, 'name': 'FG_Pilot_Plate'})
        self.assertEqual(result['decision'], 'block')
        self.app.save_callback = None
        return {'action': 'reconcile_initial_save', 'operation_nonce': self.gate()['pending']['nonce'],
                'expected_file_id': self.app.activeDocument.dataFile.id, 'user_confirmed': True,
                'reason': 'The user inspected the newly saved test document and approved read-only reconciliation.'}

    def test_complete_lifecycle_keeps_original_unchanged(self):
        original = self.app.original_doc.dataFile
        folder, source = self.saved_document()
        # A separate copy destination avoids an intermediate filename collision.
        self.invoke({'action': 'create_folder', 'parent_folder_id': self.app.root.id, 'name': 'FG_Pilot_Copies'})
        destination = next(k for k in self.gate()['document_registry']['folders'] if k != folder)
        self.assertNotIn('decision', self.invoke(self.copy_request(destination, source)))
        registered = self.gate()['document_registry']['files']
        self.assertEqual(len(registered), 2)
        copied = next(f for key, f in registered.items() if key != source.id)
        self.assertEqual(copied['source_id'], source.id)
        self.assertTrue(copied['editable'])
        self.assertEqual((original.name, original.versionNumber, self.app.original_doc.isModified), ('Original', 1, False))
        self.assertIsNone(self.gate()['pending'])

    def test_identical_open_document_aliases_preserve_multiplicity(self):
        self.app.documents.values.append(self.app.original_doc)
        self.saved_document()
        self.assertIsNone(self.gate()['pending'])
        reports = [hook.read_json(p) for p in (self.state / 'reports').glob('*.json')]
        before = next(r['reports']['before']['snapshot'] for r in reports if r['operation']['document_request']['action'] == 'create_folder')
        self.assertEqual(before['documents'][0]['aliases'], 2)

    def test_different_open_versions_of_one_file_are_distinguished(self):
        current = self.app.original_doc.dataFile
        old = copy.copy(current)
        current.versionNumber = current.latestVersionNumber = 2
        current.versionId = current.id + ':2'
        historical = Document(self.app, old)
        historical.creationId = self.app.original_doc.creationId
        self.app.documents.values.append(historical)
        self.saved_document()
        self.assertIsNone(self.gate()['pending'])
        reports = [hook.read_json(p) for p in (self.state / 'reports').glob('*.json')]
        before = next(r['reports']['before']['snapshot'] for r in reports if r['operation']['document_request']['action'] == 'create_folder')
        self.assertEqual(len(before['documents']), 2)
        self.assertEqual({d['version'] for d in before['documents']}, {1, 2})

    def test_first_save_and_later_save_have_distinct_checks(self):
        folder, source = self.saved_document()
        creation = self.app.activeDocument.creationId
        duplicate = self.invoke({'action': 'save_new_document', 'target_folder_id': folder, 'creation_id': creation, 'name': 'FG_Pilot_Plate'})
        self.assertEqual(duplicate['hookSpecificOutput']['permissionDecision'], 'deny')
        self.app.activeDocument.isModified = True
        self.assertNotIn('decision', self.invoke({'action': 'save_working_document', 'file_id': source.id}))
        self.assertEqual(self.gate()['document_registry']['files'][source.id]['version'], 2)

    def test_old_complete_revision_does_not_confirm_new_save(self):
        folder, source = self.saved_document()
        self.app.activeDocument.isModified = True
        self.app.delayed_revision = True
        calls = len(self.app.calls)
        self.assertNotIn('decision', self.invoke({'action': 'save_working_document', 'file_id': source.id}))
        self.assertEqual(self.gate()['pending']['status'], 'awaiting_cloud')
        self.assertTrue(source.isComplete)
        self.assertNotIn('decision', self.invoke(inspect=True))
        self.assertEqual(self.gate()['pending']['status'], 'awaiting_cloud')
        self.assertEqual(len(self.app.calls), calls + 1)
        source.versionNumber = source.latestVersionNumber = 2
        source.versionId = source.id + ':2'
        self.assertNotIn('decision', self.invoke(inspect=True))
        self.assertIsNone(self.gate()['pending'])
        self.assertEqual(self.gate()['document_registry']['files'][source.id]['version'], 2)

    def test_working_save_reconciliation_preserves_original_failure(self):
        folder, source = self.saved_document()
        self.app.activeDocument.isModified = True
        def fail_after_save(doc):
            raise RuntimeError('Saved revision; inspection failed')
        self.app.save_callback = fail_after_save
        self.assertEqual(self.invoke({'action': 'save_working_document', 'file_id': source.id})['decision'], 'block')
        pending = self.gate()['pending']
        path = next(p for p in (self.state / 'reports').glob('*.json') if hook.read_json(p)['operation']['call_id'] == pending['call_id'])
        original, calls = path.read_bytes(), list(self.app.calls)
        request = {'action': 'reconcile_working_save', 'operation_nonce': pending['nonce'],
                   'expected_file_id': source.id, 'user_confirmed': True,
                   'reason': 'The user reviewed the saved working revision and approved read-only reconciliation.'}
        self.assertNotIn('decision', self.invoke(request, reconcile=True))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.app.calls, calls)
        self.assertIsNone(self.gate()['pending'])
        self.assertEqual(self.gate()['document_registry']['files'][source.id]['version'], 2)

    def test_disabled_policy_never_invokes_fusion(self):
        self.policy['enabled'] = False
        result = self.invoke({'action': 'create_folder', 'parent_folder_id': self.app.root.id, 'name': 'FG_Pilot_Review'})
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(self.app.calls, [])

    def test_unauthorized_destinations_and_original_save_are_denied(self):
        requests = [
            {'action': 'create_folder', 'parent_folder_id': 'outside', 'name': 'FG_Pilot_Review'},
            {'action': 'new_document', 'target_folder_id': self.app.root.id, 'name': 'FG_Pilot_Plate'},
            {'action': 'save_working_document', 'file_id': self.app.original_doc.dataFile.id},
        ]
        for request in requests:
            result = self.invoke(request)
            self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(self.app.calls, [])

    def test_injected_code_and_duplicate_request_keys_are_rejected(self):
        source = ops.request_source({'action': 'create_folder', 'parent_folder_id': 'root', 'name': 'FG_Pilot_Review'})
        candidates = [source + 'print(1)\n', source.replace('raise RuntimeError', 'print(1)\n    raise RuntimeError'),
                      source.replace('"action":', '"action":"copy_file","action":'),
                      source.replace('"create_folder"', '"delete_file"')]
        for value in candidates:
            with self.assertRaises((ValueError, SyntaxError)):
                hook.lint(value, False, legacy.POLICY)

    def test_readonly_label_cannot_hide_document_mutation(self):
        with self.assertRaises(ValueError):
            hook.lint(ops.request_source({'action': 'create_folder', 'parent_folder_id': 'root', 'name': 'FG_Pilot_Review'}), True, legacy.POLICY)
        with self.assertRaises(ValueError):
            hook.lint(ops.request_source(inspect=True), False, legacy.POLICY)

    def test_raw_document_mutators_are_rejected_in_model_scripts(self):
        for operation in ('app.documents.add(1)', 'file.copy(folder)', 'folders = app.data.dataProjects.item(0).rootFolder.dataFolders\n    folders.add("x")'):
            source = '# fusion-guard: edit\nimport adsk.core\ndef run(_context: str):\n    app = adsk.core.Application.get()\n    ' + operation + '\n'
            with self.assertRaises(ValueError):
                hook.lint(source, False, legacy.POLICY)

    def test_unsaved_unrelated_work_stops_before_mutation(self):
        self.app.original_doc.isModified = True
        result = self.invoke({'action': 'create_folder', 'parent_folder_id': self.app.root.id, 'name': 'FG_Pilot_Review'})
        self.assertEqual(result['decision'], 'block')
        self.assertEqual(self.app.calls, [])
        self.assertEqual(self.gate()['pending']['status'], 'failed')
        reports = list((self.state / 'reports').glob('*.json'))
        report = hook.read_json(reports[0])
        self.assertIn('unsaved work', report['tool_response']['message'])

    def test_duplicate_name_is_not_an_idempotent_overwrite(self):
        self.folder()
        count = len(self.app.calls)
        result = self.invoke({'action': 'create_folder', 'parent_folder_id': self.app.root.id, 'name': 'FG_Pilot_Review'})
        self.assertEqual(result['decision'], 'block')
        self.assertEqual(len(self.app.calls), count)

    def test_async_copy_blocks_writes_until_readonly_confirmation(self):
        folder, source = self.saved_document()
        self.invoke({'action': 'create_folder', 'parent_folder_id': self.app.root.id, 'name': 'FG_Pilot_Copies'})
        destination = next(k for k in self.gate()['document_registry']['folders'] if k != folder)
        self.app.async_next = True
        self.assertNotIn('decision', self.invoke(self.copy_request(destination, source)))
        pending = self.gate()['pending']
        self.assertEqual(pending['status'], 'awaiting_cloud')
        self.assertEqual(self.invoke(self.copy_request(destination, source))['hookSpecificOutput']['permissionDecision'], 'deny')
        file = self.app.files[pending['after']['result']['file']['id']]
        self.assertNotIn(file.id, self.gate()['document_registry']['files'])
        self.assertNotIn('decision', self.invoke(inspect=True))
        self.assertIsNotNone(self.gate()['pending'])
        file.isComplete = True
        self.assertNotIn('decision', self.invoke(inspect=True))
        self.assertIsNone(self.gate()['pending'])
        self.assertIn(file.id, self.gate()['document_registry']['files'])

    def test_cloud_listing_can_lag_a_valid_copy_receipt(self):
        folder, source = self.saved_document()
        self.invoke({'action': 'create_folder', 'parent_folder_id': self.app.root.id, 'name': 'FG_Pilot_Copies'})
        destination = next(k for k in self.gate()['document_registry']['folders'] if k != folder)
        target = self.app.folders[destination]
        self.app.copy_callback = lambda: target.dataFiles.values.clear()
        self.app.async_next = True
        self.assertNotIn('decision', self.invoke(self.copy_request(destination, source)))
        pending = self.gate()['pending']
        self.assertEqual(pending['status'], 'awaiting_cloud')
        file = self.app.files[pending['after']['result']['file']['id']]
        target.dataFiles.values.append(file)
        file.isComplete = True
        self.assertNotIn('decision', self.invoke(inspect=True))
        self.assertIsNone(self.gate()['pending'])

    def test_initial_save_waits_before_reading_cloud_relationships(self):
        folder = self.folder()
        self.invoke({'action': 'new_document', 'target_folder_id': folder, 'name': 'FG_Pilot_Plate'})
        creation = self.app.activeDocument.creationId
        self.app.async_next = True
        result = self.invoke({'action': 'save_new_document', 'target_folder_id': folder, 'creation_id': creation, 'name': 'FG_Pilot_Plate'})
        self.assertNotIn('decision', result)
        self.assertEqual(self.gate()['pending']['status'], 'awaiting_cloud')
        self.app.activeDocument.dataFile.isComplete = True
        self.assertNotIn('decision', self.invoke(inspect=True))
        self.assertIsNone(self.gate()['pending'])

    def test_initial_save_requires_empty_document_before_native_write(self):
        folder = self.folder()
        self.invoke({'action': 'new_document', 'target_folder_id': folder, 'name': 'FG_Pilot_Plate'})
        doc = self.app.activeDocument
        doc.payload.append({'name': 'Premature modeling'})
        calls = list(self.app.calls)
        result = self.invoke({'action': 'save_new_document', 'target_folder_id': folder, 'creation_id': doc.creationId, 'name': 'FG_Pilot_Plate'})
        self.assertEqual(result['decision'], 'block')
        self.assertEqual(self.app.calls, calls)
        self.assertFalse(doc.isSaved)

    def test_initial_save_root_name_normalization_is_narrow(self):
        self.saved_document()
        report = next(hook.read_json(p) for p in (self.state / 'reports').glob('*.json')
                      if hook.read_json(p)['operation']['document_request']['action'] == 'save_new_document')
        after = copy.deepcopy(report['reports']['after']['snapshot'])
        after['active_model']['components'][0].update(name='Unexpected', key='0:Unexpected')
        errors, waiting = ops.assess(report['reports']['before']['snapshot'], after, report['operation']['document_request'])
        self.assertTrue(any('unexpected root' in e for e in errors))

    def test_initial_save_local_cache_id_transitions_to_cloud_id(self):
        folder = self.folder()
        self.invoke({'action': 'new_document', 'target_folder_id': folder, 'name': 'FG_Pilot_Plate'})
        creation = self.app.activeDocument.creationId
        def expose_cache_id(doc):
            file = doc.dataFile
            del self.app.files[file.id]
            file.id = 'C:/test/cache/plate.f3d'
            file.isComplete = False
        self.app.save_callback = expose_cache_id
        self.assertNotIn('decision', self.invoke({'action': 'save_new_document', 'target_folder_id': folder, 'creation_id': creation, 'name': 'FG_Pilot_Plate'}))
        self.assertEqual(self.gate()['pending']['status'], 'awaiting_cloud')
        self.assertNotEqual(creation, self.app.activeDocument.creationId)
        file = self.app.activeDocument.dataFile
        file.id = 'urn:test:completed-initial-save'
        file.versionId = file.id + ':1'
        file.isComplete = True
        self.app.files[file.id] = file
        self.assertNotIn('decision', self.invoke(inspect=True))
        self.assertIsNone(self.gate()['pending'])
        self.assertIn(file.id, self.gate()['document_registry']['files'])

    def test_missing_receipt_fails_instead_of_waiting_forever(self):
        self.saved_document()
        report = next(hook.read_json(p) for p in (self.state / 'reports').glob('*.json')
                      if hook.read_json(p)['operation']['document_request']['action'] == 'save_new_document')
        after = copy.deepcopy(report['reports']['after']['snapshot'])
        del after['result']['file']
        errors, waiting = ops.assess(report['reports']['before']['snapshot'], after, report['operation']['document_request'])
        self.assertIn('The cloud operation receipt is missing.', errors)

    def test_incoherent_snapshot_cannot_be_accepted(self):
        self.saved_document()
        report = next(hook.read_json(p) for p in (self.state / 'reports').glob('*.json')
                      if hook.read_json(p)['operation']['document_request']['action'] == 'save_new_document')
        after = copy.deepcopy(report['reports']['after']['snapshot'])
        after['result']['metadata_coherent'] = False
        errors, waiting = ops.assess(report['reports']['before']['snapshot'], after, report['operation']['document_request'])
        self.assertEqual(errors, [])
        self.assertTrue(waiting)

    def test_confirmed_reconciliation_is_readonly_and_preserves_failed_report(self):
        request = self.failed_initial_save()
        pending = self.gate()['pending']
        path = next(p for p in (self.state / 'reports').glob('*.json')
                    if hook.read_json(p)['operation']['call_id'] == pending['call_id'])
        original_bytes, calls = path.read_bytes(), list(self.app.calls)
        self.assertNotIn('decision', self.invoke(request, reconcile=True))
        self.assertIsNone(self.gate()['pending'])
        self.assertEqual(path.read_bytes(), original_bytes)
        self.assertEqual(self.app.calls, calls)
        self.assertIn(request['expected_file_id'], self.gate()['document_registry']['files'])
        self.assertTrue(any(hook.read_json(p)['status'] == 'document_reconciled_expected_result' for p in (self.state / 'reports').glob('*.json')))

    def test_reconciliation_rejects_wrong_identity_and_keeps_original_gate(self):
        request = self.failed_initial_save()
        original = copy.deepcopy(self.gate()['pending'])
        request['expected_file_id'] = self.app.original_doc.dataFile.id
        self.assertEqual(self.invoke(request, reconcile=True)['decision'], 'block')
        self.assertEqual(self.gate()['pending'], original)

    def test_reconciliation_rejects_geometry_changes(self):
        request = self.failed_initial_save()
        self.app.activeDocument.payload.append({'name': 'Unexpected geometry'})
        self.assertEqual(self.invoke(request, reconcile=True)['decision'], 'block')
        self.assertEqual(self.gate()['pending']['status'], 'failed')

    def test_reconciliation_rejects_changed_original(self):
        request = self.failed_initial_save()
        self.app.original_doc.isModified = True
        self.assertEqual(self.invoke(request, reconcile=True)['decision'], 'block')
        self.assertEqual(self.gate()['pending']['status'], 'failed')

    def test_reconciliation_requires_confirmation_nonce_and_readonly_label(self):
        request = self.failed_initial_save()
        with self.assertRaises(ValueError):
            self.invoke(dict(request, user_confirmed=False), reconcile=True)
        rejected = self.invoke(dict(request, operation_nonce='0' * 32), reconcile=True)
        self.assertEqual(rejected['hookSpecificOutput']['permissionDecision'], 'deny')
        with self.assertRaises(ValueError):
            hook.lint(ops.request_source(request, reconcile=True), False, legacy.POLICY)
        self.assertEqual(self.gate()['pending']['status'], 'failed')

    def test_reconciliation_does_not_accept_processing_file(self):
        request = self.failed_initial_save()
        self.app.activeDocument.dataFile.isComplete = False
        self.assertNotIn('decision', self.invoke(request, reconcile=True))
        self.assertEqual(self.gate()['pending']['status'], 'failed')
        self.app.activeDocument.dataFile.isComplete = True
        self.assertNotIn('decision', self.invoke(request, reconcile=True))
        self.assertIsNone(self.gate()['pending'])

    def test_changed_original_after_copy_keeps_failure_gate(self):
        folder, source = self.saved_document()
        self.invoke({'action': 'create_folder', 'parent_folder_id': self.app.root.id, 'name': 'FG_Pilot_Copies'})
        destination = next(k for k in self.gate()['document_registry']['folders'] if k != folder)
        self.app.copy_callback = lambda: setattr(self.app.original_doc, 'isModified', True)
        result = self.invoke(self.copy_request(destination, source))
        self.assertEqual(result['decision'], 'block')
        self.app.original_doc.isModified = False
        self.assertEqual(self.invoke(inspect=True)['decision'], 'block')
        self.assertEqual(self.gate()['pending']['status'], 'failed')

    def test_missing_report_keeps_gate_and_does_not_register_copy(self):
        event = self.event(ops.request_source({'action': 'create_folder', 'parent_folder_id': self.app.root.id, 'name': 'FG_Pilot_Review'}))
        hook.process(event, legacy.POLICY, self.state)
        result = hook.process(dict(event, hook_event_name='PostToolUse', tool_response={'success': True}), legacy.POLICY, self.state)
        self.assertEqual(result['decision'], 'block')
        self.assertNotIn('document_registry', self.gate())

    def test_model_snapshot_does_not_unlock_document_failure(self):
        self.app.original_doc.isModified = True
        self.invoke({'action': 'create_folder', 'parent_folder_id': self.app.root.id, 'name': 'FG_Pilot_Review'})
        event = self.event(legacy.PROBE, True)
        hook.process(event, legacy.POLICY, self.state)
        operation = self.gate()['probes'][event['tool_use_id']]
        legacy.write_transport(operation, 'inspect', legacy.snapshot())
        result = hook.process(dict(event, hook_event_name='PostToolUse', tool_response={'success': True}), legacy.POLICY, self.state)
        self.assertEqual(result['decision'], 'block')
        self.assertEqual(self.gate()['pending']['kind'], 'document')

    def test_reference_copy_is_recorded_but_not_editable(self):
        folder, source = self.saved_document()
        source.childReferences = Items([self.app.original_doc.dataFile])
        source.hasChildReferences = True
        self.invoke({'action': 'create_folder', 'parent_folder_id': self.app.root.id, 'name': 'FG_Pilot_Copies'})
        destination = next(k for k in self.gate()['document_registry']['folders'] if k != folder)
        self.assertNotIn('decision', self.invoke(self.copy_request(destination, source)))
        copied = next(v for k, v in self.gate()['document_registry']['files'].items() if k != source.id)
        self.assertFalse(copied['editable'])
        auth = ops.model_authorization(self.gate()['document_registry'], 'test-session')
        self.assertNotIn(copied['id'], auth['file_ids'])

    def test_source_version_drift_stops_before_copy(self):
        folder, source = self.saved_document()
        request = self.copy_request(folder, source)
        request['source_version'] = 2
        count = len(self.app.calls)
        result = self.invoke(request)
        self.assertEqual(result['decision'], 'block')
        self.assertEqual(len(self.app.calls), count)

    def test_generic_save_is_rejected_when_document_scope_enabled(self):
        event = self.event('unused')
        event['tool_input'] = {'featureType': 'document', 'object': {'operation': 'save'}}
        result = hook.process(event, legacy.POLICY, self.state)
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_model_wrapper_only_authorizes_registered_targets(self):
        event = self.event(legacy.PARAMETERS)
        rewritten = hook.process(event, legacy.POLICY, self.state)['hookSpecificOutput']['updatedInput']['object']['script']
        namespace = {}
        with patch.dict(sys.modules, self.modules):
            exec(compile(rewritten, '<guarded-model-test>', 'exec'), namespace)
            with self.assertRaisesRegex(RuntimeError, 'registered independent'):
                namespace['_fgd_require_model_target']({'file_ids': [], 'creation_ids': []})


if __name__ == '__main__':
    unittest.main(verbosity=2)
