"""Pure cloud backup boundary checks; no real runtime or Redis is contacted."""
import base64
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import scratch_cloud_recovery as cloud


PROJECT = b'fixture_cloud_recovery_public'
KEY = b'scratch:cloud:' + PROJECT


def encoded(value):
    return base64.b64encode(value).decode('ascii')


def entry(key=KEY, fields=None, ttl=-1):
    if fields is None:
        fields = [(b'', b''), (b'binary\x00\xff', b'\x00\r\n\xff'),
                  ('关卡'.encode(), '"合成🚀"'.encode())]
    return {'key_b64': encoded(key), 'ttl_ms': ttl,
            'fields': [[encoded(field), encoded(value)] for field, value in sorted(fields)]}


def document(entries=None):
    return {'format': 1, 'database': 1, 'prefix': 'scratch:cloud:',
            'ttl_policy': 'persistent-only', 'entries': [entry()] if entries is None else entries}


class CloudDocumentTest(unittest.TestCase):
    def reject(self, doc, project_ids=None):
        with self.assertRaises(ValueError):
            cloud.validate_cloud(doc, project_ids)

    def test_binary_empty_unicode_and_newline_bytes_survive_validation(self):
        doc = document()
        result = cloud.validate_cloud(doc, {PROJECT})
        self.assertEqual(result, doc)
        pairs = [(base64.b64decode(field), base64.b64decode(value))
                 for field, value in result['entries'][0]['fields']]
        self.assertIn((b'', b''), pairs)
        self.assertIn((b'binary\x00\xff', b'\x00\r\n\xff'), pairs)
        self.assertIn(('关卡'.encode(), '"合成🚀"'.encode()), pairs)

    def test_empty_cloud_snapshot_is_valid_and_explicit(self):
        doc = document([])
        self.assertEqual(cloud.validate_cloud(doc, set()), doc)
        summary = cloud.cloud_summary(doc)
        self.assertEqual(summary['keys'], 0)
        self.assertEqual(summary['fields'], 0)
        self.assertEqual(summary['authentication'], 'excluded; fresh login required')

    def test_summary_binds_prefix_database_file_counts_and_policy(self):
        self.assertEqual(cloud.cloud_summary(document()), {
            'included': 'scratch-cloud-hashes', 'database': 1, 'prefix': 'scratch:cloud:',
            'file': 'cloud-values.json', 'ttl_policy': 'persistent-only', 'keys': 1, 'fields': 3,
            'authentication': 'excluded; fresh login required'})

    def test_noncloud_and_similar_prefixes_are_refused(self):
        for key in (b'userToken:synthetic', b'fixture:recovery:excluded', b'scratch:cloudx:work',
                    b'xscratch:cloud:work', b'scratch:cloud', b'scratch:cloud:'):
            with self.subTest(key=key):
                self.reject(document([entry(key)]))

    def test_invalid_utf8_project_suffix_is_refused(self):
        self.reject(document([entry(b'scratch:cloud:\xff')]))

    def test_orphan_project_is_refused_but_existing_source_id_is_kept(self):
        self.reject(document(), {b'other_project'})
        self.assertEqual(cloud.validate_cloud(document(), {PROJECT}), document())

    def test_noncanonical_base64_is_refused_in_each_byte_position(self):
        for location in ('key', 'field', 'value'):
            for bad in ('YQ', 'YQ==\n', 'YR==', '????', True, None):
                with self.subTest(location=location, value=bad):
                    doc = document()
                    if location == 'key':
                        doc['entries'][0]['key_b64'] = bad
                    else:
                        doc['entries'][0]['fields'][0][0 if location == 'field' else 1] = bad
                    self.reject(doc)

    def test_duplicate_keys_are_refused(self):
        self.reject(document([entry(), entry()]))

    def test_duplicate_hash_fields_are_refused(self):
        self.reject(document([entry(fields=[(b'name', b'a'), (b'name', b'b')])]))

    def test_unsorted_keys_are_refused(self):
        self.reject(document([entry(b'scratch:cloud:z'), entry(b'scratch:cloud:a')]))

    def test_unsorted_fields_are_refused(self):
        doc = document()
        doc['entries'][0]['fields'].reverse()
        self.reject(doc)

    def test_ttl_is_persistent_integer_only(self):
        for ttl in (0, 1, 10000, -2, '-1', None, True):
            with self.subTest(ttl=ttl):
                self.reject(document([entry(ttl=ttl)]))

    def test_scope_metadata_cannot_change_or_gain_unreviewed_fields(self):
        for key, value in [('format', 2), ('format', True), ('database', 0), ('database', True),
                           ('prefix', '*'), ('ttl_policy', 'preserve-any-ttl'), ('extra', 'not allowed')]:
            with self.subTest(key=key, value=value):
                doc = document()
                doc[key] = value
                self.reject(doc)

    def test_document_and_entries_must_have_the_expected_shape(self):
        for doc in (None, [], {}, {**document(), 'entries': None}, {**document(), 'entries': {}},
                    document([None]), document([{}])):
            with self.subTest(type=type(doc).__name__):
                self.reject(doc)

    def test_entry_metadata_cannot_be_missing_or_extended(self):
        for key in ('key_b64', 'ttl_ms', 'fields'):
            doc = document()
            del doc['entries'][0][key]
            self.reject(doc)
        doc = document()
        doc['entries'][0]['extra'] = 'ignored-state'
        self.reject(doc)

    def test_hash_pairs_must_be_canonical_two_item_arrays(self):
        for pair in (None, {}, 'text', [], ['YQ=='], ['YQ==', 'YQ==', 'YQ=='], [1, 'YQ==']):
            with self.subTest(pair=pair):
                doc = document()
                doc['entries'][0]['fields'] = [pair]
                self.reject(doc)

    def test_empty_hash_cannot_claim_an_existing_cloud_key(self):
        self.reject(document([entry(fields=[])]))

    def test_key_count_limit_refuses_the_whole_document(self):
        self.reject(document([entry(b'scratch:cloud:' + str(i).zfill(5).encode(), [(b'x', b'v')])
                              for i in range(10001)]))

    def test_hash_field_count_limit_refuses_the_whole_document(self):
        self.reject(document([entry(fields=[(str(i).zfill(3).encode(), b'v') for i in range(65)])]))

    def test_key_byte_limit_is_enforced(self):
        self.reject(document([entry(b'scratch:cloud:' + b'a' * 1024)]))

    def test_field_byte_limit_is_enforced(self):
        self.reject(document([entry(fields=[(b'f' * 4097, b'value')])]))

    def test_value_byte_limit_is_enforced(self):
        self.reject(document([entry(fields=[(b'f', b'v' * (1024 * 1024 + 1))])]))

    def test_total_raw_byte_limit_is_enforced_without_truncation(self):
        self.reject(document([entry(fields=[(str(i).encode(), b'v' * (1024 * 1024))
                                            for i in range(16)])]))

    def test_validation_does_not_mutate_supplied_bytes_document(self):
        doc = document()
        original = copy.deepcopy(doc)
        cloud.validate_cloud(doc, {PROJECT})
        self.assertEqual(doc, original)


