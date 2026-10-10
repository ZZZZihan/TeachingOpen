import contextlib
import datetime
import importlib.abc
import importlib.util
import io
import json
from pathlib import Path
import ssl
import tempfile
import types
import unittest
from unittest.mock import patch

import monitor_ip_https as monitor


NOW = 1800000000
MONOTONIC = 200000


def certificate(hours=120, fingerprint='a'*64, remote=False):
    value = {'status': 'passed', 'trust_and_ip_verified': True,
             'certificate_sha256': fingerprint,
             'expires_at': datetime.datetime.fromtimestamp(
                 NOW+hours*3600, datetime.timezone.utc).isoformat()}
    if remote:
        value.update(expected_certificate_checked=True, expected_certificate_sha256=fingerprint)
    return value


def observation(hours=120, fingerprint='a'*64):
    units = {}
    for kind in ('check', 'renew'):
        units[kind+'_timer'] = {'LoadState': 'loaded', 'ActiveState': 'active',
                               'UnitFileState': 'enabled',
                               'LastTriggerUSecMonotonic': (MONOTONIC-600)*1000000,
                               'ActiveEnterTimestampMonotonic': (MONOTONIC-1000)*1000000}
        units[kind+'_service'] = {'LoadState': 'loaded', 'ActiveState': 'inactive',
                                 'SubState': 'dead', 'Result': 'success', 'ExecMainStatus': 0,
                                 'ExecMainStartTimestampMonotonic': (MONOTONIC-600)*1000000}
    return ({'status': 'passed', 'monotonic': MONOTONIC, 'units': units,
             'certificate': certificate(hours, fingerprint, True)},
            certificate(hours, fingerprint), {'status': 'passed'})


def evaluate(observed, previous=None, now=NOW):
    return monitor.evaluate(*observed, previous or {}, now)


def codes(result):
    return {issue['code'] for issue in result['issues']}


