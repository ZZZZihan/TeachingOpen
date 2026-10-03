"""Pure tests only: never connect to a database, Redis, or application listener."""
import copy
from decimal import Decimal
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import role_flow_fixture as f


def original_seed():
    spec = importlib.util.spec_from_file_location('unchanged_seed', f.HERE / 'seed-fixtures.py')
    seed = importlib.util.module_from_spec(spec); spec.loader.exec_module(seed)
    rows = copy.deepcopy(f.base_records())
    for record in rows['sys_user']:
        record['salt'] = '01234567'
        record['password'] = '0' * ((len(record['username']) // 8 + 1) * 16)
    out = ['START TRANSACTION;']
    for table, data in rows.items():
        for row in data:
            out.append('INSERT INTO `' + table + '` (' + ','.join('`' + c + '`' for c in row) + ') VALUES (' + ','.join(seed.quote(v) for v in row.values()) + ');')
    return '\n'.join(out + ['COMMIT;']), rows


class FixtureRecords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = f.schema_model()
        cls.assets = f.generated_assets()

    def test_seed_round_trip_and_all_column_defaults(self):
        data, rows = original_seed()
        parsed = f.parse_original_seed(data)
        self.assertEqual(parsed, {t: [{n: str(v) for n, v in r.items()} for r in data] for t, data in rows.items()})
        expected = f.complete_records(self.model, parsed)
        actual = {table: [{name: None if v is None else str(v) for name, v in row.items()} for row in records] for table, records in expected.items()}
        f.compare_records(self.model, actual, expected)
        self.assertEqual(69, len(expected))
        self.assertEqual('int unsigned zerofill', self.model['sys_dict']['type']['type'])

    def test_original_seed_cannot_add_sql_or_expressions(self):
        data, _ = original_seed()
        for suffix in ('USE another;', 'GRANT ALL ON *.* TO other;', "INSERT INTO `sys_config` (`id`) VALUES ('x');"):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                f.parse_original_seed(data.replace('COMMIT;', suffix + ' COMMIT;'))
        with self.assertRaises(ValueError):
            f.parse_original_seed(data.replace("'fixture_admin'", 'CONCAT(\'fixture_\',\'admin\')', 1))

    def test_unknown_account_and_duplicate_id_are_rejected(self):
        data, _ = original_seed()
        with self.assertRaises(ValueError): f.parse_original_seed(data.replace('fixture_student_b', 'fixture_intruder_b'))
        insert = next(line for line in data.splitlines() if line.startswith('INSERT INTO `sys_user`'))
        with self.assertRaises(ValueError): f.parse_original_seed(data.replace('COMMIT;', insert + '\nCOMMIT;'))

    def test_unexpected_business_data_and_modified_fields_refuse(self):
        _, original = original_seed()
        baseline = f.complete_records(self.model, original)
        for table, field, value in [('sys_user', 'realname', 'unapproved name'), ('sys_role', 'role_code', 'dev'), ('sys_depart', 'org_category', '3'), ('teaching_work', 'work_status', 1)]:
            altered = copy.deepcopy(baseline); altered[table][0][field] = value
            with self.subTest(table=table, field=field), self.assertRaises(ValueError):
                f.compare_records(self.model, altered, baseline)
        altered = copy.deepcopy(baseline); altered['sys_config'] = [{'id': 'existing'}]
        with self.assertRaises(ValueError): f.compare_records(self.model, altered, baseline)
        altered = copy.deepcopy(baseline); altered['new_business_table'] = []
        with self.assertRaises(ValueError): f.compare_records(self.model, altered, baseline)

    def test_new_columns_and_required_values_refuse(self):
        _, original = original_seed()
        baseline = f.complete_records(self.model, original)
        altered = copy.deepcopy(baseline); altered['sys_user'][0]['unreviewed_contact'] = 'x'
        with self.assertRaises(ValueError): f.compare_records(self.model, altered, baseline)
        with self.assertRaises(ValueError): f.complete_records(self.model, {'sys_config': [{'id': 'fixture_ui_config'}]})

    def test_five_accounts_roles_and_old_work_relations_stay_exact(self):
        _, original = original_seed()
        before = f.complete_records(self.model, original)
        after = f.expected_after(self.model, original, f.ui_records(self.assets))
        for table in ('sys_user', 'sys_user_role', 'sys_user_depart', 'sys_role', 'teaching_work'):
            self.assertEqual(before[table], after[table])
        self.assertEqual(5, len(after['sys_user']))
        self.assertEqual(['admin', 'teacher', 'student'], [r['role_code'] for r in after['sys_role']])
        for row in after['sys_depart']:
            self.assertEqual('1' if row['id'] == 'fixture_school' else '3', row['org_category'])
        self.assertFalse(any(r['course_id'].startswith('fixture_ui') for r in after['teaching_work']))

    def test_real_permission_registration_and_minimum_role_boundaries(self):
        rows = f.ui_records(self.assets)
        permissions = {r['id']: r for r in rows['sys_permission']}
        grants = {role: {permissions[r['permission_id']]['url'] for r in rows['sys_role_permission'] if r['role_id'] == 'fixture_role_' + role and 'url' in permissions[r['permission_id']]} for role in ('admin', 'teacher', 'student')}
        self.assertIn('/teaching/mineCourse/courseUnitCard', grants['student'])
        self.assertIn('/center/myAdditionalWork', grants['student'])
        self.assertNotIn('/teaching/workList', grants['student'])
        self.assertIn('/teaching/workList', grants['teacher'])
        self.assertNotIn('/isystem/user', grants['teacher'])
        self.assertIn('/isystem/user', grants['admin'])
        self.assertIn('/isystem/departDetailList', grants['admin'])
        for row in rows['sys_role_permission']:
            self.assertIn(row['permission_id'], permissions)
        buttons = [r for r in permissions.values() if r['menu_type'] == 2]
        self.assertEqual({'user:edit', 'user:status'}, {r['perms'] for r in buttons})
        self.assertTrue(all(r['status'] == '1' and r['perms_type'] == '1' for r in buttons))
        dictionary = next(r['id'] for r in rows['sys_dict'] if r['dict_code'] == 'work_status')
        self.assertEqual({'0': '草稿', '1': '已提交', '2': '已批改', '3': '公开展示', '4': '精选'},
                         {r['item_value']: r['item_text'] for r in rows['sys_dict_item'] if r['dict_id'] == dictionary})

    def test_empty_org_rule_and_published_class_task(self):
        rows = f.ui_records(self.assets)
        rule = rows['sys_fill_rule'][0]
        self.assertEqual('org_num_role', rule['rule_code'])
        self.assertEqual('org.jeecg.modules.system.rule.OrgCodeRule', rule['rule_class'])
        self.assertEqual({}, json.loads(rule['rule_params']))
        task = rows['teaching_additional_work'][0]
        self.assertEqual(('fixture_class_a', 1, 0), (task['work_dept'], task['status'], task['code_type']))

    def test_resources_are_local_registered_visible_and_valid(self):
        rows = f.ui_records(self.assets)
        paths = {r['file_path'] for r in rows['sys_file']}
        self.assertEqual({'role-flow/' + name for name in self.assets}, paths)
        for unit in rows['teaching_course_unit']:
            for field in ('unit_cover', 'course_video', 'course_case', 'course_ppt', 'course_work', 'course_plan'):
                self.assertIn(unit[field], paths)
                self.assertNotIn('://', unit[field])
            self.assertEqual((1, 1, 1, 0), (unit['course_video_source'], unit['show_course_video'], unit['show_course_ppt'], unit['show_course_plan']))
        self.assertEqual({2, 3, 4}, {r['course_work_type'] for r in rows['teaching_course_unit']})
        with zipfile.ZipFile(io.BytesIO(self.assets['starter.sb3'])) as archive:
            project = json.loads(archive.read('project.json'))
            self.assertEqual(2, len(project['targets']))
            self.assertFalse(project['extensions'])
            for target in project['targets']:
                for costume in target['costumes']:
                    self.assertEqual(costume['assetId'], hashlib.md5(archive.read(costume['md5ext'])).hexdigest())
        with zipfile.ZipFile(io.BytesIO(self.assets['starter.sjr'])) as archive:
            project = json.loads(archive.read('project/data.json'))
            self.assertEqual(['page 1'], project['json']['pages'])
            self.assertIn('project/thumbnails/' + project['thumbnail']['md5'], archive.namelist())
        self.assertEqual(b'\x89PNG\r\n\x1a\n', self.assets['cover.png'][:8])
        self.assertEqual(b'ftyp', self.assets['lesson.mp4'][4:8])
        compile(self.assets['starter.py'], 'synthetic-starter.py', 'exec')

    def test_fixed_mutations_use_hex_text_and_no_ddl_or_source_execution(self):
        rows = f.ui_records(self.assets)
        rows['teaching_course'][0]['course_desc'] = "quote ' \\ newline\n); DROP DATABASE other;"
        payload = f.fixture_sql(rows)
        self.assertEqual(2, payload.count('UPDATE `sys_depart`'))
        self.assertNotIn('DROP DATABASE', payload)
        self.assertNotIn('GRANT ', payload)
        self.assertNotIn('CREATE TABLE', payload)
        self.assertTrue(payload.endswith('COMMIT;\n'))
        for table, records in rows.items():
            for row in records:
                self.assertLessEqual(len(row['id']), 32)
        self.assertEqual(Decimal('0'), Decimal('0.00'))


class ColdRuntimeGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=f.HERE)
        parent = Path(self.temp.name) / '.devspace'; parent.mkdir(mode=0o700)
        self.runtime = parent / 'role-flow-pure-test'; self.runtime.mkdir(mode=0o700)
        for name in ('config', 'uploads', 'mysql-data', 'logs'): (self.runtime / name).mkdir(mode=0o700)
        self.ports = {'mysql': 23350, 'redis': 26423, 'backend': 28149, 'frontend': 28150}
        f.private_write(self.runtime / 'ports.json', json.dumps(self.ports))
        self.credentials = {k: '0' * 40 for k in ('mysql_root_password', 'mysql_app_password', 'redis_password', 'test_user_password')}
        f.private_write(self.runtime / 'config/credentials.json', json.dumps(self.credentials))
        template = (f.HERE / 'application-localtest.properties.template').read_text()
        replacements = {'RUNTIME': str(self.runtime), 'MYSQL_APP_PASSWORD': '0' * 40, 'REDIS_PASSWORD': '0' * 40}
        replacements.update({k.upper() + '_PORT': str(v) for k, v in self.ports.items()})
        for k, v in replacements.items(): template = template.replace('@' + k + '@', v)
        f.private_write(self.runtime / 'config/application-localtest.properties', template)
        f.private_write(self.runtime / 'config/mysql-admin-client.cnf', '[client]\nuser=root\nhost=127.0.0.1\nport=23350\nprotocol=tcp\npassword=' + '0' * 40 + '\n')
        self.patches = [patch.object(f, 'assert_app_config'), patch.object(f, 'assert_mysql_owner'), patch.object(f, 'assert_database'), patch.object(f.socket, 'socket')]
        for p in self.patches: p.start()
        f.socket.socket.return_value.__enter__.return_value.connect_ex.return_value = 1

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()

    def test_valid_only_with_fresh_private_runtime(self):
        self.assertEqual(self.runtime, f.cold_runtime(self.runtime, creating=True))
        f.assert_mysql_owner.assert_called_once_with(self.runtime)
        f.assert_database.assert_called_once_with(self.runtime)

    def test_wrong_runtime_name_permissions_symlink_and_existing_ports(self):
        renamed = self.runtime.with_name('backend-runtime'); self.runtime.rename(renamed)
        with self.assertRaises(ValueError): f.cold_runtime(renamed)
        renamed.rename(self.runtime)
        self.runtime.chmod(0o755)
        with self.assertRaises(ValueError): f.cold_runtime(self.runtime)
        self.runtime.chmod(0o700)
        (self.runtime / 'uploads').rmdir(); (self.runtime / 'uploads').symlink_to(self.runtime / 'logs')
        with self.assertRaises(ValueError): f.cold_runtime(self.runtime)
        (self.runtime / 'uploads').unlink(); (self.runtime / 'uploads').mkdir(mode=0o700)
        self.ports['backend'] = 18141; (self.runtime / 'ports.json').write_text(json.dumps(self.ports))
        with self.assertRaises(ValueError): f.cold_runtime(self.runtime)

    def test_active_listener_or_any_application_history_refuses(self):
        f.socket.socket.return_value.__enter__.return_value.connect_ex.return_value = 0
        with self.assertRaises(ValueError): f.cold_runtime(self.runtime)
        f.socket.socket.return_value.__enter__.return_value.connect_ex.return_value = 1
        for name in ('backend.pid', 'backend-process.json', 'frontend.pid', 'frontend-process.json'):
            f.private_write(self.runtime / name, 'stopped or stale')
            with self.subTest(name=name), self.assertRaises(ValueError): f.cold_runtime(self.runtime)
            (self.runtime / name).unlink()

    def test_completed_or_incomplete_one_shot_state_refuses(self):
        for name in (f.MANIFEST, f.STARTED, 'role-flow-app-client.cnf'):
            f.private_write(self.runtime / name, '{}')
            with self.subTest(name=name), self.assertRaises(ValueError): f.cold_runtime(self.runtime, creating=True)
            (self.runtime / name).unlink()

    def test_wrong_datadir_guard_runs_and_external_config_is_rejected(self):
        f.assert_mysql_owner.side_effect = RuntimeError('different datadir')
        with self.assertRaises(RuntimeError): f.cold_runtime(self.runtime)
        f.assert_mysql_owner.side_effect = None
        profile = self.runtime / 'config/application-localtest.properties'
        profile.write_text(profile.read_text().replace('jeecg.oss.endpoint=http://127.0.0.1:9', 'jeecg.oss.endpoint=https://outside.invalid'))
        with self.assertRaises(ValueError): f.cold_runtime(self.runtime)


if __name__ == '__main__': unittest.main()
