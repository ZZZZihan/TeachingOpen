import importlib.util
from datetime import datetime, timedelta, timezone
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('backup', Path(__file__).with_name('scheduled_backup.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class BackupTests(unittest.TestCase):
    def test_retention_keeps_week_and_latest_per_older_day(self):
        now = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
        items = sorted(Path((now - timedelta(hours=i * 6)).strftime('%Y%m%dT%H%M%SZ-00000000')) for i in range(160))
        removed = b.expired(items, now)
        keep = [x for x in items if x not in removed]
        self.assertEqual(len(keep), 52)
        self.assertTrue(all(x in keep for x in items[-29:]))
        self.assertEqual(len([x for x in keep if x.name.startswith('20260920')]), 1)

    def test_retention_preserves_two_after_long_outage(self):
        items = [Path('20260101T000000Z-00000000'), Path('20260102T000000Z-00000000')]
        self.assertEqual(b.expired(items, datetime(2026, 10, 9, tzinfo=timezone.utc)), [])

    def test_private_path_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            f = root / 'file'; f.write_text('private'); f.chmod(0o644)
            with self.assertRaises(ValueError): b.ordinary(f, private=True)
            f.chmod(0o600)
            self.assertEqual(b.ordinary(f, private=True), f)
            link = root / 'link'; link.symlink_to(f)
            with self.assertRaises(ValueError): b.ordinary(link)

    def test_incomplete_and_unrelated_not_pruned(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for name, value in [('20261009T000000Z-00000000', {'kind': b.KIND, 'status': 'complete'}),
                                ('20261009T010000Z-00000000', {'kind': b.KIND, 'status': 'partial'}),
                                ('20261009T020000Z-00000000', {'kind': 'other', 'status': 'complete'})]:
                d = root / name; d.mkdir(); (d / 'receipt.json').write_text(json.dumps(value))
            self.assertEqual([x.name for x in b.snapshots(root)], ['20261009T000000Z-00000000'])

    def make_snapshot(self, root):
        snapshot = root / '20261009T000000Z-00000000'; snapshot.mkdir(mode=0o700)
        with gzip.open(snapshot / 'database.sql.gz', 'wb') as out: out.write(b'CREATE TABLE sample(id int);')
        receipt = snapshot / 'receipt.json'
        receipt.write_text(json.dumps({'kind': b.KIND, 'database_sha256': b.digest(snapshot / 'database.sql.gz')}))
        receipt.chmod(0o600)
        return snapshot

    def test_restore_checks_checksum_before_sql(self):
        with tempfile.TemporaryDirectory() as raw:
            snapshot = self.make_snapshot(Path(raw).resolve())
            (snapshot / 'database.sql.gz').write_bytes(b'bad')
            with patch.object(b, 'mysql') as sql:
                with self.assertRaises(ValueError): b.restore_check({}, snapshot)
                sql.assert_not_called()

    def test_restore_uses_restricted_user_and_drops_only_created_database(self):
        with tempfile.TemporaryDirectory() as raw:
            snapshot = self.make_snapshot(Path(raw).resolve()); queries = []; commands = []
            def sql(c, q, *args): queries.append(q); return ''
            def run(cmd, **kwargs):
                commands.append(cmd)
                options = Path(cmd[1].split('=', 1)[1]).read_text()
                self.assertIn('user=to_verify_', options)
                self.assertNotIn('user=root', options)
                return b''
            c = {'mysql':'mysql', 'mysql_socket':'/private/mysql.sock'}
            with patch.object(b, 'mysql', side_effect=sql), patch.object(b, 'run', side_effect=run), patch.object(b, 'health', return_value={}):
                result = b.restore_check(c, snapshot)
            self.assertEqual(result['status'], 'passed')
            self.assertTrue(commands[0][-1].startswith('teachingopen_restore_'))
            self.assertIn('GRANT ALL ON `teachingopen_restore_', queries[2])
            self.assertIn('DROP DATABASE `teachingopen_restore_', queries[-2])
            self.assertIn('DROP USER', queries[-1])

    def test_failed_restore_still_cleans_owned_namespace(self):
        with tempfile.TemporaryDirectory() as raw:
            snapshot = self.make_snapshot(Path(raw).resolve()); queries = []
            with patch.object(b, 'mysql', side_effect=lambda c, q, *a: queries.append(q)), patch.object(b, 'run', side_effect=RuntimeError('failed')):
                with self.assertRaises(RuntimeError): b.restore_check({'mysql':'mysql','mysql_socket':'/sock'}, snapshot)
            self.assertTrue(queries[-2].startswith('DROP DATABASE'))
            self.assertTrue(queries[-1].startswith('DROP USER'))

    def test_failed_database_create_does_not_drop_existing_namespace(self):
        with tempfile.TemporaryDirectory() as raw:
            snapshot = self.make_snapshot(Path(raw).resolve())
            with patch.object(b, 'mysql', side_effect=RuntimeError('exists')) as sql:
                with self.assertRaises(RuntimeError): b.restore_check({}, snapshot)
                self.assertEqual(sql.call_count, 1)

    def test_non_innodb_fails_before_dump(self):
        with tempfile.TemporaryDirectory() as raw, patch.object(b, 'mysql', return_value='1'), patch.object(b.subprocess, 'run') as process:
            with self.assertRaises(RuntimeError): b.backup({'database':'teachingopen'}, Path(raw))
            process.assert_not_called()

    def test_export_failure_does_not_publish_or_prune(self):
        with tempfile.TemporaryDirectory() as raw, patch.object(b, 'mysql', return_value='0'), patch.object(b.subprocess, 'run') as process:
            process.return_value.returncode = 1
            root = Path(raw)
            c = {'database':'teachingopen','mysql_options':'/private/options','mysqldump':'mysqldump','minimum_free_bytes':0}
            with self.assertRaises(RuntimeError): b.backup(c, root)
            self.assertFalse((root / 'latest.json').exists())
            self.assertEqual(b.snapshots(root), [])

    def test_missing_profile_relationship_fails_health(self):
        def sql(c, query, db):
            return '1' if query.startswith('SELECT COUNT(*) FROM teaching_registration_profile p LEFT JOIN sys_user u') else '0'
        with patch.object(b, 'mysql', side_effect=sql):
            with self.assertRaisesRegex(RuntimeError, 'profiles_have_users'): b.health({}, 'restored')

    def test_database_identifier_rejected(self):
        with self.assertRaises(ValueError):
            b.mysql({'mysql':'mysql','mysql_options':'/private/options'}, 'SELECT 1', 'db;DROP')

    def test_complete_backup_with_configs_is_discoverable_and_restorable(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve(); out = root / 'backups'; out.mkdir()
            uploads = root / 'uploads'; uploads.mkdir(); (uploads / 'lesson.txt').write_text('lesson')
            app = root / 'app'; app.write_text('application')
            conf = root / 'nginx.conf'; conf.write_text('configuration')
            c = {'database':'teachingopen','mysql_options':'/private/options','mysqldump':'mysqldump',
                 'minimum_free_bytes':0,'uploads':str(uploads),'application':str(app),
                 'configuration_files':{'nginx.conf':str(conf)}}
            def execute(cmd, **kwargs):
                if cmd[0] == 'mysqldump':
                    kwargs['stdout'].write(b'CREATE TABLE example(id int);')
                    return type('Result', (), {'returncode':0})()
                raise AssertionError(cmd)
            def rsync(cmd):
                b.shutil.copyfile(uploads / 'lesson.txt', Path(cmd[-1]) / 'lesson.txt')
                return b''
            with patch.object(b, 'mysql', return_value='0'), patch.object(b.subprocess, 'run', side_effect=execute), patch.object(b, 'run', side_effect=rsync), patch.object(b, 'restore_check', return_value={'status':'passed'}):
                result = b.backup(c, out)
                self.assertRegex(result['snapshot'], b.NAME)
                self.assertEqual(len(b.snapshots(out)), 1)
                self.assertEqual(json.loads((out / 'latest.json').read_text())['snapshot'], result['snapshot'])
                self.assertEqual(b.verify(c, out)['status'], 'passed')


if __name__ == '__main__':
    unittest.main()