class MonitorTests(unittest.TestCase):
    def test_healthy_baseline_and_no_change_are_quiet(self):
        result, state = evaluate(observation())
        self.assertEqual(result['status'], 'healthy')
        self.assertFalse(result['attention_required'])
        self.assertIsNone(result['certificate_event'])
        self.assertFalse(evaluate(observation(), state)[0]['attention_required'])

    def test_failure_repeats_quietly_then_recovers(self):
        observed = observation()
        _, baseline = evaluate(observed)
        observed[0]['units']['renew_service'].update(Result='exit-code', ExecMainStatus=1)
        observed[0]['renewal'] = {'status': 'failed', 'attempts': 3, 'invocation_id': 'c'*32}
        result, failed = evaluate(observed, baseline)
        self.assertEqual(codes(result), {'renew_service_failed'})
        self.assertTrue(result['attention_required'])
        self.assertEqual(result['renewal']['attempts'], 3)
        self.assertFalse(evaluate(observed, failed)[0]['attention_required'])
        recovered, _ = evaluate(observation(), failed)
        self.assertEqual(recovered['status'], 'healthy')
        self.assertEqual(recovered['changes'], [{'kind': 'recovered', 'code': 'renew_service_failed'}])

    def test_expiry_alert_escalates_at_48_24_and_zero_once_each(self):
        result, state = evaluate(observation(47))
        self.assertEqual(result['issues'][0]['stage'], '48h')
        self.assertTrue(result['attention_required'])
        self.assertFalse(evaluate(observation(47), state)[0]['attention_required'])
        result, state = evaluate(observation(23), state)
        self.assertEqual(result['issues'][0]['stage'], '24h')
        self.assertEqual(result['status'], 'critical')
        self.assertTrue(result['attention_required'])
        self.assertFalse(evaluate(observation(23), state)[0]['attention_required'])
        unavailable = ({'status': 'failed'}, {'status': 'failed', 'error': 'tls_expired'},
                       {'status': 'failed', 'error': 'entry_unavailable'})
        result, state = evaluate(unavailable, state, NOW+24*3600)
        self.assertEqual(next(i for i in result['issues'] if i['code'] == 'certificate_expiry')['stage'], 'expired')
        self.assertFalse(evaluate(unavailable, state, NOW+24*3600)[0]['attention_required'])

    def test_unreachable_preserves_last_good_and_previous_alarms(self):
        observed = observation()
        observed[0]['units']['check_timer']['UnitFileState'] = 'disabled'
        _, previous = evaluate(observed)
        failed = ({'status': 'failed'}, {'status': 'failed'}, {'status': 'failed', 'error': 'entry_unavailable'})
        result, state = evaluate(failed, previous)
        self.assertEqual(result['status'], 'unavailable')
        self.assertIn('check_timer_disabled', codes(result))
        self.assertEqual(state['last_good'], previous['last_good'])
        self.assertFalse(evaluate(failed, state)[0]['attention_required'])
        result, _ = evaluate(observation(), state)
        self.assertTrue(result['attention_required'])
        self.assertEqual(result['status'], 'healthy')

    def test_missing_fields_fail_closed_and_remain_quiet(self):
        observed = observation()
        del observed[0]['units']['renew_timer']['LastTriggerUSecMonotonic']
        observed[0]['certificate'].pop('expected_certificate_checked')
        result, state = evaluate(observed)
        self.assertIn('renew_unit_unavailable', codes(result))
        self.assertIn('loopback_tls_failed', codes(result))
        self.assertIsNone(state['last_good'])
        self.assertFalse(evaluate(observed, state)[0]['attention_required'])

    def test_garbage_collected_oneshot_uses_timer_trigger(self):
        observed = observation()
        observed[0]['units']['renew_service']['ExecMainStartTimestampMonotonic'] = 0
        self.assertEqual(evaluate(observed)[0]['status'], 'healthy')

    def test_first_activation_grace_is_bounded(self):
        observed = observation()
        for kind in ('check', 'renew'):
            observed[0]['units'][kind+'_timer']['LastTriggerUSecMonotonic'] = 0
            observed[0]['units'][kind+'_timer']['ActiveEnterTimestampMonotonic'] = (MONOTONIC-60)*1000000
            observed[0]['units'][kind+'_service']['ExecMainStartTimestampMonotonic'] = 0
        self.assertEqual(evaluate(observed)[0]['status'], 'healthy')
        observed[0]['monotonic'] += 54001
        self.assertEqual(codes(evaluate(observed)[0]), {'check_not_recent', 'renew_not_recent'})

    def test_activating_ignores_old_result_within_unit_budget(self):
        observed = observation()
        observed[0]['units']['renew_service'].update(
            ActiveState='activating', Result='exit-code', ExecMainStatus=1,
            ExecMainStartTimestampMonotonic=(MONOTONIC-20)*1000000)
        self.assertEqual(evaluate(observed)[0]['status'], 'healthy')
        observed[0]['monotonic'] += 321
        self.assertIn('renew_service_overdue', codes(evaluate(observed)[0]))

    def test_renewal_lock_defers_observation_without_false_recovery(self):
        observed = observation()
        _, baseline = evaluate(observed)
        observed[0]['units']['renew_service'].update(ActiveState='activating',
            ExecMainStartTimestampMonotonic=(MONOTONIC-20)*1000000)
        observed[0]['certificate'] = {'status': 'deferred', 'error': 'renewal_in_progress'}
        result, state = evaluate(observed, baseline)
        self.assertEqual(result['status'], 'checking')
        self.assertFalse(result['attention_required'])
        self.assertEqual(state['last_good'], baseline['last_good'])
        baseline['issues']['loopback_tls_failed'] = {'severity': 'error', 'domain': 'remote'}
        result, state = evaluate(observed, baseline)
        self.assertIn('loopback_tls_failed', codes(result))
        self.assertFalse(result['attention_required'])

    def test_deferred_certificate_requires_bounded_running_renewal(self):
        observed = observation()
        observed[0]['certificate'] = {'status': 'deferred', 'error': 'renewal_in_progress'}
        self.assertIn('loopback_tls_failed', codes(evaluate(observed)[0]))
        observed[0]['units']['renew_service']['ActiveState'] = 'activating'
        self.assertIn('loopback_tls_failed', codes(evaluate(observed)[0]))

    def test_deferred_renewal_does_not_hide_public_failure_or_expiry(self):
        observed = observation(23)
        _, baseline = evaluate(observed)
        observed[0]['units']['renew_service'].update(ActiveState='activating',
            ExecMainStartTimestampMonotonic=(MONOTONIC-20)*1000000)
        observed[0]['certificate'] = {'status': 'deferred', 'error': 'renewal_in_progress'}
        observed[1]['status'] = 'failed'
        self.assertTrue({'certificate_expiry', 'public_tls_failed'} <= codes(evaluate(observed, baseline)[0]))

    def test_future_monotonic_clock_is_not_accepted(self):
        observed = observation()
        observed[0]['units']['check_timer']['LastTriggerUSecMonotonic'] = (MONOTONIC+10)*1000000
        self.assertIn('check_unit_unavailable', codes(evaluate(observed)[0]))

    def test_first_new_loaded_certificate_has_unknown_attribution(self):
        _, baseline = evaluate(observation(90))
        result, state = evaluate(observation(150, 'b'*64), baseline)
        event = result['certificate_event']
        self.assertEqual(event['type'], 'first_new_trusted_certificate_loaded')
        self.assertEqual(event['scheduled_attribution'], 'unknown')
        self.assertTrue(result['attention_required'])
        self.assertIsNone(evaluate(observation(160, 'c'*64), state)[0]['certificate_event'])

    def test_reachability_failure_does_not_erase_certificate_baseline(self):
        _, baseline = evaluate(observation(90))
        incomplete = observation(150, 'b'*64)
        incomplete[1]['status'] = 'failed'
        result, partial = evaluate(incomplete, baseline)
        self.assertIsNone(result['certificate_event'])
        self.assertEqual(partial['last_good'], baseline['last_good'])
        result, _ = evaluate(observation(150, 'b'*64), partial)
        self.assertIsNotNone(result['certificate_event'])

    def test_unknown_attribution_does_not_consume_later_timer_event(self):
        _, baseline = evaluate(observation(90))
        changed = observation(150, 'b'*64)
        result, unknown = evaluate(changed, baseline)
        self.assertIsNotNone(result['certificate_event'])
        self.assertIsNone(result['scheduled_certificate_event'])
        started = changed[0]['units']['renew_service']['ExecMainStartTimestampMonotonic']
        changed[0]['units']['renew_timer']['LastTriggerUSecMonotonic'] = started-10000
        changed[0]['units']['renew_service']['InvocationID'] = 'c'*32
        changed[0]['renewal'] = {'status': 'passed', 'attempts': 1,
                               'certificate_changed_on_disk': True, 'invocation_id': 'c'*32,
                               'served_certificate_sha256': 'b'*64,
                               'served_expires_at': changed[1]['expires_at']}
        result, scheduled = evaluate(changed, unknown)
        self.assertIsNone(result['certificate_event'])
        self.assertEqual(result['scheduled_certificate_event']['scheduled_attribution'], 'consistent_with_timer')
        self.assertTrue(result['attention_required'])
        self.assertFalse(evaluate(changed, scheduled)[0]['attention_required'])

    def test_timer_event_requires_all_matching_evidence(self):
        _, baseline = evaluate(observation(90))
        changed = observation(150, 'b'*64)
        changed[0]['units']['renew_service']['InvocationID'] = 'c'*32
        changed[0]['renewal'] = {'status': 'passed', 'certificate_changed_on_disk': True,
                               'invocation_id': 'd'*32, 'served_certificate_sha256': 'b'*64,
                               'served_expires_at': changed[1]['expires_at']}
        self.assertIsNone(evaluate(changed, baseline)[0]['scheduled_certificate_event'])
        changed[0]['renewal']['invocation_id'] = 'c'*32
        changed[0]['units']['renew_timer']['LastTriggerUSecMonotonic'] -= 2000000
        self.assertIsNone(evaluate(changed, baseline)[0]['scheduled_certificate_event'])
        changed[0]['units']['renew_timer']['LastTriggerUSecMonotonic'] += 2000000
        changed[0]['renewal']['certificate_changed_on_disk'] = False
        self.assertIsNone(evaluate(changed, baseline)[0]['scheduled_certificate_event'])

    def test_disk_and_public_must_match_and_expiry_must_advance(self):
        _, baseline = evaluate(observation(90))
        mismatch = observation(150, 'b'*64)
        mismatch[0]['certificate']['expected_certificate_sha256'] = 'c'*64
        self.assertIsNone(evaluate(mismatch, baseline)[0]['certificate_event'])
        mismatch = observation(150, 'b'*64)
        mismatch[1]['certificate_sha256'] = 'c'*64
        self.assertIn('public_leaf_mismatch', codes(evaluate(mismatch, baseline)[0]))
        self.assertIsNone(evaluate(observation(80, 'b'*64), baseline)[0]['certificate_event'])

    def test_state_is_atomic_private_and_refuses_symlinks(self):
        _, state = evaluate(observation())
        state['scope'] = 'scope'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = root/'state.json'
            monitor.write_state(path, state)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(monitor.read_state(path, 'scope'), state)
            monitor.write_state(path, state)
            self.assertEqual(list(root.iterdir()), [path])
            link = root/'link.json'
            link.symlink_to(path)
            with self.assertRaises(ValueError): monitor.read_state(link, 'scope')
            with self.assertRaises(ValueError): monitor.write_state(link, state)
            with self.assertRaises(ValueError): monitor.read_state(path, 'other-scope')
            path.write_text('[]')
            with self.assertRaises(ValueError): monitor.read_state(path, 'scope')

    def test_remote_retry_emits_no_command_error_or_secret(self):
        args = types.SimpleNamespace(ip='8.8.8.8', workbench='/local/workbench', profile='safe',
                                     region='region', instance_id='instance')
        empty = types.SimpleNamespace(returncode=0, stdout=json.dumps({'exit_code': 0, 'output': ''}))
        good = types.SimpleNamespace(returncode=0, stdout=json.dumps({'exit_code': 0,
                                     'output': json.dumps({'status': 'passed'})}))
        with patch.object(monitor.subprocess, 'run', side_effect=[empty, good]) as run, patch.object(monitor.time, 'sleep'):
            self.assertEqual(monitor.remote_probe(args), {'status': 'passed'})
            self.assertEqual(run.call_count, 2)
            self.assertTrue(run.call_args.args[0][-1].startswith('python3 -B - '))
            self.assertNotIn('renew_ip_certificate.py', run.call_args.args[0][-1])
        with patch.object(monitor.subprocess, 'run', side_effect=OSError('SECRET')), patch.object(monitor.time, 'sleep'):
            self.assertEqual(monitor.remote_probe(args), {'status': 'failed', 'error': 'monitor_unavailable'})

    def test_public_untrusted_is_not_healthy(self):
        with patch.object(monitor, 'check_certificate', side_effect=ssl.SSLCertVerificationError('SECRET')):
            self.assertEqual(monitor.public_probe('8.8.8.8')['status'], 'failed')

    def test_entries_status_redirect_content_and_size(self):
        def connection(status=200, location=None, body=b'page'):
            chunks = iter((body, b''))
            response = types.SimpleNamespace(status=status, getheader=lambda _: location, read1=lambda _: next(chunks))
            return types.SimpleNamespace(request=lambda *a, **k: None, getresponse=lambda: response,
                                         sock=types.SimpleNamespace(settimeout=lambda _: None), close=lambda: None)
        for first, second, expected in ((connection(), connection(), 'passed'),
                                        (connection(307, 'https://8.8.8.8/'), connection(), 'passed'),
                                        (connection(307, 'https://8.8.8.8/'), connection(500), 'failed'),
                                        (connection(307, 'https://8.8.8.8/'), connection(body=b''), 'failed'),
                                        (connection(307, 'https://other.example/'), connection(), 'failed'),
                                        (connection(307, 'http://8.8.8.8/'), connection(), 'failed'),
                                        (connection(307, 'https://8.8.8.8:8443/'), connection(), 'failed'),
                                        (connection(307, 'https://8.8.8.8/'), connection(307, 'https://other.example/'), 'failed'),
                                        (connection(301), connection(), 'failed'),
                                        (connection(location='/'), connection(), 'failed'),
                                        (connection(), connection(body=b'other'), 'failed'),
                                        (connection(body=b'x'*1048577), connection(), 'failed')):
            with patch.object(monitor.http.client, 'HTTPConnection', return_value=first), patch.object(
                    monitor.http.client, 'HTTPSConnection', return_value=second):
                self.assertEqual(monitor.entry_probe('8.8.8.8')['status'], expected)

    def test_slow_continuous_entry_response_obeys_total_deadline(self):
        response = types.SimpleNamespace(status=200, getheader=lambda _: None, read1=lambda _: b'x')
        connection = types.SimpleNamespace(request=lambda *a, **k: None, getresponse=lambda: response,
                                           sock=types.SimpleNamespace(settimeout=lambda _: None), close=lambda: None)
        with patch.object(monitor, 'wall_budget', return_value=contextlib.nullcontext()), patch.object(
                monitor.http.client, 'HTTPConnection', return_value=connection), patch.object(
                monitor.time, 'monotonic', side_effect=[0, 1, 2, 6, 7, 11]):
            self.assertEqual(monitor.entry_probe('8.8.8.8'), {'status': 'failed', 'error': 'entry_unavailable'})

    def test_absolute_budget_interrupts_slow_headers_and_restores_alarm(self):
        import signal
        import time
        handler = signal.getsignal(signal.SIGALRM)
        budget = monitor.wall_budget
        connection = types.SimpleNamespace(request=lambda *a, **k: None, getresponse=lambda: time.sleep(1),
                                           sock=types.SimpleNamespace(settimeout=lambda _: None), close=lambda: None)
        started = time.monotonic()
        with patch.object(monitor, 'wall_budget', side_effect=lambda _: budget(0.02)), patch.object(
                monitor.http.client, 'HTTPConnection', return_value=connection):
            self.assertEqual(monitor.entry_probe('8.8.8.8'), {'status': 'failed', 'error': 'entry_unavailable'})
        self.assertLess(time.monotonic()-started, 0.5)
        self.assertEqual(signal.getsignal(signal.SIGALRM), handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_remote_journal_is_whitelisted_and_timer_timestamp_is_uint64(self):
        class Loader(importlib.abc.Loader):
            def create_module(self, spec): return None
            def exec_module(self, module):
                module.check_certificate = lambda *a, **k: certificate(remote=True)
                module.certificate_lock = lambda **kwargs: contextlib.nullcontext()
        def run(arguments, **kwargs):
            if arguments[0] == 'systemctl':
                fields = {'LoadState': 'loaded', 'ActiveState': 'active', 'SubState': 'waiting',
                          'UnitFileState': 'enabled', 'Result': 'success', 'ExecMainStatus': '0',
                          'ActiveEnterTimestampMonotonic': '123', 'ExecMainStartTimestampMonotonic': '456',
                          'ExecMainExitTimestampMonotonic': '457', 'InvocationID': 'c'*32}
                output = '\n'.join(k+'='+v for k,v in fields.items())
            elif arguments[0] == 'busctl': output = 't 73234159058\n'
            else:
                record = {'MESSAGE': json.dumps({'status': 'passed', 'attempts': 3,
                           'certificate_changed_on_disk': True, 'stderr': 'SECRET',
                           'served_certificate': certificate()}),
                          '__REALTIME_TIMESTAMP': str(NOW*1000000), '_SYSTEMD_INVOCATION_ID': 'c'*32}
                output = json.dumps(record)
            return types.SimpleNamespace(returncode=0, stdout=output)
        output = io.StringIO()
        spec = importlib.util.spec_from_loader('checker', Loader())
        with patch('subprocess.run', side_effect=run), patch('importlib.util.spec_from_file_location', return_value=spec), contextlib.redirect_stdout(output):
            exec(monitor.REMOTE, {'IP': '8.8.8.8', 'CERTIFICATE': monitor.CERTIFICATE})
        value = json.loads(output.getvalue())
        self.assertNotIn('SECRET', output.getvalue())
        self.assertEqual(value['units']['check_timer']['LastTriggerUSecMonotonic'], 73234159058)
        self.assertEqual(value['renewal']['attempts'], 3)
        self.assertEqual(value['renewal']['served_certificate_sha256'], 'a'*64)


if __name__ == '__main__':
    unittest.main()
