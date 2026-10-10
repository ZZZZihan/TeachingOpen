"""Renewal, failed-hook recovery, and command containment without target services."""
import contextlib
import io
import json
import signal
import ssl
import subprocess
import unittest
from unittest.mock import MagicMock, patch

import renew_ip_certificate as renewal


class RenewalTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.object(renewal.time, 'monotonic', side_effect=lambda: self.now))
        self.stack.enter_context(patch.object(renewal.time, 'sleep', side_effect=self.advance))
        self.fingerprint = self.stack.enter_context(
            patch.object(renewal, 'certificate_sha256', side_effect=['old-leaf', 'new-leaf']))
        self.processes = []
        self.popen = self.stack.enter_context(patch.object(renewal.subprocess, 'Popen', side_effect=self.process))
        self.checked = {'status': 'passed', 'certificate_sha256': 'new-leaf', 'remaining_hours': 100}
        self.check = self.stack.enter_context(patch.object(renewal, 'check_certificate', return_value=self.checked))
        self.killpg = self.stack.enter_context(patch.object(renewal.os, 'killpg'))

    def tearDown(self):
        self.stack.close()

    def advance(self, seconds):
        self.now += seconds

    def process(self, arguments, **kwargs):
        process = MagicMock(pid=12345)
        process.wait.return_value = 0
        self.processes.append(process)
        return process

    def arguments(self):
        return [call.args[0] for call in self.popen.call_args_list]

    def unchanged_certificate(self):
        self.fingerprint.side_effect = None
        self.fingerprint.return_value = 'old-leaf'

    def returning_process(self, code, elapsed=0, pid=1):
        process = MagicMock(pid=pid)

        def wait(timeout):
            self.advance(elapsed)
            return code

        process.wait.side_effect = wait
        return process

    def test_updated_and_served_leaf_needs_no_extra_reload(self):
        result = renewal.renew_certificate('8.8.8.8')
        self.assertTrue(result['certificate_changed_on_disk'])
        self.assertFalse(result['reload_recovery_performed'])
        self.assertEqual(result['attempts'], 1)
        self.assertEqual(result['retry_stop_reason'], 'command_succeeded')
        self.assertEqual(result['backoff_results'], [])
        self.assertEqual(result['attempt_results'][0]['status'], 'passed')
        self.assertEqual(len(self.arguments()), 1)
        self.check.assert_called_once_with('8.8.8.8', minimum_hours=48,
            connect_host='127.0.0.1', expected_certificate=renewal.CERTIFICATE, timeout=5)
        arguments = self.arguments()[0]
        self.assertIn('--no-random-sleep-on-renew', arguments)
        self.assertNotIn('--force-renewal', arguments)
        self.assertEqual(arguments[arguments.index('--cert-name') + 1], 'teachingopen-ip')
        self.assertEqual(arguments[arguments.index('--config-dir') + 1], '/var/lib/teachingopen-acme/config')
        self.processes[0].wait.assert_called_once_with(timeout=240)

    def test_success_exit_with_failed_hook_recovers_loaded_leaf(self):
        self.check.side_effect = [renewal.CertificateMismatch('stale'), self.checked]
        result = renewal.renew_certificate('8.8.8.8')
        self.assertTrue(result['reload_recovery_performed'])
        self.assertEqual(self.arguments()[1:], [['/usr/sbin/nginx', '-t'],
                                              ['/bin/systemctl', 'reload', 'nginx']])
        self.assertEqual(len(self.arguments()), 3)
        self.processes[1].wait.assert_called_once_with(timeout=10)
        self.processes[2].wait.assert_called_once_with(timeout=10)

    def test_later_noop_renewal_repairs_previous_failed_reload_without_issuance(self):
        self.fingerprint.side_effect = ['new-leaf', 'new-leaf']
        self.check.side_effect = [renewal.CertificateMismatch('stale'), self.checked]
        result = renewal.renew_certificate('8.8.8.8')
        self.assertFalse(result['certificate_changed_on_disk'])
        self.assertTrue(result['reload_recovery_performed'])
        self.assertEqual(sum(arguments[0].endswith('/certbot') for arguments in self.arguments()), 1)
        self.assertNotIn('--force-renewal', self.arguments()[0])

    def test_expired_served_leaf_can_recover_from_current_disk_leaf(self):
        self.check.side_effect = [ssl.SSLCertVerificationError('expired'), self.checked]
        self.assertTrue(renewal.renew_certificate('8.8.8.8')['reload_recovery_performed'])

    def test_first_certbot_failure_recovers_on_second_attempt(self):
        self.fingerprint.side_effect = ['old-leaf', 'old-leaf', 'new-leaf']
        self.popen.side_effect = [self.returning_process(1, 2), self.returning_process(0, 3)]
        result = renewal.renew_certificate('8.8.8.8')
        self.assertTrue(result['renewal_command_succeeded'])
        self.assertEqual(result['attempts'], 2)
        self.assertEqual([outcome['status'] for outcome in result['attempt_results']],
                         ['failed', 'passed'])
        self.assertEqual(result['backoff_results'], [{'after_attempt': 1,
            'requested_seconds': 5, 'slept_seconds': 5, 'status': 'completed'}])
        self.assertEqual(self.now - 100, 10)
        self.assertEqual(self.popen.call_count, 2)
        self.check.assert_called_once()

    def test_three_certbot_failures_stop_without_reload(self):
        self.unchanged_certificate()
        failed = MagicMock(pid=12345)
        failed.wait.return_value = 1
        self.popen.side_effect = None
        self.popen.return_value = failed
        with self.assertRaises(renewal.RenewalFailure) as caught:
            renewal.renew_certificate('8.8.8.8')
        report = caught.exception.report()
        self.assertEqual(report['stage'], 'certbot')
        self.assertEqual(report['error'], 'command_failed')
        self.assertEqual(report['command_returncode'], 1)
        self.assertEqual(report['attempts'], 3)
        self.assertEqual(report['retry_stop_reason'], 'attempt_limit_reached')
        self.assertEqual([outcome['attempt'] for outcome in report['attempt_results']], [1, 2, 3])
        self.assertEqual([backoff['slept_seconds'] for backoff in report['backoff_results']], [5, 10])
        self.assertEqual(self.now - 100, 15)
        self.assertEqual(self.popen.call_count, 3)
        self.check.assert_not_called()

    def test_timeout_kills_command_group_including_hook_descendants(self):
        self.unchanged_certificate()
        blocked = MagicMock(pid=54321)

        def wait(timeout):
            if blocked.wait.call_count == 1:
                self.advance(timeout)
                raise subprocess.TimeoutExpired('certbot', timeout)
            return -9

        blocked.wait.side_effect = wait
        self.popen.side_effect = None
        self.popen.return_value = blocked
        with self.assertRaises(renewal.RenewalFailure) as caught:
            renewal.renew_certificate('8.8.8.8')
        self.assertEqual(caught.exception.reason, 'command_timeout')
        self.assertEqual(caught.exception.report()['attempts'], 1)
        self.assertEqual(caught.exception.report()['retry_stop_reason'], 'retry_budget_exhausted')
        self.killpg.assert_called_once_with(54321, signal.SIGKILL)
        self.assertEqual(self.popen.call_count, 1)
        self.assertEqual(self.now - 100, renewal.CERTBOT_TIMEOUT)
        self.assertTrue(self.popen.call_args.kwargs['start_new_session'])
        self.check.assert_not_called()

    def test_second_attempt_timeout_uses_remaining_shared_budget(self):
        self.unchanged_certificate()
        blocked = MagicMock(pid=54321)

        def wait(timeout):
            if blocked.wait.call_count == 1:
                self.advance(timeout)
                raise subprocess.TimeoutExpired('certbot', timeout)
            return -9

        blocked.wait.side_effect = wait
        self.popen.side_effect = [self.returning_process(1, 200), blocked]
        with self.assertRaises(renewal.RenewalFailure) as caught:
            renewal.renew_certificate('8.8.8.8')
        self.assertEqual(caught.exception.report()['attempts'], 2)
        self.assertEqual(caught.exception.report()['retry_stop_reason'], 'retry_budget_exhausted')
        self.assertEqual(blocked.wait.call_args_list[0].kwargs['timeout'], 35)
        self.assertEqual(self.popen.call_count, 2)
        self.assertEqual(self.now - 100, renewal.CERTBOT_TIMEOUT)
        self.killpg.assert_called_once_with(54321, signal.SIGKILL)

    def test_backoff_is_skipped_when_no_retry_budget_remains(self):
        self.unchanged_certificate()
        self.popen.side_effect = [self.returning_process(1, 237)]
        with self.assertRaises(renewal.RenewalFailure) as caught:
            renewal.renew_certificate('8.8.8.8')
        report = caught.exception.report()
        self.assertEqual(report['attempts'], 1)
        self.assertEqual(report['retry_stop_reason'], 'retry_budget_exhausted')
        self.assertEqual(report['backoff_results'], [{'after_attempt': 1,
            'requested_seconds': 5, 'slept_seconds': 0, 'status': 'skipped_insufficient_budget'}])
        self.assertEqual(self.now - 100, 237)
        self.assertEqual(self.popen.call_count, 1)

    def test_scheduler_delay_after_backoff_cannot_launch_over_budget(self):
        self.unchanged_certificate()
        self.popen.side_effect = [self.returning_process(1, 200)]
        with patch.object(renewal.time, 'sleep', side_effect=lambda seconds: self.advance(41)):
            with self.assertRaises(renewal.RenewalFailure) as caught:
                renewal.renew_certificate('8.8.8.8')
        report = caught.exception.report()
        self.assertEqual(report['attempts'], 1)
        self.assertEqual(report['retry_stop_reason'], 'retry_budget_exhausted')
        self.assertEqual(report['backoff_results'][0]['slept_seconds'], 41)
        self.assertEqual(self.popen.call_count, 1)

    def test_command_unavailable_is_permanent_and_never_retried(self):
        self.popen.side_effect = FileNotFoundError('private command path is not printed')
        with self.assertRaises(renewal.RenewalFailure) as caught:
            renewal.renew_certificate('8.8.8.8')
        report = caught.exception.report()
        self.assertEqual(report['error'], 'command_unavailable')
        self.assertEqual(report['attempts'], 1)
        self.assertEqual(report['retry_stop_reason'], 'command_unavailable')
        self.assertEqual(report['backoff_results'], [])
        self.assertEqual(self.popen.call_count, 1)
        self.check.assert_not_called()

    def test_failed_hook_with_new_disk_leaf_recovers_without_second_ca_attempt(self):
        self.fingerprint.side_effect = ['old-leaf', 'new-leaf', 'new-leaf']
        self.check.side_effect = [renewal.CertificateMismatch('stale'), self.checked]
        self.popen.side_effect = [self.returning_process(1), self.returning_process(0),
                                 self.returning_process(0)]
        result = renewal.renew_certificate('8.8.8.8')
        self.assertEqual(result['status'], 'passed')
        self.assertFalse(result['renewal_command_succeeded'])
        self.assertTrue(result['certificate_changed_on_disk'])
        self.assertTrue(result['reload_recovery_performed'])
        self.assertEqual(result['attempts'], 1)
        self.assertEqual(result['retry_stop_reason'], 'certificate_changed_on_disk')
        self.assertEqual(result['attempt_results'][0]['status'], 'failed')
        self.assertEqual(result['backoff_results'], [])
        self.assertEqual(self.arguments()[1:], [['/usr/sbin/nginx', '-t'],
                                              ['/bin/systemctl', 'reload', 'nginx']])

    def test_unreadable_initial_certificate_stops_before_certbot(self):
        self.fingerprint.side_effect = ValueError('private certificate input is not printed')
        with self.assertRaises(renewal.RenewalFailure) as caught:
            renewal.renew_certificate('8.8.8.8')
        self.assertEqual(caught.exception.stage, 'certificate_input')
        self.assertEqual(caught.exception.report()['attempts'], 0)
        self.assertEqual(caught.exception.report()['retry_stop_reason'], 'invalid_certificate_input')
        self.popen.assert_not_called()

    def test_unreadable_certificate_after_failure_prevents_retry(self):
        self.fingerprint.side_effect = ['old-leaf', OSError('private path')]
        self.popen.side_effect = [self.returning_process(1)]
        with self.assertRaises(renewal.RenewalFailure) as caught:
            renewal.renew_certificate('8.8.8.8')
        self.assertEqual(caught.exception.stage, 'certificate_input')
        self.assertEqual(caught.exception.report()['attempts'], 1)
        self.assertEqual(caught.exception.report()['retry_stop_reason'], 'invalid_certificate_input')
        self.assertEqual(caught.exception.report()['backoff_results'], [])
        self.assertEqual(self.popen.call_count, 1)

    def test_nginx_test_failure_prevents_reload(self):
        self.check.side_effect = renewal.CertificateMismatch('stale')
        processes = [MagicMock(pid=1), MagicMock(pid=2)]
        processes[0].wait.return_value = 0
        processes[1].wait.return_value = 1
        self.popen.side_effect = processes
        with self.assertRaises(renewal.RenewalFailure) as caught:
            renewal.renew_certificate('8.8.8.8')
        self.assertEqual(caught.exception.stage, 'nginx_test')
        self.assertEqual(self.popen.call_count, 2)

    def test_reload_failure_remains_nonzero(self):
        self.check.side_effect = renewal.CertificateMismatch('stale')
        processes = [MagicMock(pid=1), MagicMock(pid=2), MagicMock(pid=3)]
        for process in processes:
            process.wait.return_value = 0
        processes[2].wait.return_value = 1
        self.popen.side_effect = processes
        with self.assertRaises(renewal.RenewalFailure) as caught:
            renewal.renew_certificate('8.8.8.8')
        self.assertEqual(caught.exception.stage, 'nginx_reload')
        self.assertEqual(self.check.call_count, 1)

    def test_reload_that_never_serves_new_leaf_fails_within_budget(self):
        self.check.side_effect = renewal.CertificateMismatch('stale')
        with self.assertRaises(renewal.RenewalFailure) as caught:
            renewal.renew_certificate('8.8.8.8')
        self.assertEqual(caught.exception.reason, 'verification_failed_after_reload')
        self.assertLessEqual(self.now - 100, 15)
        self.assertEqual(self.popen.call_count, 3)

    def test_three_attempts_leave_full_recovery_budget(self):
        self.fingerprint.side_effect = ['old-leaf', 'old-leaf', 'old-leaf', 'new-leaf']
        self.popen.side_effect = [self.returning_process(1, 100),
            self.returning_process(1, 100), self.returning_process(0, 25),
            self.returning_process(0, 10), self.returning_process(0, 10)]
        checks = 0

        def slow_stale_check(*args, **kwargs):
            nonlocal checks
            checks += 1
            self.advance(kwargs['timeout'] * 2)
            raise renewal.CertificateMismatch('stale')

        self.check.side_effect = slow_stale_check
        with self.assertRaises(renewal.RenewalFailure) as caught:
            renewal.renew_certificate('8.8.8.8')
        self.assertEqual(caught.exception.report()['attempts'], 3)
        self.assertEqual(caught.exception.reason, 'verification_failed_after_reload')
        self.assertEqual(self.now - 100, 285)
        self.assertLessEqual(self.now - 100, renewal.TOTAL_TIMEOUT)
        self.assertEqual(checks, 3)
        self.assertEqual(self.popen.call_count, 5)

    def test_timeout_cleanup_is_bounded_by_total_deadline(self):
        blocked = MagicMock(pid=54321)

        def wait(timeout):
            self.advance(timeout)
            raise subprocess.TimeoutExpired('certbot', timeout)

        blocked.wait.side_effect = wait
        self.popen.side_effect = None
        self.popen.return_value = blocked
        with self.assertRaises(renewal.RenewalFailure):
            renewal.command(renewal.CERTBOT, 'certbot', 110, 10, cleanup_deadline=111)
        self.assertEqual([call.kwargs['timeout'] for call in blocked.wait.call_args_list], [10, 1])
        self.assertEqual(self.now, 111)
        self.killpg.assert_called_once_with(54321, signal.SIGKILL)

    def test_reloaded_leaf_with_insufficient_lifetime_still_fails(self):
        self.check.side_effect = [renewal.CertificateMismatch('stale')] + [
            ValueError('Served certificate expires in 1 hour')] * 20
        with self.assertRaises(renewal.RenewalFailure) as caught:
            renewal.renew_certificate('8.8.8.8')
        self.assertEqual(caught.exception.reason, 'verification_failed_after_reload')
        self.assertTrue(all(call.kwargs['minimum_hours'] == 48
                            for call in self.check.call_args_list))

    def test_long_renewal_and_recovery_fit_the_300_second_unit_budget(self):
        def slow_process(arguments, **kwargs):
            process = self.process(arguments, **kwargs)
            process.wait.side_effect = lambda timeout: (self.advance(timeout), 0)[1]
            return process

        checks = 0

        def slow_check(*args, **kwargs):
            nonlocal checks
            checks += 1
            self.advance(kwargs['timeout'] * 2)
            if checks == 1:
                raise renewal.CertificateMismatch('stale')
            return self.checked

        self.popen.side_effect = slow_process
        self.check.side_effect = slow_check
        result = renewal.renew_certificate('8.8.8.8')
        self.assertTrue(result['reload_recovery_performed'])
        self.assertLess(self.now - 100, renewal.TOTAL_TIMEOUT)
        self.assertLess(renewal.TOTAL_TIMEOUT, 300)

    def test_connection_failure_does_not_blindly_reload(self):
        self.check.side_effect = OSError('loopback unavailable')
        with self.assertRaises(renewal.RenewalFailure) as caught:
            renewal.renew_certificate('8.8.8.8')
        self.assertEqual(caught.exception.reason, 'verification_failed')
        self.assertEqual(self.popen.call_count, 1)

    def test_invalid_ip_fails_before_read_or_renew(self):
        with self.assertRaises(ValueError):
            renewal.renew_certificate('127.0.0.1')
        self.fingerprint.assert_not_called()
        self.popen.assert_not_called()

    def test_cli_failure_is_structured_and_does_not_print_command_output(self):
        self.unchanged_certificate()
        failed = MagicMock(pid=1)
        failed.wait.return_value = 1
        self.popen.side_effect = None
        self.popen.return_value = failed
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = renewal.main(['--ip', '8.8.8.8'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())['stage'], 'certbot')
        self.assertEqual(json.loads(output.getvalue())['attempts'], 3)
        self.assertEqual(self.popen.call_args.kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(self.popen.call_args.kwargs['stderr'], subprocess.DEVNULL)

    def test_cli_invalid_input_reports_zero_attempts(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = renewal.main(['--ip', '127.0.0.1'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue())['attempts'], 0)
        self.popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
