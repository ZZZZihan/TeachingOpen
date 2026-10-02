"""Recovery boundary checks; the actual MySQL/HTTP drill is recorded separately."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import local_recovery as recovery


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


if __name__ == '__main__':
    unittest.main()
