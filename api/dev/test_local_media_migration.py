#!/usr/bin/env python3
"""Opt-in real DDL tests using random databases on an owned synthetic MySQL.

LOCAL_MEDIA_TEST_RUNTIME selects an existing synthetic runtime. No service is
started/stopped, and teachingopen_dev is only read for the ownership assertion.
Each test migrates its own new localmedia_test_* database, then removes it.
"""
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import unittest

from local_runtime import assert_database, mysql_command

API = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('LOCAL_MEDIA_TEST_RUNTIME'), 'native MySQL is explicit opt-in')
class LocalMediaMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = Path(os.environ['LOCAL_MEDIA_TEST_RUNTIME']).resolve()
        if cls.runtime.parent.name != '.devspace':
            raise RuntimeError('Use an explicitly owned synthetic .devspace runtime')
        assert_database(cls.runtime)
        cls.command = mysql_command(cls.runtime)
        cls.migration = (API / 'db/local-media-references.sql').read_text()

    def setUp(self):
        self.database = 'localmedia_test_' + secrets.token_hex(6)
        self.sql('CREATE DATABASE ' + self.database + ' CHARACTER SET utf8mb4', database=False)
        self.sql("CREATE TABLE sys_file(id VARCHAR(64) PRIMARY KEY,file_path VARCHAR(1024) NOT NULL,"
                 "file_location TINYINT NOT NULL,del_flag INT NOT NULL DEFAULT 0) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
                 "CREATE TABLE teaching_work(id VARCHAR(64) PRIMARY KEY,work_file VARCHAR(32) NOT NULL,"
                 "work_cover VARCHAR(32),del_flag INT NOT NULL DEFAULT 0) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
                 "CREATE TABLE teaching_course(id VARCHAR(64) PRIMARY KEY) ENGINE=InnoDB;"
                 "CREATE TABLE teaching_course_unit(id VARCHAR(64) PRIMARY KEY) ENGINE=InnoDB;"
                 "CREATE TABLE teaching_additional_work(id VARCHAR(64) PRIMARY KEY) ENGINE=InnoDB;"
                 "CREATE TABLE sys_config(id VARCHAR(64) PRIMARY KEY) ENGINE=InnoDB;"
                 "CREATE TABLE teaching_news(id VARCHAR(64) PRIMARY KEY) ENGINE=InnoDB;"
                 "CREATE TABLE sys_data_log(id VARCHAR(64) PRIMARY KEY) ENGINE=InnoDB;"
                 "INSERT INTO sys_file VALUES('file-a','unrelated/preserved.png',1,0);"
                 "INSERT INTO teaching_work VALUES('work-a','file-a','file-a',0);")

    def tearDown(self):
        self.sql('DROP DATABASE ' + self.database, database=False)

    def sql(self, statement, database=True, check=True):
        result = subprocess.run(self.command + ([self.database] if database else []),
                                input=statement, text=True, capture_output=True)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def apply(self, preflight=False, check=True):
        return self.sql('SET @teachingopen_registration_preflight_only=' + str(int(preflight)) + ';\n' +
                        self.migration, check=check)

    def preserved(self):
        self.assertEqual(self.sql('SELECT * FROM sys_file').stdout.strip(), 'file-a\tunrelated/preserved.png\t1\t0')
        self.assertEqual(self.sql('SELECT * FROM teaching_work').stdout.strip(), 'work-a\tfile-a\tfile-a\t0')

    def test_preflight_creates_no_tables_indexes_or_rows(self):
        tables = self.sql('SHOW TABLES').stdout
        indexes = self.sql('SHOW INDEX FROM sys_file; SHOW INDEX FROM teaching_work').stdout
        self.apply(preflight=True)
        self.assertEqual(self.sql('SHOW TABLES').stdout, tables)
        self.assertEqual(self.sql('SHOW INDEX FROM sys_file; SHOW INDEX FROM teaching_work').stdout, indexes)
        self.preserved()

    def test_migration_is_additive_and_repeat_preserves_initialized_state(self):
        self.apply()
        self.assertEqual(self.sql('SELECT id,version,static_domain FROM sys_local_file_reference_state').stdout.strip(), '1\t0\tNULL')
        self.assertEqual(self.sql('SELECT COUNT(*) FROM sys_local_file_reference').stdout.strip(), '0')
        self.sql("UPDATE sys_local_file_reference_state SET version=1,static_domain='https://media.example.test/';"
                 "INSERT INTO sys_local_file_reference VALUES('teaching_course','course-a','course_desc','key',SHA2('old/key.png',256),'old/key.png');")
        state = self.sql('SELECT * FROM sys_local_file_reference_state').stdout
        references = self.sql('SELECT * FROM sys_local_file_reference').stdout
        self.apply(); self.apply(preflight=True)
        self.assertEqual(self.sql('SELECT * FROM sys_local_file_reference_state').stdout, state)
        self.assertEqual(self.sql('SELECT * FROM sys_local_file_reference').stdout, references)
        self.assertEqual(self.sql('SHOW TABLES').stdout.count('\n'), 10)
        self.preserved()

    def test_metadata_indexes_have_full_work_keys_and_191_path_prefix(self):
        self.apply()
        rows = self.sql("SELECT table_name,index_name,GROUP_CONCAT(CONCAT(column_name,':',COALESCE(sub_part,'full')) ORDER BY seq_in_index) "
                        "FROM information_schema.statistics WHERE table_schema=DATABASE() AND index_name IN "
                        "('idx_sys_file_local_path','idx_work_file_live','idx_work_cover_live') GROUP BY table_name,index_name ORDER BY table_name,index_name").stdout.strip()
        self.assertEqual(rows, 'sys_file\tidx_sys_file_local_path\tfile_path:191,file_location:full,del_flag:full\n'
                               'teaching_work\tidx_work_cover_live\twork_cover:full,del_flag:full\n'
                               'teaching_work\tidx_work_file_live\twork_file:full,del_flag:full')
        self.preserved()

    def test_text_file_path_is_compatible_with_prefix_index(self):
        self.sql('ALTER TABLE sys_file MODIFY file_path MEDIUMTEXT NOT NULL')
        self.apply(); self.apply()
        self.preserved()

    def test_case_sensitive_ids_long_unicode_values_and_constraints(self):
        self.apply()
        value = '资料😀/' * 1500
        value_hash = hashlib.sha256(value.encode('utf-8')).hexdigest()
        base = "INSERT INTO sys_local_file_reference VALUES('teaching_course',"
        suffix = ",'course_desc','key','" + value_hash + "','" + value + "')"
        self.sql(base + "'case-id'" + suffix)
        self.sql(base + "'CASE-ID'" + suffix)
        self.assertEqual(self.sql('SELECT COUNT(*) FROM sys_local_file_reference').stdout.strip(), '2')
        self.assertEqual(self.sql("SELECT reference_hash FROM sys_local_file_reference WHERE source_id='case-id'").stdout.strip(), value_hash)
        self.assertNotEqual(self.sql(base + "'case-id'" + suffix, check=False).returncode, 0)
        self.assertNotEqual(self.sql("INSERT INTO sys_local_file_reference_state(id,version) VALUES(2,0)", check=False).returncode, 0)
        self.assertNotEqual(self.sql("UPDATE sys_local_file_reference SET reference_kind='other'", check=False).returncode, 0)
        self.apply(); self.preserved()

    def test_incompatible_reserved_metadata_index_is_rejected_before_new_tables(self):
        self.sql('ALTER TABLE sys_file ADD INDEX idx_sys_file_local_path(file_location,file_path(191),del_flag)')
        self.assertNotEqual(self.apply(check=False).returncode, 0)
        self.assertEqual(self.sql('SHOW TABLES').stdout.count('\n'), 8)
        self.preserved()

    def test_incompatible_reference_schema_is_rejected_without_repair(self):
        self.apply()
        self.sql('ALTER TABLE sys_local_file_reference DROP PRIMARY KEY, ADD PRIMARY KEY(reference_hash)')
        self.assertNotEqual(self.apply(preflight=True, check=False).returncode, 0)
        self.assertEqual(self.sql("SELECT GROUP_CONCAT(column_name ORDER BY seq_in_index) FROM information_schema.statistics "
                                 "WHERE table_schema=DATABASE() AND table_name='sys_local_file_reference' AND index_name='PRIMARY'").stdout.strip(), 'reference_hash')
        self.preserved()

    def test_invisible_lookup_or_metadata_index_is_rejected(self):
        self.apply()
        self.sql('ALTER TABLE sys_local_file_reference ALTER INDEX idx_local_reference_lookup INVISIBLE')
        self.assertNotEqual(self.apply(preflight=True, check=False).returncode, 0)
        self.sql('ALTER TABLE sys_local_file_reference ALTER INDEX idx_local_reference_lookup VISIBLE; '
                 'ALTER TABLE teaching_work ALTER INDEX idx_work_cover_live INVISIBLE')
        self.assertNotEqual(self.apply(preflight=True, check=False).returncode, 0)
        self.preserved()

    def test_permissive_reference_check_or_trigger_is_rejected(self):
        self.apply()
        self.sql("ALTER TABLE sys_local_file_reference DROP CHECK chk_local_reference_kind, "
                 "ADD CONSTRAINT chk_local_reference_kind CHECK(reference_kind<>'')")
        self.assertNotEqual(self.apply(check=False).returncode, 0)
        self.sql("ALTER TABLE sys_local_file_reference DROP CHECK chk_local_reference_kind, "
                 "ADD CONSTRAINT chk_local_reference_kind CHECK(reference_kind IN ('key','file'))")
        self.apply()
        self.sql("CREATE TRIGGER wrong_reference BEFORE INSERT ON sys_local_file_reference FOR EACH ROW SET NEW.reference_kind='key'")
        self.assertNotEqual(self.apply(preflight=True, check=False).returncode, 0)
        self.preserved()

    def test_incompatible_state_schema_or_nontransactional_metadata_is_rejected(self):
        self.apply()
        self.sql('ALTER TABLE sys_local_file_reference_state MODIFY version INT NULL DEFAULT 0')
        self.assertNotEqual(self.apply(check=False).returncode, 0)
        self.sql('ALTER TABLE sys_local_file_reference_state MODIFY version INT NOT NULL DEFAULT 0; ALTER TABLE teaching_news ENGINE=MyISAM')
        self.assertNotEqual(self.apply(preflight=True, check=False).returncode, 0)
        self.preserved()


if __name__ == '__main__':
    unittest.main()
