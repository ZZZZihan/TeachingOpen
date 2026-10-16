"""Behavior checks for conservative CI environment reuse; no services/network."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import reuse_environment as environment


ROOT = Path(__file__).resolve().parents[1]


class EnvironmentContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in (*environment.POMS, '.github/workflows/ci.yml', 'web/.nvmrc'):
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)

    def edit(self, relative, old, new):
        path = self.root / relative
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1))

    def verify(self):
        environment.verify_environment_contract(self.root)

    def test_current_pinned_environment_is_eligible(self):
        self.verify()

    def test_fixed_release_qualifier_and_snapshot_publication_url_are_eligible(self):
        self.assertIn('<version>2.1.3.RELEASE</version>', (self.root / 'api/pom.xml').read_text())
        self.assertIn('/snapshots', (self.root / 'api/pom.xml').read_text())
        self.verify()

    def test_floating_runtime_action_runner_and_container_are_rejected(self):
        cases = (
            ('python-version: \'3.12.15\'', 'python-version: \'3.12\''),
            ('java-version: \'8.0.504+1\'', 'java-version: \'8\''),
            ('npm@11.19.0', 'npm@latest'),
            ('runs-on: ubuntu-22.04', 'runs-on: ubuntu-latest'),
            (environment.SERVICE_IMAGES['mysql'], 'mysql:8.0'),
            (environment.SERVICE_IMAGES['redis'], 'redis:7.2'),
            ('actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1', 'actions/checkout@v7'),
            ('nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94',
             'nginx:stable'),
        )
        original = (self.root / '.github/workflows/ci.yml').read_text()
        for old, new in cases:
            with self.subTest(value=new):
                (self.root / '.github/workflows/ci.yml').write_text(original)
                self.edit('.github/workflows/ci.yml', old, new)
                with self.assertRaises(ValueError):
                    self.verify()

    def test_node_version_file_and_unknown_runtime_inputs_are_rejected(self):
        self.edit('web/.nvmrc', '26.7.0', '26')
        with self.assertRaises(ValueError):
            self.verify()
        (self.root / 'web/.nvmrc').write_text('26.7.0\n')
        self.edit('.github/workflows/ci.yml', 'node-version-file: web/.nvmrc',
                  "node-version-file: web/.nvmrc\n          node-version: '26.7.0'")
        with self.assertRaises(ValueError):
            self.verify()

    def test_remote_repository_variables_and_dynamic_runner_disable_reuse(self):
        self.edit('.github/workflows/ci.yml', 'runs-on: ubuntu-22.04',
                  'runs-on: ${{ vars.CI_RUNNER }}')
        with self.assertRaises(ValueError):
            self.verify()

    def test_duplicate_jobs_or_runtime_versions_are_rejected(self):
        self.edit('.github/workflows/ci.yml', "python-version: '3.12.15'",
                  "python-version: '3.12.15'\n          python-version: '3.12'")
        with self.assertRaises(ValueError):
            self.verify()

    def test_unknown_action_is_rejected_even_with_an_immutable_action_sha(self):
        path = self.root / '.github/workflows/ci.yml'
        original = path.read_text()
        for declaration in ('uses: actions/setup-go@' + '1' * 40,
                            '"uses": actions/setup-go@' + '1' * 40,
                            '{uses: actions/setup-go@' + '1' * 40 + '}'):
            with self.subTest(declaration=declaration):
                path.write_text(original)
                self.edit('.github/workflows/ci.yml', '    steps:',
                          '    steps:\n      - ' + declaration
                          + '\n        with:\n          go-version: stable')
                with self.assertRaises(ValueError):
                    self.verify()

    def test_mutable_dependency_versions_and_ranges_are_rejected(self):
        original = (self.root / 'api/jeecg-boot-module-system/pom.xml').read_text()
        for version in ('1.0-SNAPSHOT', 'LATEST', 'RELEASE', '[1.0,2.0)', '(,2.0]', '${env.VERSION}'):
            with self.subTest(version=version):
                (self.root / 'api/jeecg-boot-module-system/pom.xml').write_text(original)
                self.edit('api/jeecg-boot-module-system/pom.xml', '<version>2.2.224</version>',
                          '<version>' + version + '</version>')
                with self.assertRaises(ValueError):
                    self.verify()

    def test_mutable_parent_and_plugin_versions_are_rejected(self):
        self.edit('api/pom.xml', '<version>2.1.3.RELEASE</version>', '<version>RELEASE</version>')
        with self.assertRaises(ValueError):
            self.verify()
        self.edit('api/pom.xml', '<version>RELEASE</version>', '<version>2.1.3.RELEASE</version>')
        self.edit('api/jeecg-boot-module-system/pom.xml',
                  '<artifactId>spring-boot-maven-plugin</artifactId>',
                  '<artifactId>spring-boot-maven-plugin</artifactId><version>LATEST</version>')
        with self.assertRaises(ValueError):
            self.verify()

    def test_nested_properties_resolve_and_mutable_or_cyclic_versions_are_rejected(self):
        self.edit('api/pom.xml', '<commons.version>2.6</commons.version>',
                  '<commons.version>${ci.commons.version}</commons.version>'
                  '<ci.commons.version>2.6</ci.commons.version>')
        self.verify()
        self.edit('api/pom.xml', '<ci.commons.version>2.6</ci.commons.version>',
                  '<ci.commons.version>2.6-SNAPSHOT</ci.commons.version>')
        with self.assertRaises(ValueError):
            self.verify()
        self.edit('api/pom.xml', '<ci.commons.version>2.6-SNAPSHOT</ci.commons.version>',
                  '<ci.commons.version>${commons.version}</ci.commons.version>')
        with self.assertRaises(ValueError):
            self.verify()

    def test_unknown_unversioned_plugins_and_dependencies_are_rejected(self):
        relative = 'api/jeecg-boot-module-system/pom.xml'
        original = (self.root / relative).read_text()
        additions = (
            ('<plugins>', '<plugins><plugin><artifactId>unknown-plugin</artifactId></plugin>'),
            ('<dependencies>', '<dependencies><dependency><groupId>example</groupId>'
             '<artifactId>unknown-library</artifactId></dependency>'),
            ('<dependencies>', '<dependencies><dependency><groupId>example</groupId>'
             '<artifactId>lombok</artifactId></dependency>'),
        )
        for old, new in additions:
            with self.subTest(declaration=new):
                (self.root / relative).write_text(original)
                self.edit(relative, old, new)
                with self.assertRaises(ValueError):
                    self.verify()
        (self.root / relative).write_text(original)
        self.edit(relative, '<plugins>',
                  '<plugins><plugin><artifactId>unknown-plugin</artifactId>'
                  '<version>1.2.3</version></plugin>')
        self.verify()

    def test_managed_versions_require_the_known_parent_and_fixed_overrides(self):
        self.edit('api/pom.xml', '<version>2.1.3.RELEASE</version>', '<version>2.1.4.RELEASE</version>')
        with self.assertRaises(ValueError):
            self.verify()
        self.edit('api/pom.xml', '<version>2.1.4.RELEASE</version>', '<version>2.1.3.RELEASE</version>')
        self.edit('api/pom.xml', '<java.version>1.8</java.version>',
                  '<java.version>1.8</java.version><lombok.version>LATEST</lombok.version>')
        with self.assertRaises(ValueError):
            self.verify()

    def test_empty_module_declaration_is_a_rejected_contract(self):
        self.edit('api/pom.xml', '<module>jeecg-boot-base-common</module>', '<module/>')
        with self.assertRaises(ValueError):
            self.verify()

    def test_child_inherits_fixed_properties_but_cannot_override_them_to_floating(self):
        self.edit('api/jeecg-boot-module-system/pom.xml', '<version>2.2.224</version>',
                  '<version>${commons.version}</version>')
        self.verify()
        self.edit('api/jeecg-boot-module-system/pom.xml', '<dependencies>',
                  '<properties><commons.version>LATEST</commons.version></properties><dependencies>')
        with self.assertRaises(ValueError):
            self.verify()

    def test_unknown_module_profiles_and_xml_entities_disable_reuse(self):
        new = self.root / 'api/new-module/pom.xml'
        new.parent.mkdir()
        new.write_text('<project/>')
        with self.assertRaises(ValueError):
            self.verify()
        new.unlink()
        self.edit('api/pom.xml', '<packaging>pom</packaging>',
                  '<packaging>pom</packaging><profiles><profile><id>ci</id></profile></profiles>')
        with self.assertRaises(ValueError):
            self.verify()
        self.edit('api/pom.xml', '<profiles><profile><id>ci</id></profile></profiles>', '')
        self.edit('api/pom.xml', '<modelVersion>', '<!DOCTYPE project><modelVersion>')
        with self.assertRaises(ValueError):
            self.verify()

    def test_maven_command_overrides_disable_reuse(self):
        (self.root / 'api/.mvn').mkdir()
        (self.root / 'api/.mvn/maven.config').write_text('-Dcommons.version=LATEST\n')
        with self.assertRaises(ValueError):
            self.verify()


class InstalledPackageTests(unittest.TestCase):
    def digest(self, output):
        result = subprocess.CompletedProcess([], 0, output, '')
        with patch.object(environment.subprocess, 'run', return_value=result) as run:
            digest = environment.installed_packages_digest()
        self.assertEqual(run.call_args.args[0], ['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\n'])
        self.assertTrue(run.call_args.kwargs['check'])
        return digest

    def test_canonical_package_order_and_all_dependency_versions_are_fingerprinted(self):
        expected = hashlib.sha256(b'libc6:amd64\t2.35-1\nredis-tools\t7.0.1\n').hexdigest()
        self.assertEqual(self.digest('redis-tools\t7.0.1\nlibc6:amd64\t2.35-1\n'), expected)
        self.assertEqual(self.digest('libc6:amd64\t2.35-1\nredis-tools\t7.0.1\n'), expected)
        self.assertNotEqual(self.digest('libc6:amd64\t2.35-2\nredis-tools\t7.0.1\n'), expected)

    def test_empty_malformed_or_duplicate_package_inventory_is_rejected(self):
        for value in ('', 'package\n', 'package\t\n', '\tversion\n', 'p\t1\np\t2\n'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.digest(value)


if __name__ == '__main__':
    unittest.main()
