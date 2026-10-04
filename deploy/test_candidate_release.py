#!/usr/bin/env python3
"""Independent filesystem contract tests for candidate_release (no services).

Set CANDIDATE_TEST_SOURCE to the explicit integrated source checkout and
CANDIDATE_TEST_JAVA_HOME to a Java 8 JDK. Inputs use a small committed temporary
Git repository, a synthetic ZIP/JAR, and three synthetic dist files. Java is
used only to generate the five fixture password hashes; no JAR is executed.
"""
import configparser
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PASSWORD_UTIL = 'api/jeecg-boot-base-common/src/main/java/org/jeecg/common/util/PasswordUtil.java'
SOURCE_INPUTS = (
    'api/dev/extract-schema.py', 'api/dev/role_flow_fixture.py',
    'api/dev/local_recovery.py', 'api/dev/local_runtime.py',
    'api/dev/production_fixture.py', 'api/dev/scratch_cloud_recovery.py',
    'api/dev/FixturePassword.java', 'api/dev/application-localtest.properties.template',
    PASSWORD_UTIL, 'web/nginx/default.conf',
)
CANARY = 'DO_NOT_PACKAGE_ORIGINAL_SOURCE_INSERT_9c207eb5'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return result.stdout.strip()


def inventory(root):
    """Independent ordinary-file inventory, never follows links."""
    result = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(folder) / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError('test inventory refuses nonordinary input')
            if stat.S_ISREG(mode):
                result[path.relative_to(root).as_posix()] = {
                    'bytes': path.stat().st_size, 'sha256': digest(path)}
    return dict(sorted(result.items()))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


class CandidateReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module(ROOT / 'deploy/candidate_release.py', 'independent_candidate_release')
        cls.trusted_source = Path(os.environ.get('CANDIDATE_TEST_SOURCE', ROOT)).resolve()
        java_home = os.environ.get('CANDIDATE_TEST_JAVA_HOME') or os.environ.get('JAVA_HOME')
        if not java_home:
            raise RuntimeError('Set CANDIDATE_TEST_JAVA_HOME to a Java 8 JDK; this suite does not silently stub passwords')
        cls.java_home = Path(java_home).resolve()
        for name in SOURCE_INPUTS + ('api/db/teachingopen2.8.sql',):
            if not (cls.trusted_source / name).is_file():
                raise RuntimeError('CANDIDATE_TEST_SOURCE lacks integrated source input: ' + name)
        cls.suite_tmp = tempfile.TemporaryDirectory(prefix='teachingopen-candidate-tests-')
        # macOS temporary paths commonly begin with the /var symlink; use the
        # canonical ordinary ancestors so link tests target our actual aliases.
        cls.suite_root = Path(cls.suite_tmp.name).resolve()
        cls.base_source = cls.suite_root / 'source'
        cls.base_source.mkdir()
        for name in SOURCE_INPUTS:
            destination = cls.base_source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cls.trusted_source / name, destination)
        shutil.copytree(cls.trusted_source / 'api/dev/role-flow-assets',
                        cls.base_source / 'api/dev/role-flow-assets')
        extractor = load_module(cls.trusted_source / 'api/dev/extract-schema.py', 'independent_schema_extractor')
        schema = extractor.extract_schema((cls.trusted_source / 'api/db/teachingopen2.8.sql').read_text())
        sql = cls.base_source / 'api/db/teachingopen2.8.sql'
        sql.parent.mkdir(parents=True)
        sql.write_text(schema + "\nINSERT INTO `sys_user` (`id`) VALUES ('" + CANARY + "');\n")
        (cls.base_source / 'README.fixture').write_text('Only synthetic test inputs.\n')
        git(cls.base_source, 'init', '-q')
        git(cls.base_source, 'config', 'user.name', 'Candidate Filesystem Test')
        git(cls.base_source, 'config', 'user.email', 'candidate-test@example.invalid')
        git(cls.base_source, 'config', 'commit.gpgsign', 'false')
        git(cls.base_source, 'add', '.')
        git(cls.base_source, 'commit', '-qm', 'Synthetic candidate input fixture')
        dist = cls.base_source / 'web/dist'
        (dist / 'js').mkdir(parents=True)
        (dist / 'css').mkdir()
        (dist / 'index.html').write_text('<!doctype html><script src="/js/app.js"></script>\n')
        (dist / 'js/app.js').write_text('window.syntheticCandidate = true;\n')
        (dist / 'css/app.css').write_text('body { color: #123456; }\n')
        inputs = cls.suite_root / 'inputs'
        inputs.mkdir()
        cls.base_dist_manifest = inputs / 'dist-manifest.json'
        write_json(cls.base_dist_manifest, inventory(dist))
        cls.base_jar = inputs / 'synthetic.jar'
        with zipfile.ZipFile(cls.base_jar, 'w') as archive:
            archive.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\nSynthetic-Test: true\n\n')
            archive.writestr('synthetic.txt', 'This is not an executable application.\n')
        cls.base_bundle = cls.suite_root / 'baseline-bundle'
        cls.baseline_summary = cls.module.create_bundle(
            cls.base_source, cls.base_jar, digest(cls.base_jar),
            cls.base_dist_manifest, digest(cls.base_dist_manifest), cls.base_bundle,
            port=18190, java_home=cls.java_home)

    @classmethod
    def tearDownClass(cls):
        cls.suite_tmp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='case-', dir=self.suite_root)
        self.case_root = Path(self.tmp.name)
        self.source = self.case_root / 'source'
        shutil.copytree(self.base_source, self.source)
        inputs = self.case_root / 'inputs'
        inputs.mkdir()
        self.jar = inputs / 'synthetic.jar'
        shutil.copy2(self.base_jar, self.jar)
        self.dist_manifest = inputs / 'dist-manifest.json'
        shutil.copy2(self.base_dist_manifest, self.dist_manifest)
        self.output = self.case_root / 'created-bundle'

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, **overrides):
        args = dict(source=self.source, jar=self.jar, jar_sha256=digest(self.jar),
                    dist_manifest=self.dist_manifest,
                    dist_manifest_sha256=digest(self.dist_manifest), output=self.output,
                    port=18190, java_home=self.java_home)
        args.update(overrides)
        return self.module.create_bundle(**args)

    def bundle_copy(self):
        destination = self.case_root / 'bundle-copy'
        shutil.copytree(self.base_bundle, destination)
        return destination

    def rejected_create(self, **overrides):
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            self.create(**overrides)

    def rejected_verify(self, bundle):
        with self.assertRaises((ValueError, RuntimeError, OSError, KeyError)):
            self.module.verify_bundle(bundle)

    def rewrite_dist_manifest(self, mapping):
        write_json(self.dist_manifest, mapping)

    def edit_manifest(self, bundle, mutate):
        path = bundle / 'manifest.json'
        manifest = json.loads(path.read_text())
        mutate(manifest)
        write_json(path, manifest)

    def reseal_inventory(self, bundle):
        # A manifest is not an authenticated statement. These tests deliberately
        # rehash edited files to exercise the separate fixed semantic contract.
        files = {name: receipt for name, receipt in inventory(bundle).items()
                 if name != 'manifest.json' and not name.startswith('data/')}
        self.edit_manifest(bundle, lambda manifest: manifest.update(files=files))

    def replace_bundle_file(self, bundle, name, content):
        path = bundle / name
        mode = stat.S_IMODE(path.stat().st_mode)
        path.chmod(0o600)
        path.write_text(content)
        path.chmod(mode)

    def parse_fixture_rows(self, bundle):
        # Use the frozen source's real quote-aware SQL lexer, never execute SQL.
        _, fixture = self.module.load_source_helpers(self.source)

        def value(group):
            if len(group) == 1:
                return fixture.literal(group[0])
            # sql_value transports UTF-8 text with this one fixed expression.
            # Decode it locally; reject every other expression in the fixture.
            if (len(group) == 7 and group[:3] == [('word', 'CONVERT'), ('sym', '('), ('word', 'X')]
                    and group[3][0] == 'str'
                    and group[4:] == [('word', 'USING'), ('word', 'utf8mb4'), ('sym', ')')]):
                return bytes.fromhex(group[3][1]).decode('utf-8')
            raise ValueError('Unexpected SQL value expression in generated test fixture')

        rows = {}
        for tokens in fixture.statements(fixture.lex((bundle / 'init/02-fixtures.sql').read_text())):
            if tokens[:2] != [('word', 'INSERT'), ('word', 'INTO')]:
                continue
            end = tokens.index(('sym', ')'), 4)
            names = [group[0][1] for group in fixture.split_groups(tokens[4:end])]
            values = [value(group) for group in fixture.split_groups(tokens[end + 3:-1])]
            self.assertEqual(len(names), len(values))
            rows.setdefault(tokens[2][1], []).append(dict(zip(names, values)))
        return fixture, rows

    def test_verify_baseline(self):
        result = self.module.verify_bundle(self.base_bundle)
        self.assertIsInstance(result, dict)
        self.assertIs(result['services_started'], False)
        self.assertIs(result['runtime_data_checked'], False)
        self.assertEqual(result['manifest_sha256'], digest(self.base_bundle / 'manifest.json'))

    def test_create_copies_exact_bytes_and_preserves_source(self):
        before = {name: receipt for name, receipt in inventory(self.source).items()
                  if not name.startswith('.git/')}
        before_status = git(self.source, 'status', '--porcelain')
        self.create()
        self.assertEqual({name: receipt for name, receipt in inventory(self.source).items()
                          if not name.startswith('.git/')}, before)
        self.assertEqual(git(self.source, 'status', '--porcelain'), before_status)
        self.assertEqual((self.output / 'app/app.jar').read_bytes(), self.jar.read_bytes())
        self.assertEqual(inventory(self.output / 'web/dist'), inventory(self.source / 'web/dist'))
        self.assertEqual((self.output / 'web/nginx.conf').read_bytes(),
                         (self.source / 'web/nginx/default.conf').read_bytes())
        self.module.verify_bundle(self.output)

    def test_manifest_binds_source_and_explicit_inputs_without_claiming_jar_build(self):
        manifest = json.loads((self.base_bundle / 'manifest.json').read_text())
        self.assertEqual(manifest['source_commit'], git(self.base_source, 'rev-parse', 'HEAD'))
        self.assertEqual(manifest['artifact_inputs']['jar_sha256'], digest(self.base_jar))
        self.assertEqual(manifest['artifact_inputs']['dist_manifest_sha256'], digest(self.base_dist_manifest))
        self.assertEqual(set(manifest['helper_sha256']), set(self.module.HELPERS))
        for name, receipt in manifest['helper_sha256'].items():
            self.assertEqual(receipt, digest(self.base_source / name))
        self.assertNotIn('jar_build_commit', manifest)

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / 'sentinel.txt'
        sentinel.write_bytes(b'preserve user data\x00')
        before = inventory(self.output)
        self.rejected_create()
        self.assertEqual(inventory(self.output), before)

    def test_existing_output_file_is_never_overwritten(self):
        self.output.write_bytes(b'user file')
        self.rejected_create()
        self.assertEqual(self.output.read_bytes(), b'user file')

    def test_untracked_source_assets_are_preserved_and_excluded(self):
        (self.source / '.playwright-cli').mkdir()
        (self.source / '.playwright-cli/private-session.txt').write_text('synthetic browser state')
        (self.source / 'output').mkdir()
        (self.source / 'output/unrelated.txt').write_text('unrelated fixture output')
        self.create()
        self.assertTrue((self.source / '.playwright-cli/private-session.txt').exists())
        self.assertTrue((self.source / 'output/unrelated.txt').exists())
        self.assertFalse(any('.playwright-cli' in name or 'unrelated.txt' in name
                             for name in inventory(self.output)))

    def test_tracked_dirty_input_is_rejected(self):
        (self.source / 'README.fixture').write_text('uncommitted change\n')
        self.rejected_create()

    def test_staged_dirty_input_is_rejected(self):
        (self.source / 'README.fixture').write_text('staged uncommitted change\n')
        git(self.source, 'add', 'README.fixture')
        self.rejected_create()

    def test_jar_hash_mismatch_is_rejected(self):
        self.rejected_create(jar_sha256='0' * 64)

    def test_dist_manifest_hash_mismatch_is_rejected(self):
        self.rejected_create(dist_manifest_sha256='0' * 64)

    def test_missing_dist_file_is_rejected(self):
        (self.source / 'web/dist/js/app.js').unlink()
        self.rejected_create()

    def test_extra_dist_file_is_rejected(self):
        (self.source / 'web/dist/extra.txt').write_text('not in manifest')
        self.rejected_create()

    def test_changed_dist_file_is_rejected(self):
        (self.source / 'web/dist/js/app.js').write_text('different bytes')
        self.rejected_create()

    def test_wrong_dist_size_is_rejected(self):
        mapping = json.loads(self.dist_manifest.read_text())
        mapping['index.html']['bytes'] += 1
        self.rewrite_dist_manifest(mapping)
        self.rejected_create()

    def test_jar_symlink_is_rejected(self):
        link = self.case_root / 'jar-link'
        link.symlink_to(self.jar)
        self.rejected_create(jar=link)

    def test_dist_file_symlink_is_rejected(self):
        (self.source / 'web/dist/js/app.js').unlink()
        (self.source / 'web/dist/js/app.js').symlink_to(self.source / 'README.fixture')
        self.rejected_create()

    def test_dist_directory_symlink_is_rejected(self):
        shutil.rmtree(self.source / 'web/dist/js')
        (self.source / 'web/dist/js').symlink_to(self.source / 'web/dist/css', target_is_directory=True)
        self.rejected_create()

    def test_dist_root_symlink_is_rejected(self):
        dist = self.source / 'web/dist'
        dist.rename(self.source / 'web/dist-real')
        dist.symlink_to(self.source / 'web/dist-real', target_is_directory=True)
        self.rejected_create()

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO required')
    def test_dist_special_file_is_rejected(self):
        os.mkfifo(self.source / 'web/dist/pipe')
        self.rejected_create()

    def test_dist_manifest_symlink_is_rejected(self):
        link = self.case_root / 'manifest-link'
        link.symlink_to(self.dist_manifest)
        self.rejected_create(dist_manifest=link)

    def test_output_symlink_is_rejected(self):
        target = self.case_root / 'existing'
        target.mkdir()
        (target / 'sentinel').write_text('keep')
        self.output.symlink_to(target, target_is_directory=True)
        self.rejected_create()
        self.assertEqual((target / 'sentinel').read_text(), 'keep')

    def test_output_symlink_ancestor_is_rejected(self):
        (self.case_root / 'alias').symlink_to(self.case_root, target_is_directory=True)
        self.rejected_create(output=self.case_root / 'alias/new-output')

    def test_dist_manifest_parent_escape_is_rejected(self):
        mapping = json.loads(self.dist_manifest.read_text())
        mapping['../escape'] = {'bytes': 1, 'sha256': '0' * 64}
        self.rewrite_dist_manifest(mapping)
        self.rejected_create()

    def test_dist_manifest_absolute_path_is_rejected(self):
        mapping = json.loads(self.dist_manifest.read_text())
        mapping['/tmp/escape'] = {'bytes': 1, 'sha256': '0' * 64}
        self.rewrite_dist_manifest(mapping)
        self.rejected_create()

    def test_dist_manifest_empty_inventory_is_rejected(self):
        self.rewrite_dist_manifest({})
        self.rejected_create()

    def test_dist_manifest_duplicate_paths_are_rejected(self):
        mapping = json.loads(self.dist_manifest.read_text())
        entries = [json.dumps(name) + ':' + json.dumps(value) for name, value in mapping.items()]
        entries.append(json.dumps('index.html') + ':' + json.dumps(mapping['index.html']))
        self.dist_manifest.write_text('{' + ','.join(entries) + '}\n')
        self.rejected_create()

    def test_dist_manifest_unexpected_entry_fields_are_rejected(self):
        mapping = json.loads(self.dist_manifest.read_text())
        mapping['index.html']['trusted'] = True
        self.rewrite_dist_manifest(mapping)
        self.rejected_create()

    def test_dist_manifest_noncanonical_path_is_rejected(self):
        mapping = json.loads(self.dist_manifest.read_text())
        mapping['./index.html'] = mapping.pop('index.html')
        self.rewrite_dist_manifest(mapping)
        self.rejected_create()

    def test_dist_manifest_wrong_entry_types_are_rejected(self):
        for field, value in (('bytes', True), ('bytes', -1), ('bytes', '12'), ('sha256', 'bad')):
            with self.subTest(field=field, value=value):
                mapping = json.loads(self.base_dist_manifest.read_text())
                mapping['index.html'][field] = value
                self.rewrite_dist_manifest(mapping)
                self.rejected_create()

    def test_invalid_frontend_port_is_rejected(self):
        for port in (0, -1, 65536, '18190', True):
            with self.subTest(port=port):
                self.rejected_create(port=port)

    def test_source_without_git_is_rejected(self):
        shutil.rmtree(self.source / '.git')
        self.rejected_create()

    def test_untracked_helper_cannot_be_claimed_as_committed_source(self):
        name = 'api/dev/FixturePassword.java'
        git(self.source, 'rm', '--cached', name)
        git(self.source, 'commit', '-qm', 'Leave the helper untracked')
        self.assertTrue((self.source / name).exists())
        self.rejected_create()

    def test_copy_time_dist_mutation_leaves_no_complete_manifest(self):
        actual_write = self.module.write_file
        mutated = []

        def write_then_mutate(root, name, *args, **kwargs):
            result = actual_write(root, name, *args, **kwargs)
            if name == 'web/dist/js/app.js' and not mutated:
                (self.source / 'web/dist/js/app.js').write_text('changed during copy\n')
                mutated.append(True)
            return result

        with patch.object(self.module, 'write_file', side_effect=write_then_mutate):
            self.rejected_create()
        self.assertEqual(mutated, [True])
        self.assertTrue(self.output.is_dir())
        self.assertFalse((self.output / 'manifest.json').exists())

    def test_schema_has_69_create_statements_and_no_source_insert(self):
        schema = (self.base_bundle / 'init/01-schema.sql').read_text()
        _, fixture = self.module.load_source_helpers(self.source)
        statements = list(fixture.statements(fixture.lex(schema)))
        self.assertEqual(sum(tokens[:2] == [('word', 'CREATE'), ('word', 'TABLE')]
                             for tokens in statements), 69)
        self.assertFalse(any(tokens and tokens[0] == ('word', 'INSERT') for tokens in statements))
        for name in ('init/01-schema.sql', 'init/02-fixtures.sql'):
            self.assertNotIn(CANARY, (self.base_bundle / name).read_text())
        self.assertFalse((self.base_bundle / 'api/db/teachingopen2.8.sql').exists())

    def test_five_fixture_accounts_match_roles_relations_and_private_credentials(self):
        fixture, rows = self.parse_fixture_rows(self.base_bundle)
        users = {row['id']: row for row in rows['sys_user']}
        self.assertEqual(set(users), set(fixture.ACCOUNT_ROLES))
        credentials = json.loads((self.base_bundle / 'config/credentials.json').read_text())
        self.assertEqual(set(credentials), {'mysql_root_password', 'mysql_app_password',
                                           'redis_password', 'test_user_password'})
        self.assertEqual(len(set(credentials.values())), 4)
        salts = []
        for name, role in fixture.ACCOUNT_ROLES.items():
            self.assertEqual(users[name]['username'], name)
            self.assertRegex(users[name]['salt'], r'^[0-9a-f]{8}$')
            length = ((len(name.encode()) // 8) + 1) * 16
            self.assertRegex(users[name]['password'], r'^[0-9a-f]{' + str(length) + r'}$')
            self.assertNotEqual(users[name]['password'], credentials['test_user_password'])
            salts.append(users[name]['salt'])
            self.assertEqual(sum(row['user_id'] == name and row['role_id'] == 'fixture_role_' + role
                                 for row in rows['sys_user_role']), 1)
            expected_class = 'fixture_school' if role == 'admin' else 'fixture_class_' + name[-1]
            self.assertEqual(sum(row['user_id'] == name and row['dep_id'] == expected_class
                                 for row in rows['sys_user_depart']), 1)
        self.assertEqual(len(set(salts)), 5)
        classes = [row for row in rows['sys_depart'] if row['id'].startswith('fixture_class_')]
        self.assertEqual(len(classes), 2)
        self.assertTrue(all(str(row['org_category']) == '3' for row in classes))
        self.assertEqual(len(rows['sys_role']), 3)
        self.assertEqual(len(rows['teaching_course']), 3)

    def test_generated_asset_inventory_and_fixture_receipt_agree(self):
        _, fixture = self.module.load_source_helpers(self.source)
        assets = fixture.generated_assets()
        expected = {'role-flow/' + name: {'bytes': len(value),
                    'sha256': hashlib.sha256(value).hexdigest()} for name, value in assets.items()}
        for suffix in ('a', 'b'):
            value = ('synthetic work ' + suffix + '\n').encode()
            expected['fixture-work-' + suffix + '.txt'] = {
                'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
        observed = inventory(self.base_bundle / 'data/uploads')
        self.assertEqual(observed, dict(sorted(expected.items())))
        manifest = json.loads((self.base_bundle / 'manifest.json').read_text())
        self.assertEqual(manifest['fixtures']['initial_upload_files'], len(observed))
        self.assertEqual(manifest['fixture_counts'],
                         {'accounts': 5, 'classes': 2, 'courses': 3, 'tables': 69})

    def test_private_and_container_readable_permissions(self):
        bundle = self.base_bundle
        self.assertEqual(stat.S_IMODE(bundle.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((bundle / 'config').stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((bundle / 'config/credentials.json').stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((bundle / 'config/application-localtest.properties').stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((bundle / 'web/dist').stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((bundle / 'web/dist/js/app.js').stat().st_mode), 0o644)
        for name in ('init/01-schema.sql', 'init/02-fixtures.sql', 'config/mysql-root-password',
                     'config/mysql-app-password', 'config/redis.conf'):
            self.assertEqual(stat.S_IMODE((bundle / name).stat().st_mode), 0o444)

    def test_application_profile_is_exact_54_key_template_derivation(self):
        def properties(text):
            result = {}
            for line in text.splitlines():
                if not line.strip() or line.lstrip().startswith('#'):
                    continue
                key, separator, value = line.partition('=')
                self.assertEqual(separator, '=')
                self.assertNotIn(key, result)
                result[key] = value
            return result

        template = properties((self.source / 'api/dev/application-localtest.properties.template').read_text())
        rendered = properties((self.base_bundle / 'config/application-localtest.properties').read_text())
        credentials = json.loads((self.base_bundle / 'config/credentials.json').read_text())
        self.assertEqual(len(template), 54)
        self.assertEqual(set(rendered), set(template))
        substitutions = {'BACKEND_PORT': '8080', 'MYSQL_PORT': '3306', 'REDIS_PORT': '6379',
                         'FRONTEND_PORT': '18190', 'RUNTIME': '/app',
                         'MYSQL_APP_PASSWORD': credentials['mysql_app_password'],
                         'REDIS_PASSWORD': credentials['redis_password']}
        for key, value in template.items():
            for name, replacement in substitutions.items():
                value = value.replace('@' + name + '@', replacement)
            if key == 'server.address':
                value = '0.0.0.0'
            elif key == 'spring.redis.host':
                value = 'redis'
            elif key == 'jeecg.media.cookie-name':
                value = 'teaching_media_18190'
            elif key == 'spring.datasource.dynamic.datasource.master.url':
                value = value.replace('127.0.0.1:3306/', 'db:3306/')
            # Do not put secret values in assertion failure reports.
            self.assertTrue(rendered[key] == value, 'Unexpected derived property key: ' + key)
            self.assertFalse(re.search(r'@[A-Z_]+@', rendered[key]),
                             'Unresolved placeholder in property key: ' + key)

    def test_mysql_client_option_groups_do_not_break_mysqladmin(self):
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string((self.base_bundle / 'config/mysql-client.cnf').read_text())
        self.assertEqual(set(parser.sections()), {'client', 'mysql'})
        self.assertEqual(set(parser['client']), {'user', 'password', 'host', 'protocol'})
        self.assertEqual(parser['client']['user'], 'root')
        self.assertEqual(parser['client']['host'], '127.0.0.1')
        self.assertEqual(parser['client']['protocol'], 'tcp')
        credentials = json.loads((self.base_bundle / 'config/credentials.json').read_text())
        self.assertTrue(parser['client']['password'] == credentials['mysql_root_password'],
                        'MySQL client password must match the private owned-root credential')
        self.assertEqual(dict(parser['mysql']), {'local-infile': '0'})
        compose = json.loads((self.base_bundle / 'compose.json').read_text())
        health = compose['services']['db']['healthcheck']['test']
        self.assertEqual(health, ['CMD', 'mysqladmin',
                                 '--defaults-extra-file=/run/secrets/mysql-client.cnf', 'ping', '--silent'])

    def test_compose_has_loopback_web_port_internal_backend_and_web_only_ingress(self):
        compose = json.loads((self.base_bundle / 'compose.json').read_text())
        self.assertEqual(set(compose['services']), {'api', 'web', 'db', 'redis'})
        self.assertRegex(compose['name'], r'^teaching-candidate-[0-9a-f]{12}$')
        self.assertEqual(compose['networks'], {'candidate': {'internal': True},
                                               'ingress': {'driver': 'bridge', 'internal': False}})
        ports = [(name, port) for name, service in compose['services'].items()
                 for port in service.get('ports', [])]
        self.assertEqual(ports, [('web', {'target': 80, 'published': '18190',
                                        'host_ip': '127.0.0.1', 'protocol': 'tcp'})])
        for name, service in compose['services'].items():
            self.assertEqual(service['platform'], 'linux/arm64')
            self.assertRegex(service['image'], r'^[a-z0-9-]+@sha256:[0-9a-f]{64}$')
            self.assertEqual(service['networks'], ['candidate', 'ingress'] if name == 'web' else ['candidate'])
            for forbidden in ('network_mode', 'privileged', 'pid', 'container_name'):
                self.assertNotIn(forbidden, service)
            for mount in service.get('volumes', []):
                self.assertEqual(mount['type'], 'bind')
                source = mount['source']
                self.assertTrue(source.startswith('./'))
                self.assertNotIn('..', Path(source).parts)
                self.assertNotIn('docker.sock', source)
                self.assertNotIn('docker.sock', mount['target'])
                self.assertEqual(mount['bind'], {'create_host_path': False})
                if source[2:].startswith('data/'):
                    self.assertIn(source[2:], self.module.MUTABLE_DIRECTORIES)
                else:
                    self.assertIs(mount['read_only'], True)
        self.assertFalse(any('uploads' in mount['source']
                             for mount in compose['services']['web']['volumes']))

    def test_verify_rejects_missing_frozen_file(self):
        bundle = self.bundle_copy()
        (bundle / 'app/app.jar').unlink()
        self.rejected_verify(bundle)

    def test_verify_rejects_extra_frozen_file(self):
        bundle = self.bundle_copy()
        (bundle / 'extra.txt').write_text('extra')
        self.rejected_verify(bundle)

    def test_verify_rejects_changed_frozen_file(self):
        bundle = self.bundle_copy()
        (bundle / 'web/dist/js/app.js').write_text('different')
        self.rejected_verify(bundle)

    def test_verify_rejects_file_symlink(self):
        bundle = self.bundle_copy()
        path = bundle / 'web/dist/js/app.js'
        path.unlink()
        path.symlink_to(self.jar)
        self.rejected_verify(bundle)

    def test_verify_rejects_directory_symlink(self):
        bundle = self.bundle_copy()
        shutil.rmtree(bundle / 'web/dist/js')
        (bundle / 'web/dist/js').symlink_to(bundle / 'web/dist/css', target_is_directory=True)
        self.rejected_verify(bundle)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'POSIX FIFO required')
    def test_verify_rejects_special_file(self):
        bundle = self.bundle_copy()
        os.mkfifo(bundle / 'unexpected-pipe')
        self.rejected_verify(bundle)

    def test_verify_rejects_nonprivate_root(self):
        bundle = self.bundle_copy()
        bundle.chmod(0o755)
        self.rejected_verify(bundle)

    def test_verify_rejects_broadened_credentials_permissions(self):
        bundle = self.bundle_copy()
        (bundle / 'config/credentials.json').chmod(0o644)
        self.rejected_verify(bundle)

    def test_verify_rejects_unreadable_dist_permissions(self):
        bundle = self.bundle_copy()
        (bundle / 'web/dist/js/app.js').chmod(0o600)
        self.rejected_verify(bundle)

    def test_verify_rejects_wrong_manifest_kind_and_version(self):
        for key, value in (('kind', 'anything'), ('format', 999), ('format', True), ('format', 1.0)):
            with self.subTest(key=key):
                bundle = self.bundle_copy()
                self.edit_manifest(bundle, lambda manifest: manifest.update({key: value}))
                self.rejected_verify(bundle)
                shutil.rmtree(bundle)

    def test_verify_rejects_duplicate_manifest_keys(self):
        bundle = self.bundle_copy()
        path = bundle / 'manifest.json'
        data = path.read_text().rstrip()
        path.write_text(data[:-1] + ',"format":1}\n')
        self.rejected_verify(bundle)

    def test_verify_rejects_unknown_manifest_field(self):
        bundle = self.bundle_copy()
        self.edit_manifest(bundle, lambda manifest: manifest.update({'unexpected': True}))
        self.rejected_verify(bundle)

    def test_verify_rejects_manifest_path_escape(self):
        bundle = self.bundle_copy()
        self.edit_manifest(bundle, lambda manifest: manifest['files'].update(
            {'../outside': {'bytes': 1, 'sha256': '0' * 64}}))
        self.rejected_verify(bundle)

    def test_verify_rejects_missing_required_manifest_fields(self):
        for key in ('source_commit', 'generator_sha256', 'helper_sha256', 'artifact_inputs',
                    'fixture_counts', 'fixtures', 'images', 'platform'):
            with self.subTest(key=key):
                bundle = self.bundle_copy()
                self.edit_manifest(bundle, lambda manifest: manifest.pop(key))
                self.rejected_verify(bundle)
                shutil.rmtree(bundle)

    def test_verify_rejects_schema_removed_and_inventory_resealed(self):
        bundle = self.bundle_copy()
        (bundle / 'init/01-schema.sql').unlink()
        self.reseal_inventory(bundle)
        self.rejected_verify(bundle)

    def test_verify_rejects_fixture_removed_and_inventory_resealed(self):
        bundle = self.bundle_copy()
        (bundle / 'init/02-fixtures.sql').unlink()
        self.reseal_inventory(bundle)
        self.rejected_verify(bundle)

    def test_verify_rejects_added_external_config_even_when_resealed(self):
        bundle = self.bundle_copy()
        (bundle / 'config/application-prod.yml').write_text('synthetic: unsafe extra config\n')
        (bundle / 'config/application-prod.yml').chmod(0o600)
        self.reseal_inventory(bundle)
        self.rejected_verify(bundle)

    def test_verify_rejects_compose_host_bind_after_resealing(self):
        bundle = self.bundle_copy()
        compose = json.loads((bundle / 'compose.json').read_text())
        compose['services']['api']['volumes'].append(
            {'type': 'bind', 'source': '/', 'target': '/host', 'read_only': False})
        write_json(bundle / 'compose.json', compose)
        self.reseal_inventory(bundle)
        self.rejected_verify(bundle)

    def test_verify_rejects_compose_broad_web_publish_after_resealing(self):
        bundle = self.bundle_copy()
        compose = json.loads((bundle / 'compose.json').read_text())
        compose['services']['web']['ports'][0]['host_ip'] = '0.0.0.0'
        write_json(bundle / 'compose.json', compose)
        self.reseal_inventory(bundle)
        self.rejected_verify(bundle)

    def test_verify_rejects_mutable_image_tag_after_resealing(self):
        bundle = self.bundle_copy()
        compose = json.loads((bundle / 'compose.json').read_text())
        compose['services']['api']['image'] = 'eclipse-temurin:latest'
        write_json(bundle / 'compose.json', compose)
        self.reseal_inventory(bundle)
        self.rejected_verify(bundle)

    def test_verify_rejects_wrong_networks_after_resealing(self):
        for mutation in ('noninternal_backend', 'internal_ingress', 'api_on_ingress', 'web_without_ingress'):
            with self.subTest(mutation=mutation):
                bundle = self.bundle_copy()
                compose = json.loads((bundle / 'compose.json').read_text())
                if mutation == 'noninternal_backend':
                    compose['networks']['candidate']['internal'] = False
                elif mutation == 'internal_ingress':
                    compose['networks']['ingress']['internal'] = True
                elif mutation == 'api_on_ingress':
                    compose['services']['api']['networks'].append('ingress')
                else:
                    compose['services']['web']['networks'] = ['candidate']
                write_json(bundle / 'compose.json', compose)
                self.reseal_inventory(bundle)
                self.rejected_verify(bundle)
                shutil.rmtree(bundle)

    def test_verify_accepts_runtime_data_changes_and_does_not_walk_them(self):
        bundle = self.bundle_copy()
        (bundle / 'data/mysql/runtime-page').write_bytes(b'synthetic mutable database pages')
        (bundle / 'data/uploads/new-runtime-file').write_bytes(b'new synthetic upload')
        (bundle / 'data/mysql/link-that-must-not-be-read').symlink_to(self.case_root / 'missing')
        result = self.module.verify_bundle(bundle)
        self.assertIs(result['runtime_data_checked'], False)
        self.assertIs(result['services_started'], False)

    def test_verify_rejects_replaced_data_root_symlink(self):
        bundle = self.bundle_copy()
        shutil.rmtree(bundle / 'data')
        (bundle / 'data').symlink_to(self.case_root, target_is_directory=True)
        self.rejected_verify(bundle)

    def test_verify_rejects_missing_mutable_boundary_directory(self):
        bundle = self.bundle_copy()
        shutil.rmtree(bundle / 'data/redis')
        self.rejected_verify(bundle)

    def test_verify_rejects_extra_mutable_boundary_directory(self):
        bundle = self.bundle_copy()
        (bundle / 'data/unexpected').mkdir()
        self.rejected_verify(bundle)

    def test_verify_rejects_mutable_boundary_directory_symlink(self):
        bundle = self.bundle_copy()
        shutil.rmtree(bundle / 'data/redis')
        (bundle / 'data/redis').symlink_to(self.case_root, target_is_directory=True)
        self.rejected_verify(bundle)


if __name__ == '__main__':
    unittest.main(verbosity=2)
