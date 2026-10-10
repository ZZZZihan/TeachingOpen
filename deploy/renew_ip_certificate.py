#!/usr/bin/env python3
"""Renew the dedicated IP certificate and verify that Nginx actually serves it."""
import argparse
import ipaddress
import json
import os
import signal
import ssl
import subprocess
import sys
import time

from check_ip_certificate import CertificateMismatch, certificate_sha256, check_certificate


CERTIFICATE = '/var/lib/teachingopen-acme/config/live/teachingopen-ip/cert.pem'
CERTBOT = [
    '/opt/teachingopen-certbot/bin/certbot', 'renew', '--no-random-sleep-on-renew',
    '--non-interactive', '--cert-name', 'teachingopen-ip',
    '--config-dir', '/var/lib/teachingopen-acme/config',
    '--work-dir', '/var/lib/teachingopen-acme/work',
    '--logs-dir', '/var/lib/teachingopen-acme/logs',
    '--deploy-hook', '/usr/sbin/nginx -t && /bin/systemctl reload nginx',
]
# All Certbot attempts and backoff share 240 seconds, reserving 55 seconds for
# certificate verification and failed hook recovery within the 300 second unit.
TOTAL_TIMEOUT = 295
CERTBOT_TIMEOUT = 240
COMMAND_TIMEOUT = 10
VERIFY_TIMEOUT = 15
CERTBOT_ATTEMPTS = 3
RETRY_DELAYS = (5, 10)


class RenewalFailure(Exception):
    def __init__(self, stage, reason, returncode=None):
        super().__init__(reason)
        self.stage, self.reason, self.returncode = stage, reason, returncode
        self.retry_state = None

    def report(self):
        result = {'status': 'failed', 'stage': self.stage, 'error': self.reason}
        if self.returncode is not None:
            result['command_returncode'] = self.returncode
        if self.retry_state is not None:
            result.update(self.retry_state)
        return result


def remaining(deadline, maximum):
    seconds = min(maximum, deadline - time.monotonic())
    if seconds <= 0:
        raise RenewalFailure('budget', 'total_timeout')
    return seconds


