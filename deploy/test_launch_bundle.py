"""Meaningful offline rejection checks; fixtures contain no real business data."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('launch_bundle', Path(__file__).with_name('launch_bundle.py'))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class PrivateBundleIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='launch-bundle-test-')
        self.root = Path(self.temporary.name).resolve()
        self.root.chmod(0o700)
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir(mode=0o700)
        self.write('app/app.jar', b'fake test artifact, never deployed')
        self.write('web/dist/index.html', '<!doctype html>offline unit fixture')
        for name in release.SUPPORT:
            self.write('tools/' + name, 'placeholder ' + name)
        for name in release.MIGRATIONS:
            self.write('migrations/' + Path(name).name, '-- offline test migration\n')
        self.write('migrations/Dockerfile.db.reference', '# offline test reference')
        self.write('web/nginx.conf', '# offline test proxy')
        self.write('RUNBOOK.md', 'placeholder deploy/LAUNCH_BUNDLE.md')
        self.write('config/application-launch.properties.template', 'placeholder deploy/application-launch.properties.template')
        self.write('initial-data/mysql/seed.sql', '-- empty synthetic test fixture')
        self.write('initial-data/uploads/fixture.txt', 'synthetic course resource')
        data = {'source_commit': 'c' * 40, 'counts': {'retained': {'admin': 1}},
                'assets': {'count': 1}}
        self.write('initial-data/manifest.json', release.paths.json_bytes(data))
        self.write('evidence/backend-build.log', 'BUILD SUCCESS\n')
        self.write('evidence/frontend-build.log', 'DONE Build complete.\n')
        inputs = {'api': {'api/pom.xml': {'bytes': 1, 'sha256': '0' * 64}},
                  'web': {'web/package.json': {'bytes': 1, 'sha256': '1' * 64}}}
        built = {'format': 1, 'kind': 'teachingopen-launch-build', 'complete': True,
                 'source_commit': 'b' * 40, 'compiled_inputs': inputs,
                 'compiled_input_sha256': {k: release.inventory_digest(v) for k, v in inputs.items()},
                 'jar': release.receipt(self.bundle / 'app/app.jar'),
                 'dist': release.paths.file_inventory(self.bundle / 'web/dist'),
                 'logs': {name: release.receipt(self.bundle / 'evidence' / name)
                          for name in ['backend-build.log', 'frontend-build.log']}}
        self.write('evidence/build.json', release.paths.json_bytes(built))
        copies = {name: 'tools/' + name for name in release.SUPPORT}
        copies.update({name: 'migrations/' + Path(name).name for name in release.MIGRATIONS})
        copies.update({'api/Dockerfile.db': 'migrations/Dockerfile.db.reference',
                       'web/nginx/default.conf': 'web/nginx.conf'})
        order = ['initial-data/mysql/seed.sql'] + ['migrations/' + Path(name).name for name in release.MIGRATIONS]
        self.manifest = {'format': 1, 'kind': 'teachingopen-private-launch-bundle', 'complete': True,
                         'source_commit': 'a' * 40, 'build_source_commit': 'b' * 40,
                         'initial_data_source_commit': 'c' * 40,
                         'jar': built['jar'], 'dist_files': 1,
                         'compiled_input_sha256': built['compiled_input_sha256'],
                         'dist_inventory_sha256': release.inventory_digest(built['dist']),
                         'build_receipt_sha256': release.paths.sha256(self.bundle / 'evidence/build.json'),
                         'initial_data_manifest_sha256': release.paths.sha256(self.bundle / 'initial-data/manifest.json'),
                         'initial_data_counts': data['counts']['retained'], 'course_assets': data['assets'],
                         'migration_order_new_database': order, 'migration_order_existing_database': order[1:],
                         'source_files': {name: release.receipt(self.bundle / copied) for name, copied in copies.items()},
                         'files': release.paths.file_inventory(self.bundle),
                         'services_started': False, 'runtime_data_checked': False,
                         'cloud_deployed': False, 'human_accepted': False}
        self.freeze()

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, name, value):
        release.write_file(self.bundle, name, value)

    def freeze(self):
        path = self.bundle / 'manifest.json'
        if path.exists():
            path.unlink()
        self.write('manifest.json', release.paths.json_bytes(self.manifest))

    def test_valid_offline_bundle(self):
        frozen = release.paths.sha256(self.bundle / 'manifest.json')
        result = release.verify_bundle(self.bundle, frozen)
        self.assertFalse(result['cloud_deployed'])
        self.assertFalse(result['source_checked'])

    def test_private_data_byte_change_is_rejected(self):
        (self.bundle / 'initial-data/uploads/fixture.txt').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            release.verify_bundle(self.bundle)

    def test_upgrade_sql_byte_change_is_rejected(self):
        (self.bundle / 'migrations/enable-phone-registration.sql').write_text('-- changed')
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            release.verify_bundle(self.bundle)

    def test_extra_file_is_rejected(self):
        self.write('unexpected-secret.txt', 'synthetic extra')
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            release.verify_bundle(self.bundle)

    def test_shared_permission_is_rejected(self):
        (self.bundle / 'initial-data/mysql/seed.sql').chmod(0o644)
        with self.assertRaisesRegex(ValueError, '0600'):
            release.verify_bundle(self.bundle)

    def test_symlink_is_rejected(self):
        (self.bundle / 'web/dist/index.html').unlink()
        (self.bundle / 'web/dist/index.html').symlink_to(self.bundle / 'RUNBOOK.md')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            release.verify_bundle(self.bundle)

    def test_frozen_manifest_rejects_rewritten_claim(self):
        frozen = release.paths.sha256(self.bundle / 'manifest.json')
        self.manifest['source_commit'] = 'd' * 40
        self.freeze()
        with self.assertRaisesRegex(ValueError, 'independently frozen'):
            release.verify_bundle(self.bundle, frozen)

    def test_runtime_claim_is_rejected(self):
        self.manifest['cloud_deployed'] = True
        self.freeze()
        with self.assertRaisesRegex(ValueError, 'cannot claim'):
            release.verify_bundle(self.bundle)

    def test_migration_order_is_not_trusted_from_manifest(self):
        self.manifest['migration_order_new_database'].reverse()
        self.freeze()
        with self.assertRaisesRegex(ValueError, 'Migration order'):
            release.verify_bundle(self.bundle)


if __name__ == '__main__':
    unittest.main()
