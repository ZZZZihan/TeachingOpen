"""Offline safety regressions; do not start services, log in or write real SQL."""
import base64
from email.message import Message
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('teaching_journey_fixture',
    Path(__file__).with_name('teaching-journey-fixture.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class RequestBoundaryTests(unittest.TestCase):
    def headers(self, hosts, origins=()):
        headers = Message()
        for host in hosts:
            headers['Host'] = host
        for origin in origins:
            headers['Origin'] = origin
        return headers

    def test_only_matching_loopback_host_and_origin(self):
        for host in ('127.0.0.1:18192', 'localhost:18192'):
            self.assertTrue(fixture.allowed_request(self.headers([host]), 18192))
            self.assertTrue(fixture.allowed_request(self.headers([host], ['http://' + host]), 18192))
        for hosts, origins in (([], []), (['evil.test:18192'], []),
                (['127.0.0.1:18191'], []), (['localhost:18192', 'localhost:18192'], []),
                (['localhost:18192'], ['https://localhost:18192']),
                (['localhost:18192'], ['http://evil.test:18192']),
                (['localhost:18192'], ['http://localhost:18192', 'http://localhost:18192'])):
            with self.subTest(hosts=hosts, origins=origins):
                self.assertFalse(fixture.allowed_request(self.headers(hosts, origins), 18192))

    def test_material_rejects_unknown_actors_and_unbounded_nonces_before_io(self):
        for actor, nonce in (('admin', 'valid'), ('teacher_a', '../bad'),
                ('student_a', 'x' * 101), ('production_user', 'valid')):
            with self.subTest(actor=actor, nonce=nonce):
                with self.assertRaises(ValueError):
                    fixture.material(None, actor, nonce)

    def test_material_uses_actual_captcha_value_without_logging_in(self):
        class Api:
            credentials = {'test_user_password': 'offline-test-value'}
            requests = []
            generated = False
            nonce = 'valid-ui-nonce'
            code = 'a7cd'
            key = hashlib.md5((code + nonce).encode()).hexdigest()

            def cache(self, *args):
                if args[0] == 'KEYS':
                    return self.key if self.generated else ''
                if args == ('GET', self.key):
                    return json.dumps(self.code)
                raise AssertionError('Unexpected cache access')

            def request(self, method, route):
                self.requests.append((method, route))
                self.generated = True
                return 200, {'success': True}, 'application/json'

        api = Api()
        value = fixture.material(api, 'student_b', api.nonce)
        self.assertEqual(value['username'], 'fixture_student_b')
        self.assertEqual(value['captcha'], api.code)
        self.assertEqual(api.requests, [('GET', '/sys/randomImage/' + api.nonce)])
        fixture.material(api, 'teacher_b', api.nonce)
        self.assertEqual(len(api.requests), 1)  # Keep the existing UI CAPTCHA.


class RecoveryBoundaryTests(unittest.TestCase):
    def test_restore_is_one_transaction_for_only_reviewed_tables(self):
        model = fixture.reviewed_model()
        snapshot = {'tables': {table: {'columns': list(model[table]), 'rows': []}
                                for table in fixture.TABLES}}
        snapshot['tables']['teaching_work_correct']['rows'] = [[
            None if name != 'comment' else "学生's反馈\n".encode().hex()
            for name in model['teaching_work_correct']]]
        query = fixture.restore_sql(snapshot, model)
        self.assertEqual(query.count('START TRANSACTION;'), 1)
        self.assertEqual(query.count('COMMIT;'), 1)
        self.assertEqual(query.count('DELETE FROM teachingopen_dev.'), len(fixture.TABLES))
        self.assertNotIn('sys_log', query)
        self.assertNotIn('teaching_course`', query)
        self.assertIn('`sys_data_log`', query)
        self.assertIn('`sys_local_file_reference`', query)
        self.assertNotIn("学生's反馈", query)

    def test_restore_rejects_column_and_value_injection(self):
        model = fixture.reviewed_model()
        snapshot = {'tables': {table: {'columns': list(model[table]), 'rows': []}
                                for table in fixture.TABLES}}
        snapshot['tables']['sys_user']['columns'][0] = 'id); DROP TABLE sys_user;'
        with self.assertRaises(RuntimeError):
            fixture.restore_sql(snapshot, model)
        snapshot['tables']['sys_user']['columns'] = list(model['sys_user'])
        snapshot['tables']['sys_user']['rows'] = [['0xabc);COMMIT'] * len(model['sys_user'])]
        with self.assertRaises(RuntimeError):
            fixture.restore_sql(snapshot, model)

    def test_only_new_uploads_are_selected_and_baseline_mutation_blocks_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            (runtime / 'uploads').mkdir()
            original = runtime / 'uploads/original.txt'
            original.write_bytes(b'original bytes\n')
            baseline = fixture.file_inventory(runtime / 'uploads')
            (runtime / 'uploads/new.txt').write_bytes(b'new upload')
            self.assertEqual(fixture.new_uploads(runtime, baseline), ['new.txt'])
            self.assertEqual(original.read_bytes(), b'original bytes\n')
            original.write_bytes(b'changed original')
            with self.assertRaises(RuntimeError):
                fixture.new_uploads(runtime, baseline)

    def test_upload_symlink_is_rejected_before_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            (runtime / 'uploads').mkdir()
            (runtime / 'outside.txt').write_bytes(b'keep this file')
            (runtime / 'uploads/link.txt').symlink_to(runtime / 'outside.txt')
            with self.assertRaises(ValueError):
                fixture.new_uploads(runtime, {})
            self.assertEqual((runtime / 'outside.txt').read_bytes(), b'keep this file')

    def test_snapshot_digest_detects_changes_and_allows_no_foreign_table(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            root = runtime / 'config' / fixture.BACKUP_NAME
            root.mkdir(parents=True, mode=0o700)
            payload = {'format': fixture.FORMAT, 'kind': fixture.KIND,
                'runtime': str(runtime), 'ports': fixture.EXPECTED_PORTS,
                'tables': dict.fromkeys(fixture.TABLES, {})}
            fixture.private_write(root / 'snapshot.json', json.dumps(payload))
            fixture.private_write(root / 'snapshot.sha256', fixture.sha256(root / 'snapshot.json'))
            self.assertEqual(fixture.load_snapshot(runtime), payload)
            with (root / 'snapshot.json').open('a') as handle:
                handle.write(' ')
            with self.assertRaises(RuntimeError):
                fixture.load_snapshot(runtime)
            payload['tables']['sys_log'] = {}
            (root / 'snapshot.json').write_text(json.dumps(payload))
            (root / 'snapshot.sha256').write_text(fixture.sha256(root / 'snapshot.json'))
            with self.assertRaises(RuntimeError):
                fixture.load_snapshot(runtime)

    def test_cache_restoration_preserves_binary_dump_and_ignores_expired_keys(self):
        key = 'departLog:addiWorkAssign:fixture_class_a'
        expired = 'sys:cache:dict::sex'
        saved = {key: {'dump': base64.b64encode(b'\x00\xff\r\n').decode(), 'expires_ms': None},
                 expired: {'dump': base64.b64encode(b'x').decode(), 'expires_ms': int(time.time() * 1000) - 1}}
        api = type('Api', (), {'redis': ['offline-redis'], 'redis_env': {}})()
        response = type('Result', (), {'stdout': b'errors: 0, replies: 3\n'})()
        with patch.object(fixture, 'cache_keys', return_value=[]), patch.object(fixture.subprocess, 'run', return_value=response) as run:
            fixture.restore_cache(api, saved)
        wire = run.call_args.kwargs['input']
        self.assertIn(fixture.redis_resp(('RESTORE', key, 0, b'\x00\xff\r\n')), wire)
        self.assertNotIn(b'RESTORE\r\n$20\r\nsys:cache:dict::sex', wire)
        self.assertEqual(wire.count(b'RESTORE'), 1)
        saved['production-key'] = saved[key]
        with self.assertRaises(RuntimeError):
            fixture.restore_cache(api, saved)

    def test_cache_scope_matches_backend_department_cache_names(self):
        source = Path(__file__).resolve().parents[1] / 'jeecg-boot-base-common/src/main/java/org/jeecg/common/constant/CacheConstant.java'
        constants = source.read_text()
        for prefix in ('sys:cache:depart:alldata', 'sys:cache:depart:allids', 'sys:cache:dict', 'sys:cache:dictTable'):
            self.assertIn('"' + prefix + '"', constants)
            self.assertTrue(fixture.cache_scope(prefix + '::SimpleKey []'))
        self.assertTrue(fixture.cache_scope('sys:cache:user::fixture_student_a'))
        self.assertFalse(fixture.cache_scope('sys:cache:user::real_user'))
        self.assertFalse(fixture.cache_scope('sys:cache:departids::SimpleKey []'))
        self.assertFalse(fixture.cache_scope('scratch:cloud:unrelated'))

    def test_ui_preparation_never_contains_business_results(self):
        records = fixture.ui_records()
        self.assertEqual(set(records), {'sys_permission', 'sys_role_permission', 'sys_dict', 'sys_dict_item'})
        self.assertEqual(len(records['sys_permission']), 5)
        self.assertFalse(set(records) & {'teaching_additional_work', 'teaching_work', 'teaching_work_correct'})
        fixture.validate_records(fixture.reviewed_model(), records)

    def test_ui_fixture_ids_obey_real_varchar_lengths(self):
        records = fixture.ui_records()
        model = fixture.reviewed_model()
        fixture.validate_records(model, records)
        records['sys_dict'][0]['id'] = 'x' * 33
        with self.assertRaises(RuntimeError):
            fixture.validate_records(model, records)


if __name__ == '__main__':
    unittest.main()
