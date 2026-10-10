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
# Reserve time for failed hook recovery within the unit's 300 second budget.
TOTAL_TIMEOUT = 295
CERTBOT_TIMEOUT = 240
COMMAND_TIMEOUT = 10
VERIFY_TIMEOUT = 15


class RenewalFailure(Exception):
    def __init__(self, stage, reason, returncode=None):
        super().__init__(reason)
        self.stage, self.reason, self.returncode = stage, reason, returncode

    def report(self):
        result = {'status': 'failed', 'stage': self.stage, 'error': self.reason}
        if self.returncode is not None:
            result['command_returncode'] = self.returncode
        return result


def remaining(deadline, maximum):
    seconds = min(maximum, deadline - time.monotonic())
    if seconds <= 0:
        raise RenewalFailure('budget', 'total_timeout')
    return seconds


def command(arguments, stage, deadline, maximum):
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
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass  # systemd's unit timeout remains the final containment boundary.
        raise RenewalFailure(stage, 'command_timeout') from None
    except OSError:
        raise RenewalFailure(stage, 'command_unavailable') from None
    if returncode:
        # Certbot retains its detailed output in the dedicated private log.
        raise RenewalFailure(stage, 'command_failed', returncode)


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
    before = certificate_sha256(CERTIFICATE)
    command(CERTBOT, 'certbot', deadline, CERTBOT_TIMEOUT)
    changed = certificate_sha256(CERTIFICATE) != before
    recovered = False
    try:
        checked = served_certificate(ip, deadline)
    except (CertificateMismatch, ssl.SSLCertVerificationError):
        # A failed deploy hook can leave Certbot successful and Nginx stale.
        # Also repair this on a later no-op renewal, without another issuance.
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
    return {
        'status': 'passed', 'renewal_command_succeeded': True,
        'certificate_changed_on_disk': changed, 'reload_recovery_performed': recovered,
        'served_certificate': checked,
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
                          'error': 'invalid_or_unreadable_certificate_input'}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
