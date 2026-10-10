"""Leaf binding and failure checks using synthetic PEM and TLS fixtures."""
import contextlib
import hashlib
import io
from pathlib import Path
import ssl
import tempfile
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


if __name__ == '__main__':
    unittest.main()