class CloudTransportTest(unittest.TestCase):
    def test_resp_transport_preserves_raw_bytes_and_refuses_bad_or_oversized_replies(self):
        client = cloud.OwnedRedis('/not-a-runtime')
        client.sock = MagicMock()
        client.reader = io.BytesIO(b'*3\r\n$0\r\n\r\n$5\r\n\x00\r\n\xffx\r\n:-1\r\n')
        self.assertEqual(client.execute(b'HGETALL', b'key\x00\xff'), [b'', b'\x00\r\n\xffx', -1])
        self.assertEqual(client.sock.sendall.call_args.args[0], b'*2\r\n$7\r\nHGETALL\r\n$5\r\nkey\x00\xff\r\n')
        for reply in (b'$3\r\nx\r\n', b'$-2\r\n', b':bad\r\n', b'+unterminated',
                      b'*1\r\n' * 6 + b':0\r\n'):
            with self.subTest(reply=reply):
                client.reader = io.BytesIO(reply)
                with self.assertRaises(RuntimeError): client.execute('READ')
        client.reader = io.BytesIO(b'*2\r\n$5\r\n12345\r\n$5\r\n67890\r\n')
        with patch.object(cloud, 'MAX_DOCUMENT_BYTES', 25):
            with self.assertRaisesRegex(RuntimeError, 'total recovery'): client.execute('READ')

    def test_owner_and_configuration_rejections_close_connections_without_selecting_another_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp).resolve() / '.devspace' / 'runtime'
            (runtime / 'config').mkdir(parents=True); runtime.chmod(0o700)
            credentials = runtime / 'config/credentials.json'
            credentials.write_text(json.dumps({'redis_password': 'synthetic-private-password'})); credentials.chmod(0o600)
            config = runtime / 'config/application-localtest.properties'
            config.write_text('spring.redis.database=1\nspring.redis.password=synthetic-private-password\n'); config.chmod(0o600)
            expected = [b'OK', [b'dir', str(runtime / 'redis-data').encode()],
                        [b'bind', b'127.0.0.1'], [b'port', b'16420'], b'OK']
            for position, bad in ((1, [b'dir', b'/another-runtime']), (2, [b'bind', b'0.0.0.0']),
                                  (3, [b'port', b'6379'])):
                with self.subTest(position=position):
                    sock, reader = MagicMock(), MagicMock(); sock.makefile.return_value = reader
                    replies = expected.copy(); replies[position] = bad
                    with patch.object(cloud, 'assert_app_config'), patch.object(cloud, 'load_ports', return_value={'redis': 16420}), \
                            patch.object(cloud.socket, 'create_connection', return_value=sock), \
                            patch.object(cloud.OwnedRedis, 'execute', side_effect=replies) as execute:
                        with self.assertRaisesRegex(RuntimeError, 'not owned'): cloud.OwnedRedis(runtime).__enter__()
                    sock.close.assert_called_once(); reader.close.assert_called_once()
                    self.assertNotIn(('SELECT', 1), [call.args for call in execute.call_args_list])
            for settings in ('spring.redis.database=0\nspring.redis.password=synthetic-private-password\n',
                             'spring.redis.database=1\nspring.redis.password=different\n'):
                config.write_text(settings)
                with patch.object(cloud, 'assert_app_config'), patch.object(cloud.socket, 'create_connection') as connect:
                    with self.assertRaisesRegex(RuntimeError, 'configuration'): cloud.OwnedRedis(runtime).__enter__()
                connect.assert_not_called()

    def test_atomic_capture_and_restore_use_binary_allowlisted_bytes_only(self):
        doc = document(); raw_fields = []
        for field, value in doc['entries'][0]['fields']:
            raw_fields.extend((base64.b64decode(field), base64.b64decode(value)))
        client = MagicMock(); client.execute.return_value = [[KEY, -1, raw_fields]]
        self.assertEqual(cloud.capture_cloud(client, {PROJECT}), doc)
        client.execute.assert_called_once_with('EVAL', cloud.CAPTURE, 0)
        client.reset_mock(); client.execute.side_effect = [0, 1, [[KEY, -1, raw_fields]]]
        cloud.restore_cloud(client, doc, {PROJECT})
        self.assertEqual(client.execute.call_args_list[1].args,
                         ('EVAL', cloud.RESTORE, 1, KEY, len(raw_fields) // 2, *raw_fields))
        self.assertNotIn(b'fixture:recovery:excluded', client.execute.call_args_list[1].args)

    def test_capture_errors_and_nonempty_target_refuse_without_writes(self):
        for code in ('CLOUD_WRONG_TYPE', 'CLOUD_EXPIRING', 'CLOUD_BYTE_LIMIT'):
            with self.subTest(code=code):
                client = MagicMock(); client.execute.side_effect = cloud.RedisCommandError(code)
                with self.assertRaises(ValueError): cloud.capture_cloud(client, {PROJECT})
        client = MagicMock(); client.execute.return_value = 1
        with self.assertRaisesRegex(RuntimeError, 'not empty'): cloud.restore_cloud(client, document(), {PROJECT})
        client.execute.assert_called_once_with('DBSIZE')


if __name__ == '__main__':
    unittest.main()
