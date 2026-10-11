"""Offline boundaries for explicit media-index fixture synchronization."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

DEV = Path(__file__).resolve().parents[1] / 'api/dev'
sys.path.insert(0, str(DEV))
from media_index_fixture import (MEDIA_SOURCES, media_index_snapshot,
                                 mutates_media_source, rebuild_media_index_after_sql)
sys.path.remove(str(DEV))


AFFECTED_PROBES = (
    'verify-unit-view-statistics.py', 'verify-news-content.py',
    'verify-additional-work-authorization.py', 'verify-work-cloning.py',
    'verify-pagination.py', 'verify-course-update.py',
    'verify-work-submission.py', 'verify-work-reference-authorization.py',
)


def fixture_api(token=True, response=None):
    api = Mock(tokens={'admin': 'synthetic-token'} if token else {}, runtime=Path('/owned/fixture'))
    api.request.return_value = response or (200, {'success': True, 'code': 200, 'result': 1}, 'application/json')
    def login(actor):
        api.tokens[actor] = 'synthetic-token'
    api.login.side_effect = login
    return api


class MediaIndexFixtureTest(unittest.TestCase):
    def test_all_six_sources_and_mutation_commands_are_recognized(self):
        for table in MEDIA_SOURCES:
            for statement in (
                'INSERT INTO ' + table + '(id) VALUES (1)',
                'REPLACE LOW_PRIORITY INTO teachingopen_dev.`' + table + '`(id) VALUES (1)',
                'UPDATE IGNORE `' + table + '` SET id=1',
                'DELETE QUICK FROM `teachingopen_dev`.`' + table + '` WHERE id=1',
                'TRUNCATE TABLE teachingopen_dev.' + table,
            ):
                with self.subTest(statement=statement):
                    self.assertTrue(mutates_media_source(statement))

    def test_reads_comments_literals_metadata_and_other_schema_do_not_rebuild(self):
        api = fixture_api(token=False)
        for statement in (
            'SELECT * FROM teaching_news',
            "SELECT 'literal; DELETE FROM sys_data_log;'; UPDATE sys_file SET file_path='teaching_news'",
            '/* DELETE FROM teaching_news; */ SELECT 1; -- UPDATE sys_config SET x=1\nSELECT 2',
            '# INSERT INTO teaching_course\nUPDATE teaching_work SET work_file=1',
            'UPDATE other_fixture.teaching_news SET news_title=1',
            'CREATE TABLE teaching_news(id int)',
            'DROP TRIGGER fixture_source_failure',
        ):
            with self.subTest(statement=statement):
                self.assertFalse(rebuild_media_index_after_sql(api, statement))
        api.login.assert_not_called()
        api.request.assert_not_called()

    def test_trigger_delimiters_do_not_execute_their_body_but_following_mutation_does(self):
        for delimiter in ('$$', '//'):
            definition = ('USE teachingopen_dev;\nDELIMITER ' + delimiter + '\n'
                          'CREATE TRIGGER fixture BEFORE UPDATE ON sys_file FOR EACH ROW BEGIN '
                          'SELECT 1; UPDATE teaching_news SET news_title=1; END' + delimiter + '\nDELIMITER ;\n')
            with self.subTest(delimiter=delimiter):
                self.assertFalse(mutates_media_source(definition))
                self.assertTrue(mutates_media_source(definition + 'DELETE FROM teaching_course WHERE id=1;'))

    def test_multi_statement_fixture_transaction_rebuilds_once_with_existing_admin(self):
        api = fixture_api()
        self.assertTrue(rebuild_media_index_after_sql(api,
            'START TRANSACTION; DELETE FROM sys_data_log WHERE id=1; '
            'DELETE FROM teaching_course_unit WHERE id=2; COMMIT;'))
        api.login.assert_not_called()
        api.request.assert_called_once_with('POST', '/sys/localMediaReferences/rebuild', 'admin')

    def test_missing_admin_token_requires_actual_login_before_rebuild(self):
        api = fixture_api(token=False)
        def request(*args):
            self.assertEqual(api.tokens.get('admin'), 'synthetic-token')
            return 200, {'success': True, 'code': 200}, 'application/json'
        api.request.side_effect = request
        rebuild_media_index_after_sql(api, 'UPDATE sys_config SET config_value=1')
        api.login.assert_called_once_with('admin')
        api.request.assert_called_once()

    def test_denied_failed_or_invalid_rebuild_is_not_hidden_or_retried(self):
        for response in (
            (403, {'success': False, 'code': 403}, 'application/json'),
            (200, {'success': False, 'code': 500}, 'application/json'),
            (200, {'success': True, 'code': 500}, 'application/json'),
            (200, {'success': True}, 'application/json'),
            (200, None, 'text/html'),
            (200, ['not a result'], 'application/json'),
        ):
            api = fixture_api(response=response)
            with self.subTest(response=response), self.assertRaisesRegex(RuntimeError, 'rebuild failed'):
                rebuild_media_index_after_sql(api, 'DELETE FROM sys_data_log WHERE id=1')
            api.request.assert_called_once()
            api.login.assert_not_called()

    def test_snapshot_only_reads_and_detects_reference_and_state_changes(self):
        api = fixture_api(token=False)
        contents = {'sys_local_file_reference': 'source\tlong unicode bytes',
                    'sys_local_file_reference_state': '1\t1\t6C6F63616C'}
        def sql(statement):
            self.assertTrue(statement.startswith('SELECT '))
            self.assertFalse(rebuild_media_index_after_sql(api, statement))
            table = next(table for table in contents if 'teachingopen_dev.' + table + ' ' in statement)
            return contents[table]
        original = media_index_snapshot(sql)
        self.assertEqual(media_index_snapshot(sql), original)
        for table in contents:
            with self.subTest(table=table):
                saved = contents[table]
                contents[table] += '\nchanged'
                after = media_index_snapshot(sql)
                self.assertNotEqual(after[table], original[table])
                self.assertEqual(after[set(contents).difference({table}).pop()], original[set(contents).difference({table}).pop()])
                contents[table] = saved
        api.login.assert_not_called()
        api.request.assert_not_called()

    def test_all_eight_existing_wrappers_sync_success_and_leave_sql_failure_visible(self):
        # Execute just each real wrapper with injected clients, not the HTTP probe.
        # This verifies that a failed SQL call never reaches the repair endpoint.
        for name in AFFECTED_PROBES:
            tree = ast.parse((DEV / name).read_text())
            wrapper = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                           and node.name in {'sql', 'query'}
                           and any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                                   and call.func.id == 'rebuild_media_index_after_sql' for call in ast.walk(node)))
            for sql_failed in (False, True):
                with self.subTest(probe=name, sql_failed=sql_failed):
                    api = fixture_api()
                    client = Mock()
                    result = SimpleNamespace(returncode=0, stdout='  original output  ')
                    client.run.return_value = result
                    client.check_output.return_value = '  original output  '
                    raw_sql = Mock(return_value='original output')
                    if sql_failed:
                        client.run.side_effect = RuntimeError('SQL failure')
                        client.check_output.side_effect = RuntimeError('SQL failure')
                        raw_sql.side_effect = RuntimeError('SQL failure')
                    scope = {'api': api, 'runtime': api.runtime, 'subprocess': client,
                             'mysql_command': lambda runtime: ['owned-mysql'], 'sql': raw_sql,
                             'has_media_index': True,
                             'rebuild_media_index_after_sql': rebuild_media_index_after_sql}
                    exec(compile(ast.Module(body=[wrapper], type_ignores=[]), name, 'exec'), scope)
                    invoke = scope[wrapper.name]
                    if sql_failed:
                        with self.assertRaisesRegex(RuntimeError, 'SQL failure'):
                            invoke('DELETE FROM sys_data_log WHERE id=1')
                        api.request.assert_not_called()
                    else:
                        self.assertEqual(invoke('DELETE FROM sys_data_log WHERE id=1'), 'original output')
                        api.request.assert_called_once()
                        api.request.reset_mock()
                        scope['has_media_index'] = False
                        self.assertEqual(invoke('DELETE FROM sys_data_log WHERE id=1'), 'original output')
                        api.request.assert_not_called()
                    api.login.assert_not_called()


if __name__ == '__main__':
    unittest.main()
