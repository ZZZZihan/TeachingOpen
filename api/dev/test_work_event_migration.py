#!/usr/bin/env python3
"""Real MySQL migration/review tests, isolated random databases on an owned fixture server."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import unittest
from local_runtime import assert_database, mysql_command

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'deploy'))
import work_event_review as review


@unittest.skipUnless(os.environ.get('WORK_EVENT_TEST_RUNTIME'), 'explicit synthetic MySQL runtime required')
class WorkEventMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = Path(os.environ['WORK_EVENT_TEST_RUNTIME']).resolve()
        if cls.runtime.parent.name != '.devspace' or cls.runtime.name != 'teachingopen-highrisk-20261012':
            raise RuntimeError('Use only the explicitly owned release-review synthetic runtime')
        assert_database(cls.runtime)
        cls.command = mysql_command(cls.runtime)
        cls.migration = (ROOT / 'api/db/work-events.sql').read_text()

    def setUp(self):
        self.database = 'workevent_test_' + secrets.token_hex(6)
        self.sql('CREATE DATABASE ' + self.database + ' CHARACTER SET utf8mb4', database=False)
        self.sql("CREATE TABLE sys_depart(id VARCHAR(64) PRIMARY KEY) ENGINE=InnoDB;"
                 "CREATE TABLE teaching_depart_day_log(id VARCHAR(64) PRIMARY KEY,course_work_correct_count INT) ENGINE=InnoDB;"
                 "CREATE TABLE teaching_work(id VARCHAR(64) PRIMARY KEY,depart_id VARCHAR(64),course_id VARCHAR(64),additional_id VARCHAR(64),work_status INT) ENGINE=InnoDB;"
                 "CREATE TABLE teaching_work_correct(id VARCHAR(64) PRIMARY KEY,work_id VARCHAR(64)) ENGINE=InnoDB;"
                 "CREATE TABLE sys_data_log(id VARCHAR(64) PRIMARY KEY,data_table VARCHAR(64),data_id VARCHAR(64)) ENGINE=InnoDB;"
                 "INSERT INTO teaching_depart_day_log VALUES('historical',7);")

    def tearDown(self):
        self.sql('DROP DATABASE ' + self.database, database=False)

    def sql(self, sql, database=True, check=True):
        result = subprocess.run(self.command + ([self.database] if database else []), input=sql, text=True, capture_output=True)
        if check: self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def apply(self, preflight=False, check=True):
        return self.sql('SET @teachingopen_registration_preflight_only=' + str(int(preflight)) + ';\n' + self.migration, check=check)

    def preserved(self):
        self.assertEqual(self.sql('SELECT course_work_correct_count FROM teaching_depart_day_log').stdout.strip(), '7')

    def test_empty_cutover_and_rerun_do_not_classify_new_works_as_legacy(self):
        self.apply(); self.sql("INSERT INTO teaching_work VALUES('new','class-a','unit-a','',0)")
        self.apply(); self.apply(preflight=True)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM teaching_work_event').stdout.strip(), '0')
        self.assertEqual(self.sql('SELECT COUNT(*) FROM teaching_work_event_cutover').stdout.strip(), '1'); self.preserved()

    def test_existing_work_is_explicitly_pending_and_both_types_are_required(self):
        self.sql("INSERT INTO teaching_work VALUES('old','class-a','unit-a','',0),('personal','class-a','','',1)")
        self.apply(); self.apply()
        rows = review.snapshot(self.command + [self.database], self.database)
        self.assertEqual(len(rows['events']), 2)
        self.assertEqual({row['event_type'] for row in rows['events']}, {'SUBMIT','CORRECT'})
        self.assertTrue(all(row['event_state'] == 'LEGACY_REVIEW' for row in rows['events'])); self.preserved()

    def test_decisions_require_evidence_and_preserve_historical_aggregate(self):
        self.sql("INSERT INTO teaching_work VALUES('old','class-a','unit-a','',0)"); self.apply()
        command = self.command + [self.database]; manifest = review.snapshot(command, self.database)
        with tempfile.NamedTemporaryFile() as backup:
            backup.write(b'synthetic independent backup'); backup.flush()
            with self.assertRaises(ValueError): review.apply_review(command, self.database, manifest, Path(backup.name).resolve(), True)
            for row in manifest['events']:
                row.update(decision='READY' if row['event_type'] == 'CORRECT' else 'LEGACY_UNRESOLVED', evidence='Synthetic history and Redis snapshot independently reviewed')
            with self.assertRaises(ValueError): review.apply_review(command, self.database, manifest, Path(backup.name).resolve(), False)
            result = review.apply_review(command, self.database, manifest, Path(backup.name).resolve(), True)
            self.assertEqual(result['resolved'], 2)
            self.assertFalse(result['historical_counters_changed'])
            self.assertEqual(len(review.snapshot(command, self.database)['events']), 0)
            with self.assertRaises(ValueError): review.apply_review(command, self.database, manifest, Path(backup.name).resolve(), True)
        self.preserved()

    def test_preflight_creates_no_tables(self):
        before = self.sql('SHOW TABLES').stdout; self.apply(preflight=True)
        self.assertEqual(before, self.sql('SHOW TABLES').stdout); self.preserved()

    def test_unique_key_event_type_state_date_and_binary_ids_enforced(self):
        self.apply(); base="INSERT INTO teaching_work_event(work_id,event_type,depart_id,event_state,counted_day) VALUES "
        self.sql(base+"('work-a','CORRECT','class-a','COUNTED','2026-10-12')")
        self.assertNotEqual(self.sql(base+"('work-a','CORRECT','class-a','COUNTED','2026-10-13')",check=False).returncode,0)
        for event,state,day in [('OTHER','COUNTED',"'2026-10-12'"),('SUBMIT','COUNTED','NULL'),('SUBMIT','LEGACY_REVIEW',"'2026-10-12'"),('SUBMIT','OTHER','NULL')]:
            self.assertNotEqual(self.sql(base+"('other','"+event+"','class-a','"+state+"',"+day+")",check=False).returncode,0)
        self.sql(base+"('WORK-A','CORRECT','class-a','COUNTED','2026-10-12')"); self.preserved()

    def test_incompatible_state_check_fails_without_repair(self):
        self.apply(); self.sql("ALTER TABLE teaching_work_event DROP CHECK chk_work_event_state, ADD CONSTRAINT chk_work_event_state CHECK(event_state<>'')")
        self.assertNotEqual(self.apply(check=False).returncode,0); self.preserved()

    def test_extra_unique_key_or_trigger_fails_preflight(self):
        self.apply(); self.sql('ALTER TABLE teaching_work_event ADD UNIQUE KEY wrong_unique(work_id)')
        self.assertNotEqual(self.apply(preflight=True,check=False).returncode,0)
        self.sql('ALTER TABLE teaching_work_event DROP KEY wrong_unique'); self.apply(preflight=True)
        self.sql("CREATE TRIGGER wrong_event BEFORE INSERT ON teaching_work_event FOR EACH ROW SET NEW.event_state='READY'")
        self.assertNotEqual(self.apply(check=False).returncode,0); self.preserved()

    def test_lost_ledger_or_lost_cutover_cannot_recreate_history(self):
        self.apply(); self.sql('DROP TABLE teaching_work_event')
        self.assertNotEqual(self.apply(check=False).returncode,0); self.preserved()

    def test_nontransactional_work_table_fails(self):
        self.sql('ALTER TABLE teaching_work ENGINE=MyISAM'); self.assertNotEqual(self.apply(check=False).returncode,0); self.preserved()


if __name__ == '__main__': unittest.main()
