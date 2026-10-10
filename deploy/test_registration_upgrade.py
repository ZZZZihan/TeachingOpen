#!/usr/bin/env python3
"""Migration receipt tests plus opt-in real MySQL tests in an owned fresh runtime.

Set REGISTRATION_TEST_RUNTIME to the explicit fresh .devspace runtime. These
tests refuse any other port/data directory and only create new test databases.
No old, production-copy, preview or real user database is selected.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import tempfile
import unittest

import registration_upgrade as upgrade

ROOT = Path(__file__).resolve().parents[1]


def packaged(directory):
    for source, name in upgrade.MIGRATIONS:
        shutil.copyfile(ROOT / source, directory / name)
    manifest = directory / upgrade.MANIFEST
    manifest.write_text(json.dumps(upgrade.migration_manifest(ROOT), indent=2) + '\n')
    return upgrade.sha256(manifest)


class MigrationManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='teachingopen-upgrade-')
        self.directory = Path(self.tmp.name).resolve()
        self.hash = packaged(self.directory)

    def tearDown(self):
        self.tmp.cleanup()

    def test_order_and_nontransactional_boundary(self):
        manifest = upgrade.verify_migrations(self.directory, self.hash)
        self.assertEqual(manifest['initialization_order'][:2], ['schema', 'data'])
        self.assertEqual(manifest['existing_database_order'], [name for _, name in upgrade.MIGRATIONS])
        self.assertIs(manifest['automatic_apply'], False)
        self.assertIs(manifest['ddl_transactional'], False)

    def test_sql_change_rejected(self):
        (self.directory / upgrade.MIGRATIONS[0][1]).write_text('-- tampered SQL\n')
        with self.assertRaises(ValueError):
            upgrade.verify_migrations(self.directory, self.hash)

    def test_resealed_manifest_rejected_by_external_hash(self):
        sql = self.directory / upgrade.MIGRATIONS[0][1]
        sql.write_text('-- replaced SQL\n')
        manifest_path = self.directory / upgrade.MANIFEST
        manifest = json.loads(manifest_path.read_text())
        manifest['steps'][0].update(bytes=sql.stat().st_size, sha256=upgrade.sha256(sql))
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            upgrade.verify_migrations(self.directory, self.hash)

    def test_reordered_manifest_rejected_even_without_external_hash(self):
        manifest_path = self.directory / upgrade.MANIFEST
        manifest = json.loads(manifest_path.read_text())
        manifest['steps'].reverse()
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            upgrade.verify_migrations(self.directory)

    def test_symlink_sql_rejected(self):
        sql = self.directory / upgrade.MIGRATIONS[0][1]
        sql.unlink()
        sql.symlink_to(ROOT / upgrade.MIGRATIONS[0][0])
        with self.assertRaises(ValueError):
            upgrade.verify_migrations(self.directory, self.hash)

    def test_apply_requires_maintenance_and_restore_gate_before_connection(self):
        for maintenance, restore in ((False, False), (False, True), (True, False)):
            with self.subTest(maintenance=maintenance, restore=restore), self.assertRaises(ValueError):
                upgrade.apply_upgrade(self.directory, None, None, None, 'unselected', self.hash,
                    self.directory / 'backup.sql', maintenance, restore)


@unittest.skipUnless(os.environ.get('REGISTRATION_TEST_RUNTIME'), 'real MySQL is explicit opt-in')
class NativeMySQLMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = Path(os.environ['REGISTRATION_TEST_RUNTIME']).resolve()
        if cls.runtime.parent.name != '.devspace' or cls.runtime.name != 'launch-upgrade-check-1009':
            raise RuntimeError('Only the explicitly owned fresh registration runtime is accepted')
        tools = (cls.runtime / 'tools').resolve()
        cls.mysql = tools / 'mysql-8.4.6-macos15-arm64/bin/mysql'
        cls.dump = tools / 'mysql-8.4.6-macos15-arm64/bin/mysqldump'
        cls.options = cls.runtime / 'config/mysql-admin-client.cnf'
        command = [str(cls.mysql), '--defaults-extra-file=' + str(cls.options), '--batch', '--skip-column-names']
        result = subprocess.run(command, input='SELECT @@port, @@datadir;\n', text=True, capture_output=True, check=True)
        port, datadir = result.stdout.strip().split('\t')
        if port != '13449' or Path(datadir).resolve() != cls.runtime / 'mysql-data':
            raise RuntimeError('Refusing an unowned database server')
        spec = importlib.util.spec_from_file_location('upgrade_schema_extractor', ROOT / 'api/dev/extract-schema.py')
        extractor = importlib.util.module_from_spec(spec); spec.loader.exec_module(extractor)
        cls.schema = extractor.extract_schema((ROOT / 'api/db/teachingopen2.8.sql').read_text())
        cls.suite_tmp = tempfile.TemporaryDirectory(prefix='registration-native-', dir=cls.runtime)
        cls.directory = Path(cls.suite_tmp.name)
        cls.hash = packaged(cls.directory)

    @classmethod
    def tearDownClass(cls):
        cls.suite_tmp.cleanup()

    def setUp(self):
        self.database = 'registration_test_' + secrets.token_hex(6)
        self.sql('CREATE DATABASE `' + self.database + '` CHARACTER SET utf8mb4;', select=False)
        self.sql(self.schema)
        self.sql("INSERT INTO sys_role(id,role_code,role_name) VALUES ('old_student','student','原学生'),('old_admin','admin','原管理员');\n"
            "INSERT INTO sys_config(id,config_key,config_value,config_enabled) VALUES ('old_allowreg','allowReg','0',1),('other_config','brandName','test',1);")
        for i in range(5):
            name = 'old_account_' + str(i)
            self.sql("INSERT INTO sys_user(id,username,realname,school,phone,password,salt,status,del_flag,user_identity,depart_ids) "
                "VALUES ('" + name + "','" + name + "','原姓名" + str(i) + "','原学校','1390000000" + str(i) +
                "','private-synthetic-password-hash-" + str(i) + "','oldsalt" + str(i) + "',1,0,2,'existing-class');"
                "INSERT INTO sys_user_role(id,user_id,role_id) VALUES ('old_relation_" + str(i) + "','" + name + "','old_admin');")

    def tearDown(self):
        self.sql('DROP DATABASE `' + self.database + '`;', select=False)

    def sql(self, query, select=True, check=True):
        command = [str(self.mysql), '--defaults-extra-file=' + str(self.options), '--default-character-set=utf8mb4',
            '--batch', '--skip-column-names'] + ([self.database] if select else [])
        result = subprocess.run(command, input=query, text=True, capture_output=True)
        if check and result.returncode:
            # Diagnostics are safe only for these all-synthetic tests; still do
            # not include row output/passwords in an assertion report.
            raise AssertionError('Synthetic SQL failed: ' + result.stderr[:1200])
        return result

    def script(self, source_name, preflight_only=False):
        return self.sql('SET @teachingopen_registration_preflight_only = ' + str(int(preflight_only)) + ';\n' +
            (ROOT / source_name).read_text(), check=False)

    def apply(self):
        for source, _ in upgrade.MIGRATIONS:
            result = self.script(source)
            self.assertEqual(result.returncode, 0, result.stderr)

    def data_digest(self):
        # Every sys_user column, password/salt and every role relation is bound;
        # only digests reach assertions, so failures cannot expose credentials.
        user = self.sql('SELECT * FROM sys_user ORDER BY id;').stdout.encode()
        role = self.sql('SELECT * FROM sys_user_role ORDER BY id;').stdout.encode()
        definitions = self.sql('SELECT * FROM sys_role ORDER BY id;').stdout.encode()
        return hashlib.sha256(user + b'\0' + role + b'\0' + definitions).hexdigest()

    def assert_closed(self, mutation):
        self.sql(mutation)
        before = self.data_digest()
        result = self.script(upgrade.MIGRATIONS[0][0])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ERROR 1644', result.stderr)
        self.assertEqual(before, self.data_digest())
        self.assertEqual(self.sql("SELECT config_value FROM sys_config WHERE id='old_allowreg';").stdout.strip(), '0')
        self.assertEqual(self.sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='teaching_registration_profile';").stdout.strip(), '0')

    def test_new_database_schema_then_data_then_upgrade(self):
        self.assertEqual(self.sql('SHOW TABLES;').stdout.count('\n'), 69)
        self.apply()
        self.assertEqual(self.sql('SHOW TABLES;').stdout.count('\n'), 70)
        result = self.sql("SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='sys_user' AND column_name IN ('realname','school') AND character_set_name='utf8mb4';")
        self.assertEqual(result.stdout.strip(), '2')
        self.assertEqual(self.sql("SELECT config_value,config_enabled FROM sys_config WHERE config_key='allowReg';").stdout.strip(), '1\t1')
        self.sql("UPDATE sys_user SET realname='姓名😀', school='学校🧪' WHERE id='old_account_0';")
        self.assertEqual(self.sql("SELECT realname,school FROM sys_user WHERE id='old_account_0';").stdout.strip(), '姓名😀\t学校🧪')
        result = self.sql("INSERT INTO teaching_registration_profile VALUES ('old_account_0','Teacher',CURRENT_TIMESTAMP);", check=False)
        self.assertNotEqual(result.returncode, 0)

    def test_existing_accounts_and_profiles_preserved_on_repeat(self):
        before = self.data_digest()
        self.apply()
        self.assertEqual(before, self.data_digest())
        self.sql("INSERT INTO teaching_registration_profile VALUES ('old_account_0','teacher','2026-01-01 00:00:00');")
        profile = self.sql('SELECT * FROM teaching_registration_profile ORDER BY user_id;').stdout
        self.apply()
        self.assertEqual(before, self.data_digest())
        self.assertEqual(profile, self.sql('SELECT * FROM teaching_registration_profile ORDER BY user_id;').stdout)

    def test_schema_preflight_changes_no_user_data_or_tables(self):
        before = self.data_digest()
        upgrade.preflight(self.directory, self.mysql, self.options, self.database, self.hash)
        self.assertEqual(before, self.data_digest())
        self.assertEqual(self.sql('SHOW TABLES;').stdout.count('\n'), 69)
        self.assertEqual(self.sql("SELECT config_value FROM sys_config WHERE id='old_allowreg';").stdout.strip(), '0')

    def test_missing_student_role_rejected(self):
        self.assert_closed("DELETE FROM sys_role WHERE role_code='student';")

    def test_missing_role_unique_index_rejected(self):
        self.assert_closed('ALTER TABLE sys_role DROP INDEX uniq_sys_role_role_code;')

    def test_missing_phone_unique_index_rejected(self):
        self.assert_closed('ALTER TABLE sys_user DROP INDEX uniq_sys_user_phone;')

    def test_missing_username_unique_index_rejected(self):
        self.assert_closed('ALTER TABLE sys_user DROP INDEX uniq_sys_user_username;')

    def test_prefix_username_unique_index_rejected(self):
        self.assert_closed('ALTER TABLE sys_user DROP INDEX uniq_sys_user_username, ADD UNIQUE INDEX prefix_username(username(20));')

    def test_duplicate_allowreg_even_disabled_rejected(self):
        self.assert_closed("INSERT INTO sys_config(id,config_key,config_value,config_enabled) VALUES ('duplicate_switch','allowReg','0',0);")

    def test_duplicate_student_role_rejected(self):
        self.assert_closed("ALTER TABLE sys_role DROP INDEX uniq_sys_role_role_code; INSERT INTO sys_role(id,role_code) VALUES ('second_student','student');")

    def test_unexpected_column_metadata_rejected_before_alter(self):
        self.assert_closed("ALTER TABLE sys_user MODIFY school varchar(300) NOT NULL DEFAULT '' COMMENT '学校';")

    def test_reviewed_restricted_schema_without_comments_is_compatible(self):
        self.sql("ALTER TABLE sys_user MODIFY realname varchar(100) NULL DEFAULT NULL, MODIFY school varchar(256) NOT NULL DEFAULT '';")
        before = self.data_digest()
        self.apply()
        self.assertEqual(before, self.data_digest())
        result = self.sql("SELECT column_name,column_comment,character_set_name FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='sys_user' AND column_name IN ('realname','school') ORDER BY column_name;")
        self.assertEqual(result.stdout.strip(), 'realname\t真实姓名\tutf8mb4\nschool\t学校\tutf8mb4')

    def test_mixed_comment_variant_is_rejected(self):
        self.assert_closed("ALTER TABLE sys_user MODIFY realname varchar(100) NULL DEFAULT NULL;")

    def test_noncanonical_allowreg_value_rejected(self):
        self.sql("UPDATE sys_config SET config_value='1 ' WHERE id='old_allowreg';")
        result = self.script(upgrade.MIGRATIONS[0][0])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ERROR 1644', result.stderr)
        self.assertEqual(self.sql('SHOW TABLES;').stdout.count('\n'), 69)

    def test_enable_before_schema_rejected_and_switch_closed(self):
        result = self.script(upgrade.MIGRATIONS[1][0])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.sql("SELECT config_value FROM sys_config WHERE id='old_allowreg';").stdout.strip(), '0')

    def test_incompatible_profile_rejected(self):
        self.sql('CREATE TABLE teaching_registration_profile(user_id varchar(32) PRIMARY KEY) ENGINE=InnoDB;')
        before = self.data_digest()
        result = self.script(upgrade.MIGRATIONS[0][0])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.data_digest())
        self.assertEqual(self.sql("SELECT config_value FROM sys_config WHERE id='old_allowreg';").stdout.strip(), '0')

    def test_profile_constraint_with_wrong_semantics_rejected(self):
        self.sql("CREATE TABLE teaching_registration_profile(user_id varchar(32) NOT NULL PRIMARY KEY, identity varchar(16) NOT NULL, create_time datetime NOT NULL, CONSTRAINT chk_registration_identity CHECK (1=1)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")
        before = self.data_digest()
        result = self.script(upgrade.MIGRATIONS[0][0])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ERROR 1644', result.stderr)
        self.assertEqual(before, self.data_digest())

    def test_profile_constraint_with_wrong_literal_case_rejected(self):
        self.sql("CREATE TABLE teaching_registration_profile(user_id varchar(32) NOT NULL PRIMARY KEY, identity varchar(16) NOT NULL, create_time datetime NOT NULL, CONSTRAINT chk_registration_identity CHECK (BINARY identity IN (BINARY 'student', BINARY 'Teacher'))) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")
        result = self.script(upgrade.MIGRATIONS[0][0])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ERROR 1644', result.stderr)

    def test_prior_profile_migration_is_compatible_and_preserved(self):
        self.sql("CREATE TABLE teaching_registration_profile(user_id varchar(32) NOT NULL PRIMARY KEY, identity varchar(16) NOT NULL, create_time datetime NOT NULL, CONSTRAINT chk_registration_identity CHECK (identity IN ('student', 'teacher'))) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")
        self.sql("INSERT INTO teaching_registration_profile VALUES ('old_account_0','teacher','2026-01-01 00:00:00');")
        before = self.data_digest()
        self.apply()
        self.assertEqual(before, self.data_digest())
        self.assertEqual(self.sql('SELECT identity FROM teaching_registration_profile;').stdout.strip(), 'teacher')

    def test_enable_rechecks_duplicates_after_schema_step(self):
        result = self.script(upgrade.MIGRATIONS[0][0])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.sql("INSERT INTO sys_config(id,config_key,config_value,config_enabled) VALUES ('late_duplicate','allowReg','0',0);")
        before = self.data_digest()
        result = self.script(upgrade.MIGRATIONS[1][0])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.data_digest())
        self.assertEqual(self.sql("SELECT config_value FROM sys_config WHERE id='old_allowreg';").stdout.strip(), '0')

    def test_runner_takes_private_backup_before_apply(self):
        before = self.data_digest()
        backup = self.directory / (self.database + '.sql')
        result = upgrade.apply_upgrade(self.directory, self.mysql, self.dump, self.options,
            self.database, self.hash, backup, True, True)
        self.assertEqual(result['status'], 'upgrade_applied')
        self.assertEqual(before, self.data_digest())
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
        receipt = json.loads(Path(str(backup) + '.receipt.json').read_text())
        self.assertEqual(receipt['backup_sha256'], upgrade.sha256(backup))
        self.assertGreater(receipt['backup_bytes'], 0)
        self.assertEqual(receipt['status'], 'upgrade_applied')
        # Restore the actual generated backup into another owned empty database,
        # proving the preserved account and relation bytes can be recovered.
        restored = self.database + '_restore'
        self.sql('CREATE DATABASE `' + restored + '` CHARACTER SET utf8mb4;', select=False)
        try:
            original = self.database
            self.database = restored
            self.sql(backup.read_text())
            self.assertEqual(before, self.data_digest())
            self.assertEqual(self.sql('SHOW TABLES;').stdout.count('\n'), 69)
        finally:
            self.database = original
            self.sql('DROP DATABASE `' + restored + '`;', select=False)


if __name__ == '__main__':
    unittest.main()
