"""Synthetic launch-policy, package-integrity and source-isolation checks."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import prepare_launch_data as launch
import production_fixture as fixture


def synthetic_rows():
    profile = json.loads(fixture.SCHEMA_PROFILE.read_text())
    rows = {table: [] for table in profile}

    def add(table, **values):
        row = {column: None for column, _ in profile[table]}
        if set(values) - set(row):
            raise AssertionError('Synthetic fixture uses an unreviewed column')
        row.update(values)
        rows[table].append(row)
        return row

    add('sys_depart', id='organization', parent_id='', org_type='1', org_code='ORG', del_flag='0', depart_name='Synthetic organization')
    add('sys_depart', id='old-class', parent_id='organization', org_type='2', org_code='ORGCLASS', del_flag='0', depart_name='Old class')
    add('sys_user', id='admin-account', username='synthetic-admin', realname='Synthetic Admin', password='synthetic-password-hash', salt='synthetic-salt', status=1, del_flag=0, org_code='ORG', depart_ids='old-class,already-deleted-class', school='', create_by='historical-teacher')
    add('sys_user', id='frozen-admin', username='frozen-admin', password='other-hash', salt='other-salt', status=2, del_flag=0)
    add('sys_user', id='old-student', username='old-student', password='student-hash', salt='student-salt', status=1, del_flag=0)
    for code in ('admin', 'dev', 'student', 'teacher'):
        add('sys_role', id='role-' + code, role_code=code, role_name='System ' + code, create_by='old-student')
    for identity, user, code in (('ur-admin', 'admin-account', 'admin'), ('ur-dev', 'admin-account', 'dev'), ('ur-frozen', 'frozen-admin', 'admin'), ('ur-student', 'old-student', 'student')):
        add('sys_user_role', id=identity, user_id=user, role_id='role-' + code)
    add('sys_user_depart', ID='old-membership', user_id='old-student', dep_id='old-class')
    for code in ('admin', 'dev', 'student'):
        add('sys_permission', id='permission-' + code, parent_id='', name='System permission', url='/' + code, del_flag=0)
        add('sys_role_permission', id='rp-' + code, role_id='role-' + code, permission_id='permission-' + code)
    add('sys_role_permission', id='rp-orphan', role_id='role-admin', permission_id='deleted-permission')
    add('sys_permission_data_rule', id='valid-rule', permission_id='permission-admin', rule_value='#{sys_user_code}')
    rows['sys_role_permission'][0]['data_rule_ids'] = 'valid-rule'
    add('sys_permission_data_rule', id='orphan-rule', permission_id='deleted-permission')
    add('sys_dict', id='required-dictionary', dict_code='system-definition', dict_name='System definition')
    add('sys_dict_item', id='valid-item', dict_id='required-dictionary', item_text='Valid system option', item_value='1')
    add('sys_dict_item', id='orphan-item', dict_id='deleted-dictionary', item_text='Obsolete option', item_value='2')
    add('sys_config', id='config-registration', config_key='allowReg', config_value='0', config_enabled=1)
    add('sys_config', id='config-old-class', config_key='_defaultDepart', config_value='old-class', config_enabled=1)
    add('sys_config', id='config-old-role', config_key='_defaultRole', config_value='role-teacher', config_enabled=1)
    add('sys_config', id='config-old-homepage', config_key='_homeHtml', config_value='<h2>Legacy welcome page</h2>', config_enabled=1)
    add('sys_config', id='config-brand-name', config_key='brandName', config_value='Current system name', config_enabled=1)
    for key in ('brandDesc', 'bannerLinks', 'homeBgColor', 'homeBgRepeat', 'file_homeBg', 'footer', 'customJS', 'customCss'):
        add('sys_config', id='config-old-visual-' + key, config_key=key, config_value='Legacy visual override', config_enabled=1)
    for key in ('logo', 'banner', 'logo2'):
        add('sys_config', id='config-' + key, config_key=key, config_value=key + '.png', config_enabled=1)
    add('teaching_course', id='public-course', course_name='真实课程🌟', course_desc="<p>it’s safe; DROP DATABASE any; \\\n</p>", is_shared=1, show_home=1, depart_ids='', course_cover='course.png', create_by='historical-teacher', sys_org_code='ORG')
    add('teaching_course', id='hidden-course', course_name='Hidden empty course', is_shared=0, show_home=0, depart_ids='')
    add('teaching_course_unit', id='real-unit', course_id='public-course', unit_name='真实单元', course_video='video.mp4', course_video_source=1, unit_cover='unit.png', media_content='<p>Real learning content</p>', create_by='old-student', sys_org_code='ORG')
    add('teaching_course_dept', id='old-course-class', course_id='public-course', dept_id='old-class')
    add('teaching_work', id='old-submission', user_id='old-student', work_file='student-file')
    add('sys_file', id='student-file', file_path='student.py')
    add('sys_log', id='old-session', username='old-student')
    add('teaching_depart_day_log', id='old-progress', depart_id='old-class')
    add('teaching_scratch_assets', id='old-cloud-data', asset_name='private-student-asset')
    add('sys_data_source', id='production-connection', db_password='synthetic-production-secret')
    add('teaching_menu', id='legacy-front-menu', name='Old configured navigation', url='/legacy-route', hidden=0, menu_type=0)
    add('jeecg_order_customer', id='demonstration-customer', name='Private demo name')
    return rows


def synthetic_ddl():
    profile = json.loads(fixture.SCHEMA_PROFILE.read_text())
    source = '\n'.join('CREATE TABLE `' + table + '` (' + ','.join('`' + name + '` ' + dtype for name, dtype in columns) + ') ENGINE=InnoDB;' for table, columns in profile.items())
    return fixture.parse_dump(source)[0]


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.source = synthetic_rows()

    def test_retains_original_login_both_roles_and_effective_permissions(self):
        before = copy.deepcopy(self.source)
        selected, changes = launch.select_rows(self.source)
        original = self.source['sys_user'][0]
        admin = selected['sys_user'][0]
        for key in ('id', 'username', 'realname', 'password', 'salt', 'status', 'del_flag', 'org_code'):
            self.assertEqual(admin[key], original[key])
        self.assertEqual(launch.admin_permission_set(selected, admin['id']), launch.admin_permission_set(self.source, admin['id']))
        self.assertEqual(len(selected['sys_user_role']), 2)
        self.assertEqual(changes['administrator_effective_permission_count'], 2)
        self.assertEqual(changes['removed_orphan_role_permission_rows'], 1)
        self.assertEqual(changes['removed_orphan_permission_data_rule_rows'], 1)
        self.assertEqual(self.source, before, 'Selection must never mutate acquired source rows')

    def test_removes_old_users_class_history_files_and_connections(self):
        selected, changes = launch.select_rows(self.source)
        self.assertEqual([row['id'] for row in selected['sys_user']], ['admin-account'])
        self.assertEqual([row['id'] for row in selected['sys_depart']], ['organization'])
        self.assertEqual(selected['sys_user'][0]['depart_ids'], '')
        self.assertEqual(changes['removed_admin_managed_department_references'], 2)
        self.assertTrue(changes['cleared_legacy_registration_department'])
        for table in ('teaching_course_dept', 'sys_user_depart', 'teaching_work', 'sys_file', 'sys_log', 'teaching_depart_day_log', 'teaching_scratch_assets', 'sys_data_source', 'jeecg_order_customer'):
            self.assertEqual(selected[table], [], table)
        configs = launch.keyed(selected['sys_config'], 'config_key')
        self.assertEqual(configs['allowReg']['config_value'], '0', 'Upgrade, not data selection, enables registration')
        self.assertEqual(configs['_defaultDepart']['config_value'], '')
        self.assertEqual(configs['_defaultRole']['config_value'], '')

    def test_keeps_public_shared_and_hidden_private_courses(self):
        selected, _ = launch.select_rows(self.source)
        self.assertEqual([(row['show_home'], row['is_shared']) for row in selected['teaching_course']], [(1, 1), (0, 0)])
        self.assertEqual(selected['teaching_course'][0]['sys_org_code'], 'ORG')
        self.assertEqual(selected['teaching_course'][0]['create_by'], selected['sys_user'][0]['username'])
        self.assertEqual(selected['teaching_course_unit'][0]['create_by'], selected['sys_user'][0]['username'])

    def test_removes_only_dictionary_items_with_missing_definitions(self):
        selected, changes = launch.select_rows(self.source)
        self.assertEqual([row['id'] for row in selected['sys_dict_item']], ['valid-item'])
        self.assertEqual(selected['sys_dict'], self.source['sys_dict'])
        self.assertEqual(changes['removed_orphan_dictionary_item_rows'], 1)
        selected['sys_dict_item'].append(self.source['sys_dict_item'][1])
        with self.assertRaises(ValueError): launch.validate_rows(selected)

    def test_restores_modern_home_config_without_copying_preview_business_data(self):
        selected, changes = launch.select_rows(self.source)
        source_config = launch.keyed(self.source['sys_config'], 'config_key')
        selected_config = launch.keyed(selected['sys_config'], 'config_key')
        self.assertTrue(changes['cleared_legacy_custom_homepage'])
        self.assertEqual(selected_config['_homeHtml']['config_value'], '')
        self.assertEqual(source_config['_homeHtml']['config_value'], '<h2>Legacy welcome page</h2>')
        self.assertTrue(changes['modern_homepage_restored'])
        self.assertEqual(changes['modern_homepage_visual_config_count'], 13)
        self.assertEqual(changes['cleared_legacy_visual_config_values'], 13)
        for key in launch.MODERN_HOME_CONFIG_KEYS:
            self.assertEqual(selected_config[key]['config_value'], '', key)
            self.assertEqual(selected_config[key]['id'], source_config[key]['id'], key)
            self.assertEqual(selected_config[key]['config_enabled'], source_config[key]['config_enabled'], key)
        self.assertEqual(selected_config['allowReg'], source_config['allowReg'])
        self.assertEqual([row['id'] for row in selected['teaching_course']], ['public-course', 'hidden-course'])
        selected_config['_homeHtml']['config_value'] = '<h2>Legacy welcome page</h2>'
        with self.assertRaises(ValueError): launch.validate_rows(selected)

    def test_default_front_navigation_does_not_change_backend_permissions(self):
        selected, changes = launch.select_rows(self.source)
        self.assertEqual(selected['teaching_menu'], [])
        self.assertEqual(changes['removed_legacy_front_navigation_rows'], 1)
        self.assertTrue(changes['default_front_navigation_enabled'])
        self.assertEqual(selected['sys_permission'], self.source['sys_permission'])
        self.assertEqual(launch.admin_permission_set(selected, 'admin-account'), launch.admin_permission_set(self.source, 'admin-account'))
        scopes, _ = launch.resource_scopes(selected)
        self.assertEqual(scopes['system_brand_assets'], [])
        selected['teaching_menu'] = self.source['teaching_menu']
        with self.assertRaises(ValueError): launch.validate_rows(selected)

    def test_refuses_ambiguous_or_missing_effective_administrator(self):
        for status in (1, 2):
            rows = copy.deepcopy(self.source)
            if status == 1:
                rows['sys_user'][1]['status'] = 1
            else:
                rows['sys_user'][0]['status'] = 2
            with self.subTest(status=status), self.assertRaises(ValueError):
                launch.select_rows(rows)

    def test_refuses_unknown_role_rule_registration_or_environment_config(self):
        mutations = [
            lambda r: r['sys_user_role'].append(dict(id='unknown-role-link', user_id='admin-account', role_id='missing-role')),
            lambda r: r['sys_role_permission'][0].update(data_rule_ids='missing-rule'),
            lambda r: r['sys_role'][2].update(role_code='student-missing'),
            lambda r: r['sys_config'][0].update(config_key='allowReg-missing'),
            lambda r: r['sys_config'][0].update(config_key='environmentPassword'),
            lambda r: r['sys_depart'][0].update(org_type='2'),
        ]
        for mutate in mutations:
            rows = copy.deepcopy(self.source)
            mutate(rows)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                launch.select_rows(rows)

    def test_refuses_access_changes_when_removing_historical_classes(self):
        for mutation in ('restriction', 'shared'):
            rows = copy.deepcopy(self.source)
            rows['teaching_course'][0].update({'depart_ids': 'old-class'} if mutation == 'restriction' else {'is_shared': 0})
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                launch.select_rows(rows)

    def test_manifest_policy_recheck_catches_extra_history_or_privilege(self):
        selected, _ = launch.select_rows(self.source)
        for mutation in ('old-user', 'history', 'class', 'student-role'):
            rows = copy.deepcopy(selected)
            if mutation == 'old-user': rows['sys_user'].append(self.source['sys_user'][2])
            elif mutation == 'history': rows['sys_log'] = self.source['sys_log']
            elif mutation == 'class': rows['sys_depart'].append(self.source['sys_depart'][1])
            else: rows['sys_user_role'][0]['role_id'] = 'role-student'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                launch.validate_rows(rows)

    def test_literals_roundtrip_quotes_binary_unicode_and_sql_looking_content(self):
        ddl = synthetic_ddl()
        rows, _ = launch.select_rows(self.source)
        payload = "'quote; \\ backslash\n中文🌟\r\t\0\b\x1a DOUBLE''quote; -- not a statement"
        rows['teaching_course'][0]['course_desc'] = payload
        emitted = launch.emit_seed(ddl, rows)
        _, roundtrip = fixture.parse_dump(emitted)
        self.assertEqual(roundtrip, rows)
        self.assertEqual(roundtrip['teaching_course'][0]['course_desc'], payload)
        self.assertNotIn('DROP TABLE', emitted)
        self.assertEqual(fixture.literal(fixture.lex(launch.literal(b'\x00\xff\x01'))[0]), b'\x00\xff\x01')


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / 'acquisition'
        self.source.mkdir(mode=0o700)
        (self.source / 'uploads').mkdir(mode=0o700)
        rows = synthetic_rows()
        seed = launch.emit_seed(synthetic_ddl(), rows)
        fixture.private_write(self.source / 'teachingopen.sql', seed)
        fixture.private_write(self.source / 'source-manifest.json', launch.json_bytes({'bytes': len(seed.encode()), 'sha256': hashlib.sha256(seed.encode()).hexdigest()}))
        self.asset_records = {}
        for name in ('course.png', 'unit.png', 'video.mp4', 'logo.png', 'banner.png', 'logo2.png', 'student.py'):
            data = ('synthetic ' + name).encode()
            fixture.private_write(self.source / 'uploads' / name, data)
            self.asset_records[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        fixture.private_write(self.source / 'assets-manifest.json', launch.json_bytes(self.asset_records))
        self.output = self.root / 'artifacts/launch'
        self.commit = 'a' * 40

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self):
        return launch.prepare(self.source, self.output, self.commit)

    def test_creates_source_bound_private_package_with_only_referenced_assets(self):
        originals = {name: fixture.sha256(self.source / name) for name in ('teachingopen.sql', 'source-manifest.json', 'assets-manifest.json')}
        result = self.prepare()
        self.assertTrue(result['verified'])
        self.assertFalse(result['database_imported'])
        self.assertEqual(result['accounts'], 1)
        self.assertEqual(result['tables'], 69)
        self.assertEqual(result['assets']['course_assets']['count'], 3)
        self.assertEqual(result['assets']['system_brand_assets']['count'], 0)
        self.assertEqual(result['assets']['count'], 3)
        for legacy in ('logo.png', 'banner.png', 'logo2.png'):
            self.assertFalse((self.output / 'uploads' / legacy).exists())
        self.assertFalse((self.output / 'uploads/student.py').exists())
        self.assertEqual(result['initial_state']['registered_students'], 0)
        self.assertEqual(result['initial_state']['registered_teachers'], 0)
        self.assertEqual({name: fixture.sha256(self.source / name) for name in originals}, originals)
        manifest = (self.output / 'manifest.json').read_text()
        for private in ('synthetic-admin', 'synthetic-password-hash', 'synthetic-salt', 'old-student', 'logo.png', 'course.png', 'private-student-asset'):
            self.assertNotIn(private, manifest)
        for path in self.output.rglob('*'):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700 if path.is_dir() else 0o600)

    def test_refuses_overwrite_and_source_tree_destination(self):
        self.prepare()
        before = fixture.sha256(self.output / 'mysql/seed.sql')
        with self.assertRaises(ValueError): self.prepare()
        self.assertEqual(fixture.sha256(self.output / 'mysql/seed.sql'), before)
        with self.assertRaises(ValueError): launch.prepare(self.source, self.source / 'nested', self.commit)

    def test_same_source_candidate_and_tool_generate_identical_package_bytes(self):
        self.prepare()
        other = self.root / 'artifacts/repeat'
        launch.prepare(self.source, other, self.commit)
        for name in ('manifest.json', 'mysql/seed.sql', 'assets-manifest.json'):
            self.assertEqual((self.output / name).read_bytes(), (other / name).read_bytes(), name)

    def test_refuses_changed_source_dump_or_asset_before_complete_manifest(self):
        (self.source / 'uploads/video.mp4').write_bytes(b'tampered')
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse((self.output / 'manifest.json').exists())
        with tempfile.TemporaryDirectory() as other:
            output = Path(other) / 'new-package'
            (self.source / 'teachingopen.sql').write_text('unreviewed SQL')
            with self.assertRaises(ValueError): launch.prepare(self.source, output, self.commit)
            self.assertFalse(output.exists())

    def test_refuses_source_symlink_and_encoded_resource_traversal(self):
        asset = self.source / 'uploads/video.mp4'
        asset.unlink()
        asset.symlink_to(self.source / 'uploads/student.py')
        with self.assertRaises(ValueError): self.prepare()
        selected, _ = launch.select_rows(synthetic_rows())
        for path in ('../student.py', '%252e%252e/student.py', '/absolute/student.py', 'a\\student.py'):
            selected['teaching_course_unit'][0]['course_video'] = path
            with self.subTest(path=path), self.assertRaises(ValueError): launch.resource_scopes(selected)

    def test_verifier_rejects_tampered_seed_asset_extra_file_and_permissions(self):
        self.prepare()
        for mutation in ('seed', 'asset', 'extra', 'permissions'):
            target = self.output / ('mysql/seed.sql' if mutation == 'seed' else 'uploads/video.mp4')
            original = target.read_bytes()
            if mutation in ('seed', 'asset'): target.write_bytes(original + b'tampered')
            elif mutation == 'extra': fixture.private_write(self.output / 'uploads/student.py', b'extra historical asset')
            else: target.chmod(0o644)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): launch.verify(self.output)
            if mutation in ('seed', 'asset'): target.write_bytes(original)
            elif mutation == 'extra': (self.output / 'uploads/student.py').unlink()
            else: target.chmod(0o600)
        self.assertTrue(launch.verify(self.output)['verified'])

    def test_refuses_linked_output_ancestor_and_invalid_commit(self):
        linked = self.root / 'linked'
        linked.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError): launch.prepare(self.source, linked / 'output', self.commit)
        with self.assertRaises(ValueError): launch.prepare(self.source, self.output, 'main')


if __name__ == '__main__':
    unittest.main()