def command(arguments, stage, deadline, maximum, cleanup_deadline=None):
    timeout = remaining(deadline, maximum)
    try:
        process = subprocess.Popen(arguments, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Kill the entire command group, including a blocked deploy-hook shell.
        # Waiting on captured pipes could otherwise outlive the stated timeout.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        cleanup_seconds = min(3, (cleanup_deadline or deadline) - time.monotonic())
        if cleanup_seconds > 0:
            try:
                process.wait(timeout=cleanup_seconds)
            except subprocess.TimeoutExpired:
                pass  # systemd remains the final containment boundary.
        raise RenewalFailure(stage, 'command_timeout') from None
    except OSError:
        raise RenewalFailure(stage, 'command_unavailable') from None
    if returncode:
        # Certbot retains its detailed output in the dedicated private log.
        raise RenewalFailure(stage, 'command_failed', returncode)


def disk_fingerprint():
    try:
        return certificate_sha256(CERTIFICATE)
    except (ValueError, OSError):
        raise RenewalFailure('certificate_input',
                             'invalid_or_unreadable_certificate_input') from None


def retry_certbot(before, deadline, state):
    # Keep the original recovery reserve even when early failures permit retries.
    certbot_deadline = deadline - (TOTAL_TIMEOUT - CERTBOT_TIMEOUT)
    for attempt in range(1, CERTBOT_ATTEMPTS + 1):
        if certbot_deadline <= time.monotonic():
            state['retry_stop_reason'] = 'retry_budget_exhausted'
            raise RenewalFailure('budget', 'total_timeout')
        timeout = remaining(certbot_deadline, CERTBOT_TIMEOUT)
        started = time.monotonic()
        state['attempts'] = attempt
        outcome = {'attempt': attempt, 'timeout_seconds': round(timeout, 3)}
        state['attempt_results'].append(outcome)
        try:
            command(CERTBOT, 'certbot', certbot_deadline, CERTBOT_TIMEOUT,
                    cleanup_deadline=deadline)
        except RenewalFailure as error:
            outcome.update(status='failed', error=error.reason,
                           elapsed_seconds=round(time.monotonic() - started, 3))
            if error.returncode is not None:
                outcome['command_returncode'] = error.returncode
            if error.reason == 'command_unavailable':
                state['retry_stop_reason'] = 'command_unavailable'
                raise
            # A failed deploy hook can follow successful issuance. Stop CA work
            # as soon as its public leaf changed, then verify/recover Nginx below.
            if disk_fingerprint() != before:
                state['retry_stop_reason'] = 'certificate_changed_on_disk'
                return False
            if error.reason not in ('command_failed', 'command_timeout'):
                state['retry_stop_reason'] = 'non_retryable_failure'
                raise
            if attempt == CERTBOT_ATTEMPTS:
                state['retry_stop_reason'] = 'attempt_limit_reached'
                raise
            delay = RETRY_DELAYS[attempt - 1]
            backoff = {'after_attempt': attempt, 'requested_seconds': delay,
                       'slept_seconds': 0, 'status': 'skipped_insufficient_budget'}
            state['backoff_results'].append(backoff)
            if certbot_deadline - time.monotonic() <= delay:
                state['retry_stop_reason'] = 'retry_budget_exhausted'
                raise
            started_sleep = time.monotonic()
            time.sleep(delay)
            backoff.update(slept_seconds=round(time.monotonic() - started_sleep, 3),
                           status='completed')
            if certbot_deadline <= time.monotonic():
                state['retry_stop_reason'] = 'retry_budget_exhausted'
                raise
        else:
            outcome.update(status='passed',
                           elapsed_seconds=round(time.monotonic() - started, 3))
            state['retry_stop_reason'] = 'command_succeeded'
            return True


def served_certificate(ip, deadline):
    # TCP connect and TLS handshake each share this socket timeout.
    timeout = remaining(deadline, 10) / 2
    return check_certificate(ip, minimum_hours=48, connect_host='127.0.0.1',
                             expected_certificate=CERTIFICATE, timeout=timeout)


def renew_certificate(ip):
    address = ipaddress.IPv4Address(ip)
    if not address.is_global:
        raise ValueError('A public IPv4 address is required')
    deadline = time.monotonic() + TOTAL_TIMEOUT
    state = {'attempts': 0, 'attempt_results': [], 'backoff_results': [],
             'retry_stop_reason': 'not_started'}
    try:
        before = disk_fingerprint()
        succeeded = retry_certbot(before, deadline, state)
        changed = disk_fingerprint() != before
        recovered = False
        try:
            checked = served_certificate(ip, deadline)
        except (CertificateMismatch, ssl.SSLCertVerificationError):
            # Also repair this on a later no-op renewal without another issuance.
            command(['/usr/sbin/nginx', '-t'], 'nginx_test', deadline, COMMAND_TIMEOUT)
            command(['/bin/systemctl', 'reload', 'nginx'], 'nginx_reload', deadline, COMMAND_TIMEOUT)
            verify_deadline = min(deadline, time.monotonic() + VERIFY_TIMEOUT)
            while time.monotonic() < verify_deadline:
                try:
                    checked = served_certificate(ip, verify_deadline)
                    break
                except (ValueError, OSError):
                    seconds = verify_deadline - time.monotonic()
                    if seconds <= 0:
                        raise RenewalFailure('served_certificate', 'verification_failed_after_reload') from None
                    time.sleep(min(1, seconds))
            else:
                raise RenewalFailure('served_certificate', 'verification_failed_after_reload')
            recovered = True
        except (ValueError, OSError):
            raise RenewalFailure('served_certificate', 'verification_failed') from None
    except RenewalFailure as error:
        if error.stage == 'certificate_input':
            state['retry_stop_reason'] = 'invalid_certificate_input'
        error.retry_state = state
        raise
    return {
        'status': 'passed', 'renewal_command_succeeded': succeeded,
        'certificate_changed_on_disk': changed, 'reload_recovery_performed': recovered,
        'served_certificate': checked, **state,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', required=True)
    args = parser.parse_args(argv)
    try:
        result = renew_certificate(args.ip)
    except RenewalFailure as error:
        print(json.dumps(error.report()))
        return 1
    except (ValueError, OSError):
        print(json.dumps({'status': 'failed', 'stage': 'certificate_input',
                          'error': 'invalid_or_unreadable_certificate_input',
                          'attempts': 0, 'attempt_results': [], 'backoff_results': [],
                          'retry_stop_reason': 'not_started'}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
