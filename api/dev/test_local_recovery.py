"""Recovery boundary checks; the actual MySQL/HTTP drill is recorded separately."""
import hashlib
import base64
from contextlib import ExitStack, nullcontext
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import ANY, MagicMock, patch

import local_recovery as recovery
import scratch_cloud_recovery as cloud


class LocalRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # macOS /var is a symlink; use the canonical temporary parent.
        self.root = Path(self.tmp.name).resolve() / '.devspace'
        self.root.mkdir()
        self.snapshot = self.root / 'snapshot'
        self.snapshot.mkdir(mode=0o700)
        (self.snapshot / 'uploads').mkdir()
        (self.snapshot / 'uploads/a.txt').write_bytes(b'fixture')
        recovery.private_write(self.snapshot / 'database.sql', 'SELECT 1;\n')
        recovery.private_write(self.snapshot / 'fixture-login.json', json.dumps({'test_user_password': 'a' * 40}))
        digest = hashlib.sha256(b'').hexdigest()
        self.manifest = {
            'format': 1, 'kind': 'teachingopen-local-synthetic', 'complete': True,
            'database': {'test': {'rows': 0, 'rows_sha256': digest, 'schema_sha256': digest}},
            'uploads': recovery.file_inventory(self.snapshot / 'uploads'),
            'payload': recovery.file_inventory(self.snapshot),
            'source_ports': {'mysql': 13306, 'redis': 16379, 'backend': 18091, 'frontend': 18092},
        }
        self.write_manifest()

    def write_manifest(self):
        (self.snapshot / 'manifest.json').write_text(json.dumps(self.manifest))

    def test_valid_snapshot_and_private_payload(self):
        self.assertEqual(recovery.inspect_snapshot(self.snapshot), self.manifest)
        self.assertEqual((self.snapshot / 'fixture-login.json').stat().st_mode & 0o777, 0o600)

    def test_existing_target_preserved(self):
        target = self.root / 'target'
        target.mkdir(mode=0o700)
        sentinel = target / 'keep.txt'
        sentinel.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            recovery.restore_snapshot(self.snapshot, target, self.root / 'tools', {})
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_nested_and_linked_paths_rejected(self):
        with self.assertRaises(ValueError):
            recovery.local_path(self.snapshot / 'nested', new=True)
        link = self.root / 'linked'
        link.symlink_to(self.snapshot)
        with self.assertRaises(ValueError):
            recovery.local_path(link)

    def test_shared_directory_rejected(self):
        self.snapshot.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'private'):
            recovery.inspect_snapshot(self.snapshot)

    def test_corrupt_payload_rejected_before_target_creation(self):
        (self.snapshot / 'database.sql').write_text('corrupt')
        target = self.root / 'target'
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            recovery.restore_snapshot(self.snapshot, target, self.root / 'tools', {})
        self.assertFalse(target.exists())

    def test_missing_manifest_is_incomplete(self):
        (self.snapshot / 'manifest.json').unlink()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            recovery.inspect_snapshot(self.snapshot)

    def test_extra_payload_rejected(self):
        (self.snapshot / 'unexpected').write_text('extra')
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            recovery.inspect_snapshot(self.snapshot)

    def test_symlink_and_fifo_rejected(self):
        link = self.snapshot / 'uploads/link'
        link.symlink_to(self.snapshot / 'database.sql')
        with self.assertRaisesRegex(ValueError, 'Links and special'):
            recovery.inspect_snapshot(self.snapshot)
        link.unlink()
        os.mkfifo(link)
        with self.assertRaisesRegex(ValueError, 'Links and special'):
            recovery.inspect_snapshot(self.snapshot)

    def test_source_ports_cannot_be_reused(self):
        target = self.root / 'target'
        with self.assertRaisesRegex(ValueError, 'distinct from the source'):
            recovery.restore_snapshot(self.snapshot, target, self.root / 'tools', self.manifest['source_ports'])
        self.assertFalse(target.exists())

    def test_invalid_database_manifest_refused(self):
        self.manifest['database']['test']['rows'] = -1
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'Invalid database'):
            recovery.inspect_snapshot(self.snapshot)

    def test_busy_source_does_not_create_snapshot(self):
        target = self.root / 'new-snapshot'
        with patch.object(recovery, 'assert_stopped', side_effect=RuntimeError('still running')):
            with self.assertRaisesRegex(RuntimeError, 'still running'):
                recovery.create_snapshot(self.snapshot, target)
        self.assertFalse(target.exists())

    def test_empty_value_row_remains_distinct_from_zero_rows(self):
        def fake_sql(runtime, query):
            if query.startswith('SELECT (SELECT'): return '0'
            if query.startswith('SELECT TABLE_NAME'): return 'example'
            if query.startswith('SHOW COLUMNS'): return 'value\ttext'
            if query.startswith('SHOW CREATE'): return 'example\tCREATE TABLE'
            if query.startswith("SELECT 'ROW',"): return 'ROW\t'
            self.fail('Unexpected query')
        with patch.object(recovery, 'sql', side_effect=fake_sql):
            result = recovery.database_inventory(self.snapshot)['example']
        self.assertEqual(result['rows'], 1)
        self.assertNotEqual(result['rows_sha256'], hashlib.sha256(b'').hexdigest())

    def cloud_document(self):
        encode = lambda value: base64.b64encode(value).decode()
        return {'format': 1, 'database': 1, 'prefix': 'scratch:cloud:', 'ttl_policy': 'persistent-only',
                'entries': [{'key_b64': encode(b'scratch:cloud:fixture_cloud_recovery_public'), 'ttl_ms': -1,
                             'fields': [[encode(b''), encode(b'')], [encode(b'name\x00\xff'), encode(b'value\r\n\x00\xff')]]}]}

    def cloud_payload(self, raw=None):
        doc = self.cloud_document()
        path = self.snapshot / cloud.CLOUD_FILE
        if path.exists(): path.unlink()
        recovery.private_write(path, raw if raw is not None else cloud.encode_cloud(doc))
        self.manifest.update(format=2, redis=cloud.cloud_summary(doc))
        self.rebind_payload()
        return doc

    def rebind_payload(self):
        self.manifest['payload'] = recovery.file_inventory(self.snapshot)
        self.manifest['payload'].pop('manifest.json', None)
        self.write_manifest()

    def create_source(self):
        source = self.root / 'source'; source.mkdir(mode=0o700)
        (source / 'uploads').mkdir(); (source / 'uploads/a.txt').write_bytes(b'fixture')
        (source / 'config').mkdir()
        recovery.private_write(source / 'config/credentials.json', json.dumps({'test_user_password': 'a' * 40}))
        return source

    def mock_create(self, stack, doc):
        stack.enter_context(patch.object(recovery, 'assert_stopped'))
        stack.enter_context(patch.object(recovery, 'database_read_lock', return_value=nullcontext()))
        owner = stack.enter_context(patch.object(recovery, 'OwnedRedis'))
        stack.enter_context(patch.object(recovery, 'database_inventory', return_value=self.manifest['database']))
        stack.enter_context(patch.object(recovery, 'project_ids', return_value={b'fixture_cloud_recovery_public'}))
        capture = stack.enter_context(patch.object(recovery, 'capture_cloud', return_value=doc))
        stack.enter_context(patch.object(recovery, 'command', return_value=b'SELECT 1;\n'))
        stack.enter_context(patch.object(recovery, 'load_ports', return_value=self.manifest['source_ports']))
        return owner, capture

    def mock_restore(self, stack, doc):
        def prepare(runtime, tools, ports, seed_fixtures):
            self.assertFalse(seed_fixtures)
            runtime.mkdir(mode=0o700); (runtime / 'uploads').mkdir(); (runtime / 'config').mkdir()
            recovery.private_write(runtime / 'config/credentials.json', json.dumps({'mysql_app_password': 'synthetic-app', 'test_user_password': 'b' * 40}))
        module = SimpleNamespace(prepare=prepare)
        stack.enter_context(patch.object(recovery.importlib.util, 'spec_from_file_location', return_value=SimpleNamespace(loader=MagicMock())))
        stack.enter_context(patch.object(recovery.importlib.util, 'module_from_spec', return_value=module))
        for name in ('assert_app_config', 'assert_database', 'assert_mysql_owner'):
            stack.enter_context(patch.object(recovery, name))
        owner = stack.enter_context(patch.object(recovery, 'OwnedRedis'))
        owner.return_value.__enter__.return_value.execute.return_value = 0
        command = stack.enter_context(patch.object(recovery, 'command', return_value=b''))
        stack.enter_context(patch.object(recovery, 'database_inventory', return_value=self.manifest['database']))
        stack.enter_context(patch.object(recovery, 'project_ids', return_value={b'fixture_cloud_recovery_public'}))
        restore = stack.enter_context(patch.object(recovery, 'restore_cloud'))
        capture = stack.enter_context(patch.object(recovery, 'capture_cloud', return_value=doc))
        return owner, command, restore, capture

    def target_ports(self):
        return {'mysql': 13348, 'redis': 16421, 'backend': 18145, 'frontend': 18146}

    def test_format2_cloud_integrity_and_structure_rejected_before_prepare(self):
        doc = self.cloud_payload()
        self.assertEqual(recovery.inspect_snapshot(self.snapshot), self.manifest)
        valid_raw = cloud.encode_cloud(doc)
        variants = [b'{bad-json', valid_raw.replace(b'"ttl_ms": -1', b'"ttl_ms": 0'),
                    valid_raw.replace(b'"entries": [', b'"entries": [], "entries": ['),
                    valid_raw.replace(b'"key_b64":', b'"key_b64": "invalid", "key_b64":')]
        for number, raw in enumerate(variants):
            with self.subTest(number=number):
                self.cloud_payload(raw)
                target = self.root / ('malformed-target-' + str(number))
                with patch.object(recovery.importlib.util, 'spec_from_file_location') as prepare:
                    with self.assertRaises(ValueError): recovery.restore_snapshot(self.snapshot, target, self.root / 'tools', self.target_ports())
                prepare.assert_not_called(); self.assertFalse(target.exists())
        self.cloud_payload()
        for summary in ({**self.manifest['redis'], 'keys': 9}, {**self.manifest['redis'], 'keys': True}):
            self.manifest['redis'] = summary; self.write_manifest()
            with self.assertRaisesRegex(ValueError, 'Cloud summary'): recovery.inspect_snapshot(self.snapshot)
        self.cloud_payload(); self.manifest['format'] = 1; self.write_manifest()
        with self.assertRaisesRegex(ValueError, 'payload layout'): recovery.inspect_snapshot(self.snapshot)
        self.cloud_payload(); (self.snapshot / cloud.CLOUD_FILE).unlink(); self.rebind_payload()
        with self.assertRaisesRegex(ValueError, 'payload layout'): recovery.inspect_snapshot(self.snapshot)

    def test_create_format2_binds_real_encoded_bytes_and_captures_twice(self):
        source, doc, destination = self.create_source(), self.cloud_document(), self.root / 'new-snapshot'
        with ExitStack() as stack:
            _, capture = self.mock_create(stack, doc)
            result = recovery.create_snapshot(source, destination)
        self.assertEqual(capture.call_count, 2)
        manifest = recovery.inspect_snapshot(destination)
        self.assertEqual(manifest['format'], 2)
        self.assertEqual((destination / cloud.CLOUD_FILE).read_bytes(), cloud.encode_cloud(doc))
        self.assertEqual(manifest['payload'][cloud.CLOUD_FILE]['sha256'], recovery.sha256(destination / cloud.CLOUD_FILE))
        self.assertEqual((destination / cloud.CLOUD_FILE).stat().st_mode & 0o777, 0o600)
        self.assertEqual((result['cloud_keys'], result['cloud_fields'], result['redis_sessions_restored']), (1, 2, False))

    def test_source_change_retains_incomplete_diagnostics_without_manifest(self):
        source, doc, destination = self.create_source(), self.cloud_document(), self.root / 'changed-snapshot'
        changed = json.loads(json.dumps(doc)); changed['entries'][0]['fields'][1][1] = base64.b64encode(b'changed').decode()
        with ExitStack() as stack:
            _, capture = self.mock_create(stack, doc); capture.side_effect = [doc, changed]
            with self.assertRaisesRegex(RuntimeError, 'Source changed'): recovery.create_snapshot(source, destination)
        self.assertTrue((destination / cloud.CLOUD_FILE).is_file())
        self.assertFalse((destination / 'manifest.json').exists())
        self.assertEqual((source / 'uploads/a.txt').read_bytes(), b'fixture')

    def test_owner_capture_and_actual_encoded_size_fail_before_destination(self):
        source, doc = self.create_source(), self.cloud_document()
        actual_size = len(cloud.encode_cloud(doc))
        self.assertGreater(actual_size, sum(len(base64.b64decode(x)) for pair in doc['entries'][0]['fields'] for x in pair))
        for condition in ('owner', 'capture', 'encoded-size'):
            with self.subTest(condition=condition), ExitStack() as stack:
                owner, capture = self.mock_create(stack, doc)
                if condition == 'owner': owner.return_value.__enter__.side_effect = RuntimeError('wrong owned Redis')
                if condition == 'capture': capture.side_effect = ValueError('wrong type or TTL')
                if condition == 'encoded-size': stack.enter_context(patch.object(cloud, 'MAX_DOCUMENT_BYTES', actual_size - 1))
                target = self.root / ('rejected-' + condition)
                with self.assertRaises((RuntimeError, ValueError)): recovery.create_snapshot(source, target)
                self.assertFalse(target.exists())
        with patch.object(cloud, 'MAX_DOCUMENT_BYTES', actual_size):
            self.assertEqual(len(cloud.encode_cloud(doc)), actual_size)

    def test_old_and_new_restore_report_their_distinct_cloud_contracts(self):
        for version in (1, 2):
            with self.subTest(version=version):
                doc = self.cloud_payload() if version == 2 else None
                target = self.root / ('restored-' + str(version))
                with ExitStack() as stack:
                    _, command, restore, _ = self.mock_restore(stack, doc)
                    result = recovery.restore_snapshot(self.snapshot, target, self.root / 'tools', self.target_ports())
                self.assertTrue(result['database_equal']); self.assertTrue(result['attachments_equal'])
                self.assertEqual(result['cloud_data_present'], version == 2)
                self.assertEqual(result['cloud_equal'], True if version == 2 else None)
                self.assertEqual(result['legacy_cloud_missing'], version == 1)
                self.assertFalse(result['redis_sessions_restored']); self.assertFalse(result['business_read_verified'])
                self.assertTrue((target / 'restore-result.json').is_file())
                command.assert_called_once()
                self.assertIn('--defaults-extra-file=' + str(target / 'config/recovery-app-client.cnf'), command.call_args.args[1])
                self.assertTrue(command.call_args.kwargs['input'].endswith(b'SELECT 1;\n'))
                if version == 2: restore.assert_called_once_with(ANY, doc, {b'fixture_cloud_recovery_public'})
                else: restore.assert_not_called()

    def test_restore_failure_never_publishes_result_or_overwrites_source(self):
        doc = self.cloud_payload()
        for failure in ('nonempty-redis', 'sql-import', 'cloud-restore', 'cloud-readback'):
            with self.subTest(failure=failure), ExitStack() as stack:
                owner, command, restore, capture = self.mock_restore(stack, doc)
                if failure == 'nonempty-redis': owner.return_value.__enter__.return_value.execute.return_value = 1
                if failure == 'sql-import': command.side_effect = RuntimeError('synthetic SQL failure')
                if failure == 'cloud-restore': restore.side_effect = RuntimeError('synthetic Redis failure')
                if failure == 'cloud-readback': capture.return_value = {**doc, 'entries': []}
                target = self.root / ('failure-' + failure)
                with self.assertRaises(RuntimeError): recovery.restore_snapshot(self.snapshot, target, self.root / 'tools', self.target_ports())
                self.assertTrue(target.exists()); self.assertFalse((target / 'restore-result.json').exists())
                if failure == 'nonempty-redis': command.assert_not_called(); restore.assert_not_called()
                self.assertEqual(recovery.inspect_snapshot(self.snapshot), self.manifest)


if __name__ == '__main__':
    unittest.main()
