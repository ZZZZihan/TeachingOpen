"""Leaf binding and failure checks using synthetic PEM and TLS fixtures."""
import contextlib
import hashlib
import io
from pathlib import Path
import ssl
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

import check_ip_certificate as checker


class CertificateBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.leaf = Path(self.temp.name) / 'cert.pem'
        self.der = b'synthetic-leaf'
        self.leaf.write_text(ssl.DER_cert_to_PEM_cert(self.der))
        self.secured = MagicMock()
        self.secured.__enter__.return_value = self.secured
        self.secured.getpeercert.side_effect = lambda binary_form=False: (
            self.der if binary_form else {'notAfter': 'Oct 20 00:00:00 2026 GMT'})
        self.secured.version.return_value = 'TLSv1.3'
        self.context = MagicMock()
        self.context.wrap_socket.return_value = self.secured
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.object(checker.ssl, 'create_default_context', return_value=self.context))
        self.connection = self.stack.enter_context(patch.object(checker.socket, 'create_connection'))
        self.stack.enter_context(patch.object(checker.time, 'time', return_value=1791590400))
        self.stack.enter_context(patch.object(checker, 'CERTIFICATE_LOCK', str(Path(self.temp.name) / 'lock')))

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    def check(self, **kwargs):
        return checker.check_certificate('8.8.8.8', connect_host='127.0.0.1',
                                         expected_certificate=self.leaf, **kwargs)

    def test_matching_disk_and_served_leaf_passes_with_verified_identity(self):
        result = self.check()
        expected = hashlib.sha256(self.der).hexdigest()
        self.assertEqual(result['certificate_sha256'], expected)
        self.assertEqual(result['expected_certificate_sha256'], expected)
        self.assertTrue(result['expected_certificate_checked'])
        self.assertFalse(result['public_reachability_checked'])
        self.context.wrap_socket.assert_called_once()
        self.assertEqual(self.context.wrap_socket.call_args.kwargs['server_hostname'], '8.8.8.8')

    def test_old_certificate_with_more_than_48_hours_cannot_hide_mismatch(self):
        self.secured.getpeercert.side_effect = lambda binary_form=False: (
            b'old-leaf' if binary_form else {'notAfter': 'Oct 20 00:00:00 2026 GMT'})
        with self.assertRaises(checker.CertificateMismatch):
            self.check()

    def test_same_leaf_still_requires_48_hours_remaining(self):
        with self.assertRaisesRegex(ValueError, 'expires in'):
            self.check(minimum_hours=1000)

    def test_expected_leaf_does_not_bypass_ca_or_ip_validation(self):
        self.context.wrap_socket.side_effect = ssl.SSLCertVerificationError('untrusted')
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.check()

    def test_public_check_can_remain_independent_of_server_disk(self):
        result = checker.check_certificate('8.8.8.8')
        self.assertFalse(result['expected_certificate_checked'])
        self.assertTrue(result['public_reachability_checked'])

    def test_missing_or_chain_file_fails_before_network_access(self):
        self.leaf.unlink()
        with self.assertRaises(FileNotFoundError):
            self.check()
        self.leaf.write_text(ssl.DER_cert_to_PEM_cert(self.der) * 2)
        with self.assertRaisesRegex(ValueError, 'one PEM leaf'):
            self.check()
        self.connection.assert_not_called()

    def test_cli_binding_failure_returns_nonzero_json(self):
        self.leaf.write_text(ssl.DER_cert_to_PEM_cert(b'new-leaf'))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = checker.main(['--ip', '8.8.8.8', '--connect-host', '127.0.0.1',
                                 '--expected-certificate', str(self.leaf)])
        self.assertEqual(code, 1)
        self.assertIn('"status": "failed"', output.getvalue())


class CertificateLockTests(unittest.TestCase):
    def test_readers_can_overlap_but_writer_and_reader_cannot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'certificate.lock')
            with checker.certificate_lock(True, 0, path):
                with checker.certificate_lock(True, 0, path):
                    pass
                with self.assertRaises(checker.CertificateBusy):
                    with checker.certificate_lock(False, 0, path):
                        self.fail('writer entered during read')
            with checker.certificate_lock(False, 0, path):
                for shared in (True, False):
                    with self.assertRaises(checker.CertificateBusy):
                        with checker.certificate_lock(shared, 0.01, path):
                            self.fail('entered during renewal')
            with checker.certificate_lock(True, 0, path):
                pass

    def test_process_reader_waits_for_writer_then_reads_updated_leaf(self):
        with tempfile.TemporaryDirectory() as directory:
            path, value = Path(directory) / 'lock', Path(directory) / 'leaf'
            value.write_text('old')
            script = '''import sys
from pathlib import Path
from check_ip_certificate import certificate_lock
print('ready', flush=True)
with certificate_lock(True, 2, sys.argv[1]):
    print(Path(sys.argv[2]).read_text(), flush=True)
'''
            with checker.certificate_lock(False, 0, str(path)):
                process = subprocess.Popen([sys.executable, '-c', script, str(path), str(value)],
                    cwd=Path(checker.__file__).parent, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    self.assertEqual(process.stdout.readline().strip(), 'ready')
                    self.assertIsNone(process.poll())
                    value.write_text('new')
                except BaseException:
                    process.kill(); process.communicate(); raise
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(stdout.strip(), 'new')

    def test_symlink_lock_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target'
            target.write_text('preserve')
            path = Path(directory) / 'lock'
            path.symlink_to(target)
            with self.assertRaises(OSError):
                with checker.certificate_lock(True, 0, str(path)):
                    self.fail('symlink accepted')
            self.assertEqual(target.read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()
