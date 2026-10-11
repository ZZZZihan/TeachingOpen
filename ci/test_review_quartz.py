"""Keep the CI Quartz fixture faithful on case-sensitive MySQL runners."""
import re
import unittest

import registration_mysql as registration
import review_mysql as review


class ReviewQuartzTest(unittest.TestCase):
    def setUp(self):
        self.source = (registration.ROOT / 'api/db/teachingopen2.8.sql').read_text()
        self.schema = registration.load('quartz_schema_contract',
            registration.ROOT / 'api/dev/extract-schema.py').extract_schema(self.source)

    def test_actual_schema_matches_jdbc_table_names_and_case_sensitive_foreign_keys(self):
        schema = review.jdbc_review_schema(self.schema)
        original_tables = re.findall(r'^CREATE TABLE `([^`]+)`', self.schema, re.MULTILINE)
        tables = re.findall(r'^CREATE TABLE `([^`]+)`', schema, re.MULTILINE)
        expected = {name.upper() for name in original_tables if name.startswith('qrtz_')}
        self.assertEqual(len(expected), 11)
        self.assertEqual({name for name in tables if name.startswith('QRTZ_')}, expected)
        self.assertEqual(len(tables), len(original_tables))
        # Exact string membership models Linux MySQL's case-sensitive lookup.
        for target in re.findall(r'REFERENCES `([^`]+)`', schema):
            self.assertIn(target, tables)
        for target in re.findall(r'\bQRTZ_[A-Z_]+\b',
                (registration.ROOT / 'api/dev/verify-infrastructure-authorization.py').read_text()):
            self.assertIn(target, tables)
        restored = re.sub(r'`(QRTZ_[A-Z_]+)`', lambda match: '`' + match[1].lower() + '`', schema)
        self.assertEqual(restored, self.schema)
        self.assertNotRegex(schema, r'(?im)^\s*(INSERT|REPLACE)\b')

    def test_missing_or_unknown_quartz_table_is_not_silently_accepted(self):
        for name in re.findall(r'^CREATE TABLE `(qrtz_[a-z_]+)`', self.schema, re.MULTILINE):
            with self.subTest(table=name), self.assertRaisesRegex(RuntimeError, 'Quartz table set'):
                review.jdbc_review_schema(self.schema.replace('CREATE TABLE `' + name + '`',
                                                               'CREATE TABLE `unrelated_' + name + '`'))
        with self.assertRaisesRegex(RuntimeError, 'Quartz table set'):
            review.jdbc_review_schema(self.schema + '\nCREATE TABLE `qrtz_unknown` (`id` int);\n')

    def test_jdbc_review_configuration_keeps_execution_and_schema_initialization_disabled(self):
        template = (registration.ROOT / 'deploy/application-launch.properties.template').read_text()
        active = '\n'.join(line for line in template.splitlines() if not line.lstrip().startswith('#'))
        values = {name: 'synthetic-' + name for name in re.findall(r'@([A-Z_]+)@', active)}
        original = registration.render_properties(template, values)
        properties = review.jdbc_review_properties(original)
        pairs = [line.split('=', 1) for line in properties.splitlines() if '=' in line]
        config = dict(pairs)
        self.assertEqual(len(pairs), len(config), 'Review properties must not rely on duplicate-key overrides')
        self.assertEqual(config['spring.quartz.job-store-type'], 'jdbc')
        self.assertEqual(config['spring.quartz.properties.org.quartz.jobStore.tablePrefix'], 'QRTZ_')
        self.assertEqual(config['spring.quartz.auto-startup'], 'false')
        self.assertEqual(config['spring.quartz.overwrite-existing-jobs'], 'false')
        self.assertEqual(config['spring.quartz.jdbc.initialize-schema'], 'never')
        self.assertEqual(config['spring.quartz.properties.org.quartz.jobStore.isClustered'], 'false')
        self.assertIn('spring.quartz.job-store-type=memory\n', original)
        self.assertEqual(template, (registration.ROOT / 'deploy/application-launch.properties.template').read_text())
        for key, bad in [('spring.quartz.auto-startup', 'true'),
                         ('spring.quartz.overwrite-existing-jobs', 'true'),
                         ('spring.quartz.jdbc.initialize-schema', 'always')]:
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'Quartz fixture'):
                review.jdbc_review_properties(original.replace(key + '=' + config[key], key + '=' + bad))


if __name__ == '__main__':
    unittest.main()
