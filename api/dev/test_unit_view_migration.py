#!/usr/bin/env python3
"""Real ledger DDL regression on an explicitly owned synthetic local MySQL only."""
import os
from pathlib import Path
import secrets
import subprocess
import unittest
from local_runtime import assert_database, mysql_command

API = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('UNIT_VIEW_TEST_RUNTIME'), 'native MySQL is explicit opt-in')
class UnitViewMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = Path(os.environ['UNIT_VIEW_TEST_RUNTIME']).resolve()
        if cls.runtime.parent.name != '.devspace' or cls.runtime.name != 'unit-view-retry-1011':
            raise RuntimeError('Use the explicitly owned unit-view synthetic runtime')
        assert_database(cls.runtime)
        cls.command = mysql_command(cls.runtime)
        cls.migration = (API / 'db/unit-view-events.sql').read_text()

    def setUp(self):
        self.database = 'unitview_test_' + secrets.token_hex(6)
        self.sql('CREATE DATABASE ' + self.database + ' CHARACTER SET utf8mb4;', database=False)
        self.sql("CREATE TABLE sys_depart(id VARCHAR(64) PRIMARY KEY) ENGINE=InnoDB;"
                 "CREATE TABLE teaching_depart_day_log(id VARCHAR(64) PRIMARY KEY,unit_open_count INT) ENGINE=InnoDB;"
                 "INSERT INTO teaching_depart_day_log VALUES('historic-count',7);")

    def tearDown(self):
        self.sql('DROP DATABASE ' + self.database + ';', database=False)

    def sql(self, statement, database=True, check=True):
        result = subprocess.run(self.command + ([self.database] if database else []),
            input=statement, text=True, capture_output=True)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def apply(self, preflight=False, check=True):
        return self.sql('SET @teachingopen_registration_preflight_only=' + str(int(preflight)) + ';\n' + self.migration, check=check)

    def preserved_count(self):
        self.assertEqual(self.sql('SELECT unit_open_count FROM teaching_depart_day_log;').stdout.strip(), '7')

    def test_preflight_does_not_create_ledger_or_change_history(self):
        self.apply(preflight=True)
        self.assertEqual(self.sql('SHOW TABLES;').stdout.count('\n'), 2)
        self.preserved_count()

    def test_repeat_apply_preserves_history_and_ledger_rows(self):
        self.apply()
        self.sql("INSERT INTO teaching_unit_view_event(depart_id,unit_id,observed_user_id,event_state,counted_day) "
                 "VALUES('class-a','unit-a','student-a','COUNTED','2026-10-11'),('class-a','unit-b','student-a','LEGACY_UNRESOLVED',NULL);")
        self.apply(); self.apply(preflight=True)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM teaching_unit_view_event;').stdout.strip(), '2')
        self.preserved_count()

    def test_check_primary_key_and_binary_ids_are_enforced(self):
        self.apply()
        base = "INSERT INTO teaching_unit_view_event(depart_id,unit_id,observed_user_id,event_state,counted_day) VALUES"
        self.sql(base + "('class-a','unit-a','student-a','COUNTED','2026-10-11');")
        self.assertNotEqual(self.sql(base + "('class-a','unit-a','student-b','COUNTED','2026-10-12');", check=False).returncode, 0)
        for state, day in (("'COUNTED'", 'NULL'), ("'LEGACY_UNRESOLVED'", "'2026-10-11'"), ("'UNKNOWN'", 'NULL')):
            self.assertNotEqual(self.sql(base + "('class-a','invalid','student-a'," + state + ',' + day + ');', check=False).returncode, 0)
        self.sql(base + "('class-a','UNIT-A','student-a','COUNTED','2026-10-11');")
        self.assertEqual(self.sql('SELECT COUNT(*) FROM teaching_unit_view_event;').stdout.strip(), '2')

    def test_incompatible_existing_key_is_rejected_without_repair(self):
        self.apply()
        self.sql('ALTER TABLE teaching_unit_view_event DROP PRIMARY KEY, ADD PRIMARY KEY(unit_id);')
        self.assertNotEqual(self.apply(check=False).returncode, 0)
        self.assertEqual(self.sql("SELECT GROUP_CONCAT(column_name ORDER BY seq_in_index) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='teaching_unit_view_event' AND index_name='PRIMARY';").stdout.strip(), 'unit_id')
        self.preserved_count()

    def test_permissive_replacement_check_is_rejected(self):
        self.apply()
        self.sql("ALTER TABLE teaching_unit_view_event DROP CHECK chk_unit_view_event_state, ADD CONSTRAINT chk_unit_view_event_state CHECK(event_state <> '');")
        self.assertNotEqual(self.apply(check=False).returncode, 0)
        self.preserved_count()

    def test_extra_unique_constraint_cannot_break_cross_class_deduplication(self):
        self.apply()
        self.sql('ALTER TABLE teaching_unit_view_event ADD UNIQUE KEY unexpected_unit_unique(unit_id);')
        self.assertNotEqual(self.apply(preflight=True, check=False).returncode, 0)
        self.preserved_count()

    def test_extra_check_is_rejected_without_changing_it(self):
        self.apply()
        self.sql("ALTER TABLE teaching_unit_view_event ADD CONSTRAINT unexpected_check CHECK(depart_id='only-one-class');")
        self.assertNotEqual(self.apply(preflight=True, check=False).returncode, 0)
        self.preserved_count()

    def test_existing_trigger_requires_review_instead_of_automatic_acceptance(self):
        self.apply()
        self.sql("CREATE TRIGGER unexpected_ledger_trigger BEFORE INSERT ON teaching_unit_view_event FOR EACH ROW SET NEW.unit_id='rewritten';")
        self.assertNotEqual(self.apply(preflight=True, check=False).returncode, 0)
        self.preserved_count()

    def test_nontransactional_statistics_table_is_rejected(self):
        self.sql('ALTER TABLE teaching_depart_day_log ENGINE=MyISAM;')
        self.assertNotEqual(self.apply(check=False).returncode, 0)
        self.assertEqual(self.sql('SHOW TABLES;').stdout.count('\n'), 2)
        self.preserved_count()


if __name__ == '__main__':
    unittest.main()
