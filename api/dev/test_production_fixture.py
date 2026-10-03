"""Bounded dump parser, identity mapping and isolated-copy regression checks."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import production_fixture as fixture
import snapshot_backend as backend

PROFILE = {'probe': [['id', 'int'], ['text_value', 'longtext'], ['binary_value', 'blob']]}
DDL = 'CREATE TABLE `probe` (`id` int NOT NULL, `text_value` longtext, `binary_value` blob, PRIMARY KEY (`id`)) ENGINE=InnoDB;'


class DumpParserTests(unittest.TestCase):
    def test_quotes_backslashes_unicode_multiline_and_binary(self):
        source = DDL + "\nINSERT INTO `probe` VALUES (1,'it\\\'s; \\\\ \\n中文\nnext',0x000aff5c27),(2,'doubled''quote',NULL);"
        _, rows = fixture.parse_dump(source, PROFILE)
        self.assertEqual(rows['probe'][0]['text_value'], "it's; \\ \n中文\nnext")
        self.assertEqual(rows['probe'][0]['binary_value'], b'\x00\x0a\xff\\\'')
        self.assertEqual(rows['probe'][1]['text_value'], "doubled'quote")
        self.assertIsNone(rows['probe'][1]['binary_value'])

    def test_sql_like_payload_is_inert(self):
        _, rows = fixture.parse_dump(DDL + "INSERT INTO `probe` VALUES (1,'DROP DATABASE other; \\\\! echo x',NULL);", PROFILE)
        emitted = fixture.emit_sql(*fixture.parse_dump(DDL, PROFILE))
        self.assertNotIn('DROP DATABASE', emitted)
        self.assertTrue(fixture.sql_value(rows['probe'][0]['text_value']).startswith("CONVERT(X'"))

    def test_reject_cross_database_or_executable_statements(self):
        bad = ['USE other;', 'CREATE DATABASE other;', 'GRANT ALL ON *.* TO x;',
               'INSERT INTO `other`.`probe` VALUES (1,NULL,NULL);', 'LOAD DATA LOCAL INFILE \'x\' INTO TABLE probe;',
               "SELECT 'x' INTO OUTFILE '/tmp/x';", 'CREATE VIEW `view` AS SELECT 1;',
               'DELIMITER $$', '\\! echo leaked', '/*!50000 DROP DATABASE other */;']
        for statement in bad:
            with self.subTest(statement=statement), self.assertRaises(ValueError):
                fixture.parse_dump(DDL + statement, PROFILE)

    def test_reject_expressions_including_parenthesized_literal(self):
        for value in ['SLEEP(1)', "CONCAT('a','b')", '(1)', "_binary'blob'", '@secret']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                fixture.parse_dump(DDL + 'INSERT INTO `probe` VALUES (1,' + value + ',NULL);', PROFILE)

    def test_reject_unknown_table_column_type_and_order(self):
        for definition in [DDL.replace('`probe`', '`unknown`'), DDL.replace('`text_value` longtext', '`secret_email` longtext'),
                           DDL.replace('`text_value` longtext', '`text_value` text'), DDL.replace('`id` int', '`id` varchar(32)')]:
            with self.subTest(definition=definition), self.assertRaises(ValueError):
                fixture.parse_dump(definition, PROFILE)

    def test_reject_external_table_files_or_foreign_key_targets(self):
        for definition in [DDL.replace('ENGINE=InnoDB', "ENGINE=InnoDB DATA DIRECTORY='/tmp'"),
                           DDL.replace('PRIMARY KEY (`id`)', 'CONSTRAINT `f` FOREIGN KEY (`id`) REFERENCES `other` (`id`)')]:
            with self.subTest(definition=definition), self.assertRaises(ValueError):
                fixture.parse_dump(definition, PROFILE)

    def test_dump_directives_are_discarded(self):
        ddl, rows = fixture.parse_dump('/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE=\'NO_AUTO_VALUE_ON_ZERO\' */;\n' + DDL +
                                       'LOCK TABLES `probe` WRITE; /*!40000 ALTER TABLE `probe` DISABLE KEYS */; UNLOCK TABLES;', PROFILE)
        self.assertEqual(list(ddl), ['probe']); self.assertEqual(rows['probe'], [])

    def test_unterminated_or_incomplete_dump_is_rejected(self):
        for source in [DDL.rstrip(';'), DDL + "INSERT INTO `probe` VALUES (1,'unfinished,NULL);", '/* unfinished']:
            with self.subTest(source=source), self.assertRaises(ValueError): fixture.parse_dump(source, PROFILE)


def synthetic_rows():
    profile = json.loads(fixture.SCHEMA_PROFILE.read_text())
    rows = {name: [] for name in profile}
    def row(table, **values):
        item = {column[0]: None for column in profile[table]}; item.update(values); rows[table].append(item); return item
    for identity, username in [('user_admin_id', 'admin'), ('long_id_with_12345', '12345')]:
        row('sys_user', id=identity, username=username, realname='Private Name', password='old-production-hash', salt='old-salt',
            school='Private School', phone='12345678901', depart_ids='class_12345', status=1)
    row('sys_depart', id='class_12345', parent_id='', depart_name='Private Class')
    row('sys_role', id='role_admin_12345', role_code='admin', role_name='Private Role')
    row('sys_user_role', id='link_12345', user_id='user_admin_id', role_id='role_admin_12345')
    row('sys_user_depart', ID='dept_link', user_id='user_admin_id', dep_id='class_12345')
    row('sys_permission', id='permission_admin_12345', url='/admin/12345', component='admin/Permission', perms='admin:edit')
    row('teaching_course', id='course_12345', course_name='Real course', course_desc='<p>Real learning content</p>', depart_ids='class_12345')
    row('teaching_course_unit', id='unit_12345', course_id='course_12345', unit_name='Real unit', course_video='video.mp4', course_case='', course_ppt=None,
        course_work='template.py', course_work_answer=None, course_plan=None, media_content='<p>Real content</p>', unit_intro='Real intro', unit_cover=None)
    row('teaching_work', id='work_12345', user_id='long_id_with_12345', depart_id='class_12345', course_id='unit_12345',
        work_name='Private work', work_file='file_id', create_by='12345')
    row('sys_file', id='file_id', file_path='Private_Name.py', file_name='Private_Name.py', create_by='12345')
    row('sys_log', id='log', request_param='production login token')
    row('sys_config', id='external', config_value='external-api-secret')
    return rows


class IdentityTests(unittest.TestCase):
    def test_identifiers_roles_routes_and_relationships_preserved(self):
        rows = synthetic_rows(); result = fixture.sanitize(rows, lambda *_: 'new-local-credential', 'local-password')
        self.assertEqual(rows['sys_role'][0]['role_code'], 'admin')
        self.assertEqual(rows['sys_role'][0]['id'], 'role_admin_12345')
        self.assertEqual(rows['sys_permission'][0]['perms'], 'admin:edit')
        self.assertEqual(rows['sys_permission'][0]['component'], 'admin/Permission')
        self.assertEqual(rows['sys_permission'][0]['url'], '/admin/12345')
        users = {row['id']: row for row in rows['sys_user']}
        self.assertIn(rows['sys_user_role'][0]['user_id'], users)
        self.assertEqual(rows['sys_user_role'][0]['role_id'], rows['sys_role'][0]['id'])
        self.assertEqual(rows['teaching_work'][0]['user_id'], rows['teaching_work'][0]['create_by'])
        self.assertEqual(rows['teaching_work'][0]['depart_id'], rows['sys_depart'][0]['id'])
        self.assertEqual(rows['teaching_work'][0]['course_id'], 'unit_12345')
        self.assertEqual(rows['teaching_course_unit'][0]['course_id'], 'course_12345')
        self.assertEqual(rows['teaching_course'][0]['course_desc'], '<p>Real learning content</p>')
        self.assertEqual(rows['sys_log'], []); self.assertEqual(rows['sys_config'], [])
        for row in users.values():
            self.assertTrue(row['username'].startswith('snapshot_user_')); self.assertEqual(row['school'], '')
            self.assertIsNone(row['phone']); self.assertEqual(row['password'], 'new-local-credential')
        self.assertFalse(result['free_text_and_media_fully_anonymous'])

    def test_source_dangling_links_are_not_fabricated(self):
        rows = synthetic_rows(); rows['sys_user_depart'].append({'ID': 'missing', 'user_id': 'deleted_user', 'dep_id': 'deleted_class'})
        summary = fixture.sanitize(rows, lambda *_: 'new-local-credential', 'local-password')
        missing = rows['sys_user_depart'][1]
        self.assertTrue(missing['user_id'].startswith('snapshot_missing_user_'))
        self.assertTrue(missing['dep_id'].startswith('snapshot_missing_dept_'))
        self.assertNotIn(missing['user_id'], {row['id'] for row in rows['sys_user']})
        self.assertNotIn(missing['dep_id'], {row['id'] for row in rows['sys_depart']})
        self.assertEqual(summary['source_dangling_user_ids'], 1); self.assertEqual(summary['source_dangling_department_ids'], 1)

    def test_unknown_operator_maps_and_student_files_withheld(self):
        rows = synthetic_rows(); rows['teaching_course'][0]['create_by'] = 'former-person'
        fixture.sanitize(rows, lambda *_: 'new-local-credential', 'local-password')
        self.assertTrue(rows['teaching_course'][0]['create_by'].startswith('snapshot_actor_'))
        self.assertTrue(rows['sys_file'][0]['file_path'].startswith('snapshot-withheld/'))


class ResourceTests(unittest.TestCase):
    def test_paths_reject_traversal_absolute_and_encoded_forms(self):
        for path in ['../private', '/etc/passwd', 'a/../b', 'a//b', '%2e%2e/private', '%252e%252e/private', 'C:\\secret', 'https://example.invalid/a', 'a\nfile']:
            with self.subTest(path=path), self.assertRaises(ValueError): fixture.safe_relative(path)
        self.assertEqual(fixture.safe_relative('lesson/示例 file.mp4'), 'lesson/示例 file.mp4')

    def test_symlink_components_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'target').write_text('example'); (root / 'link').symlink_to(root / 'target')
            with self.assertRaises(ValueError): fixture.ordinary_asset(root, 'link')

    def test_known_static_relocation_preserves_text_and_other_external_urls(self):
        rows = synthetic_rows()
        rows['teaching_course'][0]['course_desc'] = '<p>Keep exact text</p><img src="https://old.invalid/api/sys/common/static/示例 file.png"><a href="https://outside.invalid/page">Link</a>'
        rows['teaching_course_unit'][0]['course_video'] = 'https://old.invalid/api/sys/common/static/video.mp4'
        rows['teaching_course_unit'][0]['course_video_source'] = 1
        rows['teaching_course_unit'][0]['course_ppt'] = 'https://old.invalid/api/sys/common/static/lesson.pdf,second.pdf'
        changed = fixture.normalize_resources(rows, {'示例 file.png', 'video.mp4', 'lesson.pdf'})
        self.assertEqual(changed, 3)
        self.assertEqual(rows['teaching_course_unit'][0]['course_video'], 'video.mp4')
        self.assertEqual(rows['teaching_course_unit'][0]['course_ppt'], 'lesson.pdf,second.pdf')
        self.assertIn('<p>Keep exact text</p><img src="/api/sys/common/static/示例 file.png">', rows['teaching_course'][0]['course_desc'])
        self.assertIn('https://outside.invalid/page', rows['teaching_course'][0]['course_desc'])

    def test_escaped_json_links_and_unknown_asset_are_not_assumed_verified(self):
        rows = synthetic_rows(); rows['teaching_course_unit'][0]['course_video'] = '[{"url":"https:\\/\\/old.invalid\\/api\\/sys\\/common\\/static\\/video.mp4","name":"Keep label"}]'
        fixture.normalize_resources(rows, {'video.mp4'})
        video = json.loads(rows['teaching_course_unit'][0]['course_video'])
        self.assertEqual(video[0]['url'], 'video.mp4'); self.assertEqual(video[0]['name'], 'Keep label')
        rows['teaching_course_unit'][0]['course_video'] = 'https://old.invalid/api/sys/common/static/missing.mp4'
        fixture.normalize_resources(rows, {'video.mp4'})
        self.assertTrue(rows['teaching_course_unit'][0]['course_video'].startswith('https://old.invalid/'))


class BackendGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        space = self.root / '.devspace'; space.mkdir()
        self.runtime = space / 'snapshot'; self.runtime.mkdir(mode=0o700)
        (self.runtime / 'logs').mkdir(); (self.runtime / 'webapp').mkdir()
        self.jar = self.root / 'candidate.jar'; self.jar.write_bytes(b'not a runnable jar; guard test only')
        self.digest = hashlib.sha256(self.jar.read_bytes()).hexdigest()
        (self.runtime / 'snapshot-manifest.json').write_text('{}')
        self.manifest_digest = fixture.sha256(self.runtime / 'snapshot-manifest.json')

    def tearDown(self): self.temp.cleanup()

    def test_wrong_jar_is_rejected_before_process_launch(self):
        with patch.object(backend.subprocess, 'Popen') as launch, self.assertRaises(ValueError):
            backend.start(self.runtime, self.root, self.jar, '0' * 64)
        launch.assert_not_called()

    def test_baseline_verify_failure_prevents_launch(self):
        with (patch.object(backend.os, 'access', return_value=True), patch.object(backend, 'verify', side_effect=ValueError('tampered snapshot')),
              patch.object(backend.subprocess, 'Popen') as launch, self.assertRaises(ValueError)):
            backend.start(self.runtime, self.root, self.jar, self.digest)
        launch.assert_not_called()

    def test_symlink_record_prevents_launch(self):
        (self.runtime / 'backend.pid').symlink_to(self.root / 'other.pid')
        with (patch.object(backend.os, 'access', return_value=True), patch.object(backend, 'verify', return_value={'manifest_sha256': self.manifest_digest}),
              patch.object(backend.subprocess, 'Popen') as launch, self.assertRaises(ValueError)):
            backend.start(self.runtime, self.root, self.jar, self.digest)
        launch.assert_not_called()

    def test_live_prior_record_prevents_launch(self):
        fixture.private_write(self.runtime / 'backend-process.json', json.dumps({'pid': 42}))
        with (patch.object(backend.os, 'access', return_value=True), patch.object(backend, 'verify', return_value={'manifest_sha256': self.manifest_digest}),
              patch.object(backend, 'process_identity', return_value='live prior process'), patch.object(backend.subprocess, 'Popen') as launch, self.assertRaises(ValueError)):
            backend.start(self.runtime, self.root, self.jar, self.digest)
        launch.assert_not_called()

    def record(self, identity='owned process'):
        record = {'pid': 42, 'profile': 'dev,localtest', 'config_argument': backend.config_argument(self.runtime),
                  'snapshot_manifest_sha256': self.manifest_digest, 'identity': identity, 'jar_path': str(self.jar)}
        fixture.private_write(self.runtime / 'backend-process.json', json.dumps(record))

    def test_stop_rejects_changed_pid_without_signaling(self):
        self.record()
        with (patch.object(backend, 'process_identity', return_value='reused different process'), patch.object(backend.os, 'kill') as signal_process,
              self.assertRaises(ValueError)): backend.stop(self.runtime)
        signal_process.assert_not_called()

    def test_stop_after_business_mutation_uses_identity_without_database_verify(self):
        identity = str(self.jar) + ' --spring.profiles.active=dev,localtest ' + backend.config_argument(self.runtime)
        self.record(identity)
        with (patch.object(backend, 'process_identity', side_effect=[identity, None]), patch.object(backend.os, 'kill') as signal_process,
              patch.object(backend, 'verify', side_effect=AssertionError('Stop must not compare database rows')) as verify):
            self.assertTrue(backend.stop(self.runtime)['stopped'])
        signal_process.assert_called_once(); verify.assert_not_called()


@unittest.skipUnless(os.environ.get('TEACHING_SNAPSHOT_TEST_RUNTIME'), 'explicit dedicated runtime required')
class RealMysqlLiteralTests(unittest.TestCase):
    def test_generated_literals_roundtrip_and_schema_stays_unchanged(self):
        runtime = Path(os.environ['TEACHING_SNAPSHOT_TEST_RUNTIME'])
        fixture.verify(runtime)
        client = [str(runtime / 'tools/mysql-8.4.6-macos15-arm64/bin/mysql'), '--defaults-extra-file=' + str(runtime / 'config/snapshot-app-client.cnf'),
                  '--local-infile=0', '--binary-mode', '--batch', '--skip-column-names', 'teachingopen_dev']
        payload = "it's; \\ multiline\n中文\r\t\0"
        binary = b'\0\n\xff\\\''
        try:
            fixture.command(runtime, client, input=('CREATE TABLE `snapshot_literal_probe` (`id` int, `value` longtext, `binary_value` blob) ENGINE=InnoDB; INSERT INTO `snapshot_literal_probe` VALUES (1,' + fixture.sql_value(payload) + ',' + fixture.sql_value(binary) + ');').encode())
            actual = fixture.command(runtime, client + ['-e', 'SELECT HEX(value),HEX(binary_value) FROM snapshot_literal_probe'], text=True).strip()
            self.assertEqual(actual, payload.encode().hex().upper() + '\t' + binary.hex().upper())
        finally:
            fixture.command(runtime, client + ['-e', 'DROP TABLE IF EXISTS snapshot_literal_probe'], text=True)
        fixture.verify(runtime)


if __name__ == '__main__': unittest.main()
