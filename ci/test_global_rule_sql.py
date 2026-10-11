"""Keep synthetic SQL failure diagnostics actionable without leaking source values."""
import sys
import unittest

import registration_mysql as registration


class GlobalRuleSqlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(registration.ROOT / 'api/dev'))
        try:
            cls.probe = registration.load('global_rule_sql_contract',
                registration.ROOT / 'api/dev/verify-global-rule-boundaries.py')
        finally:
            sys.path.pop(0)

    def test_mysql_error_code_survives_without_query_or_private_values(self):
        stderr = "ERROR 1267 (HY000) at line 1: private-fixture-value password=private-password\n"
        error = self.probe.sql_failure(stderr)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(str(error), 'Global-rule synthetic SQL failed: MySQL 1267 (HY000)')

    def test_connection_error_hides_user_host_and_password(self):
        error = self.probe.sql_failure("ERROR 1045 (28000): Access denied for user 'private-user'@'private-host' (using password: YES)")
        self.assertEqual(str(error), 'Global-rule synthetic SQL failed: MySQL 1045 (28000)')

    def test_unknown_client_output_does_not_become_evidence_content(self):
        for stderr in (None, '', 'private-client-option private-password', 'ERROR 1267 (not a state): private-value'):
            with self.subTest(stderr=bool(stderr)):
                self.assertEqual(str(self.probe.sql_failure(stderr)), 'Global-rule synthetic SQL failed')


if __name__ == '__main__':
    unittest.main()
