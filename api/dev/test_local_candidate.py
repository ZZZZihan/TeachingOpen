import contextlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import local_candidate as candidate
from local_recovery import file_inventory, private_write


class LocalCandidateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / '.devspace'; self.root.mkdir()
        self.runtime = self.root / 'runtime'; self.runtime.mkdir(mode=0o700)
        self.refs = []
        for name in ('a', 'b'):
            bundle = self.root / name; bundle.mkdir(mode=0o700)
            for filename, contents in {'app.jar': 'jar', 'web/index.html': name, 'runner/serve-frontend.py': 'server', 'runner/local_runtime.py': 'runtime'}.items():
                file = bundle / filename; file.parent.mkdir(exist_ok=True); file.write_text(contents)
            private_write(bundle / 'candidate.json', json.dumps({'format': 1, 'kind': 'teachingopen-local-candidate', 'files': file_inventory(bundle), 'database_schema': {'t': 'schema'}}))
            self.refs.append(candidate.reference(bundle))
        self.a, self.b = self.refs

    @contextlib.contextmanager
    def guards(self, start=None, schema=None):
        with patch.object(candidate, 'assert_app_config'), patch.object(candidate, 'assert_database'), patch.object(candidate.os, 'access', return_value=True), patch.object(candidate, 'schema_inventory', return_value=schema or {'t': 'schema'}), patch.object(candidate, 'owned_children', return_value={}), patch.object(candidate, 'stop_children') as stop, patch.object(candidate, 'start_candidate', side_effect=start) as begin:
            yield stop, begin

    def ready(self, active=None, previous=None, **kwargs):
        candidate.write_state(self.runtime, dict({'status': 'ready', 'active': active or self.a, 'previous': previous}, **kwargs))

    def test_intact_bundle_and_changed_bytes(self):
        self.assertEqual(candidate.inspect_bundle(self.a)['database_schema'], {'t': 'schema'})
        (Path(self.a['path']) / 'web/index.html').write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'hashes changed'): candidate.inspect_bundle(self.a)

    def test_manifest_replacement_rejected(self):
        (Path(self.a['path']) / 'candidate.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'manifest changed'): candidate.inspect_bundle(self.a)

    def test_corrupt_target_leaves_active_running(self):
        self.ready(); before = candidate.read_state(self.runtime)
        (Path(self.b['path']) / 'app.jar').write_bytes(b'bad')
        with self.guards() as (stop, begin):
            with self.assertRaises(ValueError): candidate.activate(self.runtime, self.b, self.root)
            stop.assert_not_called(); begin.assert_not_called()
        self.assertEqual(candidate.read_state(self.runtime), before)

    def test_schema_difference_refuses_before_stop(self):
        self.ready()
        with self.guards(schema={'t': 'changed'}) as (stop, begin):
            with self.assertRaisesRegex(ValueError, 'schema differs'): candidate.activate(self.runtime, self.b, self.root)
            stop.assert_not_called(); begin.assert_not_called()

    def test_successful_switch_remembers_previous(self):
        self.ready()
        with self.guards(): result = candidate.activate(self.runtime, self.b, self.root)
        self.assertEqual(result['active'], self.b); self.assertEqual(result['previous'], self.a)
        self.assertEqual(result['status'], 'ready')

    def test_failed_start_restores_previous(self):
        self.ready()
        with self.guards(start=[RuntimeError('startup failed'), None]) as (_, begin):
            result = candidate.activate(self.runtime, self.b, self.root)
        self.assertEqual(result['status'], 'failed_rolled_back')
        self.assertEqual([call.args[1] for call in begin.call_args_list], [self.b, self.a])
        self.assertEqual(candidate.read_state(self.runtime)['active'], self.a)

    def test_failed_initial_start_stays_stopped(self):
        with self.guards(start=RuntimeError('startup failed')):
            result = candidate.activate(self.runtime, self.b, self.root)
        self.assertEqual(result['status'], 'failed_stopped')
        self.assertIsNone(candidate.read_state(self.runtime)['active'])

    def test_failed_recovery_retains_both_references(self):
        self.ready()
        with self.guards(start=RuntimeError('all starts failed')):
            with self.assertRaisesRegex(RuntimeError, 'recovery failed'): candidate.activate(self.runtime, self.b, self.root)
        state = candidate.read_state(self.runtime)
        self.assertEqual(state['status'], 'recovery-required')
        self.assertEqual(state['active'], self.a); self.assertEqual(state['target'], self.b)

    def test_interruption_requires_explicit_recover(self):
        self.ready(status='switching', target=self.b)
        with self.guards() as (stop, begin):
            with self.assertRaisesRegex(RuntimeError, 'Interrupted'): candidate.activate(self.runtime, self.b, self.root)
            stop.assert_not_called(); begin.assert_not_called()
            result = candidate.activate(self.runtime, None, self.root, recover=True)
        self.assertEqual(result['status'], 'ready'); self.assertEqual(result['active'], self.a)

    def test_manual_rollback_uses_recorded_previous(self):
        self.ready(active=self.b, previous=self.a)
        with self.guards(): result = candidate.activate(self.runtime, None, self.root, rollback=True)
        self.assertEqual(result['active'], self.a); self.assertEqual(result['previous'], self.b)

    def test_parallel_operation_rejected(self):
        with candidate.operation_lock(self.runtime):
            with self.assertRaisesRegex(RuntimeError, 'Another candidate'):
                with candidate.operation_lock(self.runtime): self.fail('Second operation acquired lock')

    def test_reused_pid_not_stopped(self):
        (self.runtime / 'backend-process.json').write_text(json.dumps({'pid': 1234, 'jar_path': str(Path(self.a['path']) / 'app.jar'), 'process_start': 'old start'}))
        with patch.object(candidate, 'process', return_value={'start': 'new start', 'command': 'unrelated'}), patch.object(candidate, 'listeners', return_value=set()), patch.object(candidate.os, 'kill') as kill:
            with self.assertRaisesRegex(RuntimeError, 'reused backend PID'): candidate.stop_children(self.runtime, [self.a], self.root)
            kill.assert_not_called()

    def test_foreign_listener_not_stopped(self):
        with patch.object(candidate, 'listeners', return_value={1234}), patch.object(candidate.os, 'kill') as kill:
            with self.assertRaisesRegex(RuntimeError, 'another process'): candidate.stop_children(self.runtime, [], self.root)
            kill.assert_not_called()

    def test_auto_increment_is_not_schema_migration(self):
        def query(counter):
            return lambda runtime, sql: 'example' if sql.startswith('SELECT') else 'example\tCREATE TABLE example (id int) ENGINE=InnoDB AUTO_INCREMENT=' + str(counter)
        with patch.object(candidate, 'sql', side_effect=query(4)): a = candidate.schema_inventory(self.runtime)
        with patch.object(candidate, 'sql', side_effect=query(7)): b = candidate.schema_inventory(self.runtime)
        self.assertEqual(a, b)

    def test_backend_stop_refuses_same_jar_in_another_runtime(self):
        spec = importlib.util.spec_from_file_location('backend_guard_test', Path(__file__).with_name('run-backend.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        (self.runtime / 'backend.pid').write_text('1234\n')
        jar = Path(self.a['path']) / 'app.jar'
        command = str(jar) + ' --spring.profiles.active=dev,localtest --spring.config.additional-location=file:/another/runtime/config/'
        with patch.object(module.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=command)), patch.object(module.os, 'kill') as kill:
            with self.assertRaisesRegex(RuntimeError, 'another process'):
                module.run(self.runtime, self.root, 'stop', None, jar=jar)
            kill.assert_not_called()


if __name__ == '__main__': unittest.main()
