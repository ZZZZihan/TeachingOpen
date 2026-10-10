#!/usr/bin/env python3
"""Verify the certificate actually served for an IP; never renew or change services."""
import argparse
import datetime
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import socket
import ssl
import sys
import time


class CertificateMismatch(ValueError):
    """The live TLS leaf does not match the expected certificate on disk."""


def certificate_sha256(path):
    """Read one public PEM leaf certificate, never its associated private key."""
    pem = Path(path).read_text(encoding='ascii').strip()
    if (len(pem) > 65536 or pem.count('-----BEGIN CERTIFICATE-----') != 1 or
            pem.count('-----END CERTIFICATE-----') != 1):
        raise ValueError('Expected exactly one PEM leaf certificate')
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()


def check_certificate(ip, port=443, minimum_hours=48, connect_host=None, ca_file=None,
                      expected_certificate=None, timeout=5):
    address = ipaddress.IPv4Address(ip)
    if not address.is_global:
        raise ValueError('A public IPv4 address is required')
    if not 1 <= port <= 65535:
        raise ValueError('Invalid port')
    if not math.isfinite(minimum_hours) or minimum_hours <= 0:
        raise ValueError('minimum_hours must be positive and finite')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be positive and finite')
    # Loopback override checks the same served certificate without relying on
    # cloud NAT hairpin support. It does not prove public 443 reachability.
    if connect_host is not None and connect_host != '127.0.0.1':
        raise ValueError('The optional connection override must be 127.0.0.1')
    expected_sha256 = (certificate_sha256(expected_certificate)
                       if expected_certificate is not None else None)
    context = ssl.create_default_context(cafile=ca_file)
    with socket.create_connection((connect_host or ip, port), timeout=timeout) as plain:
        with context.wrap_socket(plain, server_hostname=ip) as secured:
            certificate = secured.getpeercert()
            fingerprint = hashlib.sha256(secured.getpeercert(binary_form=True)).hexdigest()
            if expected_sha256 is not None and fingerprint != expected_sha256:
                raise CertificateMismatch('Served leaf certificate does not match expected certificate')
            expires = ssl.cert_time_to_seconds(certificate['notAfter'])
            remaining = (expires - time.time()) / 3600
            if remaining < minimum_hours:
                raise ValueError('Served certificate expires in %.2f hours (minimum %.2f)' %
                                 (remaining, minimum_hours))
            return {
                'status': 'passed', 'ip': ip, 'port': port,
                'connection_host': connect_host or ip,
                'trust_and_ip_verified': True,
                'expires_at': datetime.datetime.fromtimestamp(
                    expires, datetime.timezone.utc).isoformat(),
                'remaining_hours': round(remaining, 2),
                'certificate_sha256': fingerprint,
                'expected_certificate_checked': expected_sha256 is not None,
                'expected_certificate_sha256': expected_sha256,
                'tls_version': secured.version(),
                'public_reachability_checked': connect_host is None,
                'application_behavior_checked': False,
            }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', required=True)
    parser.add_argument('--port', type=int, default=443)
    parser.add_argument('--min-hours', type=float, default=48)
    parser.add_argument('--connect-host', choices=['127.0.0.1'])
    parser.add_argument('--ca-file', help='Explicit CA only for isolated tests or managed clients')
    parser.add_argument('--expected-certificate',
                        help='Compare the served leaf with this public PEM leaf certificate')
    args = parser.parse_args(argv)
    try:
        result = check_certificate(args.ip, args.port, args.min_hours, args.connect_host,
                                   args.ca_file, args.expected_certificate)
    except (ValueError, OSError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
