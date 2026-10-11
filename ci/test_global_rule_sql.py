"""Keep synthetic SQL failure diagnostics actionable without leaking source values."""
import sys
import re
import unittest
from unittest.mock import Mock

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

    def test_existing_organization_rule_is_borrowed_without_writes(self):
        sql = Mock(return_value='existing-core-id')
        fixture = self.probe.OrganizationRuleFixture(sql, 'ruleprobe_unique')
        self.assertEqual(fixture.ensure(), 'existing-core-id')
        fixture.cleanup()
        self.assertTrue(fixture.preexisting)
        self.assertIsNone(fixture.created_id)
        sql.assert_called_once_with("SELECT id FROM sys_fill_rule WHERE rule_code='org_num_role'")

    def test_missing_rule_is_created_and_removed_by_its_exact_owned_id(self):
        sql = Mock(side_effect=['', '', ''])
        fixture = self.probe.OrganizationRuleFixture(sql, 'ruleprobe_unique')
        owned_id = fixture.ensure()
        fixture.cleanup()
        self.assertFalse(fixture.preexisting)
        self.assertEqual(owned_id, fixture.created_id)
        inserted = sql.call_args_list[1][0][0]
        self.assertIn(self.probe.q('org.jeecg.modules.system.rule.OrgCodeRule'), inserted)
        self.assertIn("'org_num_role'", inserted)
        self.assertEqual(sql.call_args_list[-1][0][0], 'DELETE FROM sys_fill_rule WHERE id='
                         + self.probe.q(owned_id) + " AND rule_code='org_num_role'")

    def test_insert_failure_still_registers_exact_cleanup_without_broad_delete(self):
        sql = Mock(side_effect=['', RuntimeError('uncertain insertion'), ''])
        fixture = self.probe.OrganizationRuleFixture(sql, 'ruleprobe_unique')
        with self.assertRaisesRegex(RuntimeError, 'uncertain insertion'):
            fixture.ensure()
        fixture.cleanup()
        self.assertIsNotNone(fixture.created_id)
        self.assertEqual(sql.call_args_list[-1][0][0], 'DELETE FROM sys_fill_rule WHERE id='
                         + self.probe.q(fixture.created_id) + " AND rule_code='org_num_role'")

    def test_class_probe_uses_the_existing_controller_and_frontend_route(self):
        controller = (registration.ROOT / 'api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/system/controller/SysDepartController.java').read_text()
        modal = (registration.ROOT / 'web/src/views/system/modules/DepartModal.vue').read_text()
        prefix = re.search(r'@RequestMapping\("([^"]+)"\)', controller)[1]
        frontend = re.search(r'add:\s*"([^"]+)"', modal)[1]
        self.assertEqual(self.probe.DEPARTMENT_ADD, prefix + '/add')
        self.assertEqual(self.probe.DEPARTMENT_ADD, frontend)


if __name__ == '__main__':
    unittest.main()
