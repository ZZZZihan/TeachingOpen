"""Filesystem-only report-target regressions; no Docker or HTTP operations."""
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location('probe_candidate_runtime', Path(__file__).with_name('probe_candidate_runtime.py'))
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class ReportTargetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='candidate-probe-output-test-')
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        # Any accidental runtime operation is an immediate test failure.
        self.addCleanup(patch.stopall)
        patch.object(PROBE, 'run', side_effect=AssertionError('No Docker operations in filesystem tests')).start()
        patch.object(PROBE.socket, 'create_connection', side_effect=AssertionError('No sockets in filesystem tests')).start()

    def mode(self, path):
        return stat.S_IMODE(path.lstat().st_mode)

    def directory(self, name, mode):
        path = self.root / name
        path.mkdir()
        os.chmod(path, mode)
        return path

    def test_existing_public_parent_rejected_without_permission_change(self):
        parent = self.directory('public', 0o755)
        output = parent / 'report.json'
        with self.assertRaises(ValueError):
            PROBE.prepare_output(output)
        self.assertEqual(self.mode(parent), 0o755)
        self.assertFalse(output.exists())

    def test_existing_private_parent_accepted_without_permission_change(self):
        parent = self.directory('private', 0o700)
        output = parent / 'report.json'
        self.assertEqual(PROBE.prepare_output(output), output.absolute())
        self.assertEqual(self.mode(parent), 0o700)
        self.assertFalse(output.exists())

    def test_existing_private_mode_preserved_exactly(self):
        parent = self.directory('write-and-traverse', 0o300)
        try:
            self.assertEqual(PROBE.prepare_output(parent / 'report.json'), parent / 'report.json')
            self.assertEqual(self.mode(parent), 0o300)
        finally:
            # Restore only this test-owned directory for TemporaryDirectory cleanup.
            os.chmod(parent, 0o700)

    def test_missing_parent_created_private(self):
        parent = self.root / 'new-private'
        output = parent / 'report.json'
        self.assertEqual(PROBE.prepare_output(output), output.absolute())
        self.assertTrue(parent.is_dir())
        self.assertEqual(self.mode(parent), 0o700)
        self.assertFalse(output.exists())

    def test_symlink_parent_rejected_without_target_permission_change(self):
        target = self.directory('target', 0o700)
        link = self.root / 'link'
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            PROBE.prepare_output(link / 'report.json')
        self.assertTrue(link.is_symlink())
        self.assertEqual(self.mode(target), 0o700)
        self.assertFalse((target / 'report.json').exists())

    def test_dangling_output_symlink_refused(self):
        parent = self.directory('private-link-output', 0o700)
        output = parent / 'report.json'
        output.symlink_to(parent / 'missing.json')
        with self.assertRaises(ValueError):
            PROBE.prepare_output(output)
        self.assertTrue(output.is_symlink())
        self.assertEqual(self.mode(parent), 0o700)

    def test_existing_output_refused_without_modification(self):
        parent = self.directory('private-existing-output', 0o700)
        output = parent / 'report.json'
        output.write_bytes(b'previous report evidence')
        os.chmod(output, 0o640)
        with self.assertRaises(ValueError):
            PROBE.prepare_output(output)
        self.assertEqual(output.read_bytes(), b'previous report evidence')
        self.assertEqual(self.mode(output), 0o640)
        self.assertEqual(self.mode(parent), 0o700)

    def test_main_rejects_public_parent_before_probe_or_traffic(self):
        parent = self.directory('public-main', 0o755)
        with patch.object(PROBE, 'Probe', side_effect=AssertionError('Probe must not start')) as constructor:
            with patch('sys.argv', ['probe', '--bundle', str(self.root / 'unread-bundle'), '--output', str(parent / 'report.json')]):
                with self.assertRaises(SystemExit):
                    PROBE.main()
            constructor.assert_not_called()
        self.assertEqual(self.mode(parent), 0o755)


if __name__ == '__main__':
    unittest.main()
