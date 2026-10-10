#!/usr/bin/env python3
"""Read IP HTTPS health and emit sanitized changes; never renew, send, or schedule."""
import argparse
import contextlib
import datetime
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import signal
import ssl
import stat
import subprocess
import sys
import tempfile
import time

from check_ip_certificate import check_certificate


CERTIFICATE = '/var/lib/teachingopen-acme/config/live/teachingopen-ip/cert.pem'
SHA256 = re.compile(r'[0-9a-f]{64}')
SEVERITY = {'warning': 1, 'error': 2, 'critical': 3}
# Fixed commands and selected properties only: no configuration, keys or raw logs.
REMOTE = r'''
import datetime, importlib.util, json, re, ssl, subprocess, time
from pathlib import Path
def command(args):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       text=True, timeout=8)
    if p.returncode: raise ValueError('command_failed')
    return p.stdout
def error(e):
    if isinstance(e, ssl.SSLCertVerificationError):
        return 'tls_expired' if getattr(e,'verify_code',None) == 10 else 'tls_untrusted'
    return 'probe_unavailable'
def cert(c):
    return {k:c[k] for k in ('certificate_sha256','expires_at','trust_and_ip_verified',
                             'expected_certificate_checked','expected_certificate_sha256')}
props = ('LoadState','ActiveState','SubState','UnitFileState','Result','ExecMainStatus',
         'ActiveEnterTimestampMonotonic','ExecMainStartTimestampMonotonic',
         'ExecMainExitTimestampMonotonic','InvocationID')
out = {'status':'passed','units':{}}
for kind in ('renew','check'):
    for suffix in ('service','timer'):
        key = kind+'_'+suffix
        name = 'teachingopen-ip-cert-'+kind+'.'+suffix
        try:
            values = dict(line.split('=',1) for line in command(
                ['systemctl','show',name,'--property='+','.join(props)]).splitlines() if '=' in line)
            clean = {}
            for k,v in values.items():
                if k.endswith('Monotonic') or k == 'ExecMainStatus':
                    if v.isdigit(): clean[k] = int(v)
                elif k == 'InvocationID':
                    if not v or re.fullmatch('[0-9a-f]{32}',v): clean[k] = v
                elif re.fullmatch('[a-z-]{1,40}',v): clean[k] = v
            if suffix == 'timer':
                path = '/org/freedesktop/systemd1/unit/'+name.replace('-','_2d').replace('.','_2e')
                raw = command(['busctl','--system','get-property','org.freedesktop.systemd1',
                               path,'org.freedesktop.systemd1.Timer','LastTriggerUSecMonotonic']).strip()
                if not re.fullmatch(r't \d+',raw): raise ValueError('invalid_timer_time')
                clean['LastTriggerUSecMonotonic'] = int(raw.split()[1])
            out['units'][key] = clean
        except Exception:
            out['units'][key] = {'error':'unit_unavailable'}
try:
    spec = importlib.util.spec_from_file_location('checker','/opt/teachingopen-https/check_ip_certificate.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    with checker.certificate_lock(shared=True, wait_seconds=0):
        checked = checker.check_certificate(IP,minimum_hours=0.000001,connect_host='127.0.0.1',
                                            expected_certificate=CERTIFICATE,timeout=5)
    out['certificate'] = dict(status='passed', **cert(checked))
except Exception as e:
    if type(e).__name__ == 'CertificateBusy':
        out['certificate'] = {'status':'deferred','error':'renewal_in_progress'}
        # Renewal may have started after the earlier unit snapshot.
        try:
            current = dict(line.split('=',1) for line in command(
                ['systemctl','show','teachingopen-ip-cert-renew.service',
                 '--property=ActiveState,ExecMainStartTimestampMonotonic']).splitlines() if '=' in line)
            if (current.get('ActiveState') == 'activating' and
                    current.get('ExecMainStartTimestampMonotonic','').isdigit()):
                out['units']['renew_service'].update(ActiveState='activating',
                    ExecMainStartTimestampMonotonic=int(current['ExecMainStartTimestampMonotonic']))
        except Exception:
            pass  # Missing bounded-running evidence remains a failure below.
    else:
        out['certificate'] = {'status':'failed','error':error(e)}
try:
    lines = command(['journalctl','--no-pager','-u','teachingopen-ip-cert-renew.service',
                     '-n','20','-o','json','--output-fields=MESSAGE,__REALTIME_TIMESTAMP,_SYSTEMD_INVOCATION_ID'])
    for line in reversed(lines.splitlines()):
        record = json.loads(line)
        try: data = json.loads(record.get('MESSAGE',''))
        except (ValueError,TypeError): continue
        if not isinstance(data,dict) or data.get('status') not in ('passed','failed'): continue
        summary = {'status':data['status']}
        if type(data.get('attempts')) is int and 1 <= data['attempts'] <= 3:
            summary['attempts'] = data['attempts']
        if type(data.get('certificate_changed_on_disk')) is bool:
            summary['certificate_changed_on_disk'] = data['certificate_changed_on_disk']
        stamp = record.get('__REALTIME_TIMESTAMP','')
        if isinstance(stamp,str) and stamp.isdigit():
            summary['completed_at'] = datetime.datetime.fromtimestamp(int(stamp)/1e6,datetime.timezone.utc).isoformat()
        invocation = record.get('_SYSTEMD_INVOCATION_ID','')
        if isinstance(invocation,str) and re.fullmatch('[0-9a-f]{32}',invocation):
            summary['invocation_id'] = invocation
        served = data.get('served_certificate',{})
        if isinstance(served,dict):
            fingerprint = served.get('certificate_sha256','')
            if isinstance(fingerprint,str) and re.fullmatch('[0-9a-f]{64}',fingerprint):
                summary['served_certificate_sha256'] = fingerprint
            try:
                date = datetime.datetime.fromisoformat(served['expires_at'])
                if date.tzinfo: summary['served_expires_at'] = date.astimezone(datetime.timezone.utc).isoformat()
            except (ValueError,KeyError,TypeError): pass
        out['renewal'] = summary
        break
except Exception:
    out['renewal'] = {'status':'unavailable'}
out['monotonic'] = time.monotonic()  # Timer may trigger while these reads run.
print(json.dumps(out))
'''


def iso_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def expiry(value):
    parsed = datetime.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('invalid_expiry')
    return parsed.timestamp()


def error_type(error):
    if isinstance(error, ssl.SSLCertVerificationError):
        return 'tls_expired' if getattr(error, 'verify_code', None) == 10 else 'tls_untrusted'
    return 'probe_unavailable'


def remote_probe(args):
    source = 'IP = '+repr(args.ip)+'\nCERTIFICATE = '+repr(CERTIFICATE)+'\n'+REMOTE
    command = [args.workbench, '--profile', args.profile, '--region', args.region,
               'exec', '--instance-id', args.instance_id, '--output', 'json',
               '--command', "python3 -B - <<'PYREMOTE'\n"+source+'\nPYREMOTE']
    for attempt in range(2):
        try:
            process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, timeout=60)
            if len(process.stdout) > 131072: raise ValueError('oversized_output')
            wrapper = json.loads(process.stdout)
            if process.returncode or wrapper.get('exit_code') != 0: raise ValueError('remote_failed')
            result = json.loads(wrapper['output'])
            if isinstance(result, dict) and result.get('status') == 'passed': return result
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
            pass
        if attempt == 0: time.sleep(0.5)
    return {'status': 'failed', 'error': 'monitor_unavailable'}


def public_probe(ip):
    try:
        with wall_budget(10):
            result = check_certificate(ip, minimum_hours=0.000001, timeout=5)
        return {'status': 'passed', **{k: result[k] for k in
                ('certificate_sha256', 'expires_at', 'trust_and_ip_verified')}}
    except (ValueError, OSError) as error:
        return {'status': 'failed', 'error': error_type(error)}


@contextlib.contextmanager
def wall_budget(seconds):
    def expired(signum, frame): raise TimeoutError('probe_deadline')
    handler = signal.signal(signal.SIGALRM, expired)
    previous = signal.setitimer(signal.ITIMER_REAL, seconds)
    started = time.monotonic()
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, handler)
        if previous[0]: signal.setitimer(signal.ITIMER_REAL, max(0.001, previous[0]-(time.monotonic()-started)), previous[1])


def entry_probe(ip):
    fingerprints = []
    redirected = False
    for secured in (False, True):
        deadline = time.monotonic()+10
        connection = (http.client.HTTPSConnection(ip, timeout=5, context=ssl.create_default_context())
                      if secured else http.client.HTTPConnection(ip, timeout=5))
        try:
            with wall_budget(10):
                connection.request('GET', '/', headers={'Accept-Encoding': 'identity'})
                network = connection.sock  # Retain the socket even for Connection: close.
                network.settimeout(max(0.001, deadline-time.monotonic()))
                response = connection.getresponse()
                if (not secured and response.status == 307
                        and response.getheader('Location') == 'https://' + ip + '/'):
                    # Probe only our fixed HTTPS endpoint below, never follow an
                    # arbitrary Location header or compare the redirect body.
                    redirected = True
                    continue
                if response.status != 200 or response.getheader('Location') is not None:
                    return {'status': 'failed', 'error': 'entry_status_or_redirect'}
                digest, size = hashlib.sha256(), 0
                while True:
                    remaining = deadline-time.monotonic()
                    if remaining <= 0: raise TimeoutError('entry_deadline')
                    network.settimeout(remaining)
                    block = response.read1(min(65536, 1048577-size))
                    if time.monotonic() >= deadline: raise TimeoutError('entry_deadline')
                    if not block: break
                    size += len(block); digest.update(block)
                    if size > 1048576: return {'status': 'failed', 'error': 'entry_size_invalid'}
                if not size: return {'status': 'failed', 'error': 'entry_size_invalid'}
                fingerprints.append(digest.hexdigest())
        except (OSError, ValueError, http.client.HTTPException):
            return {'status': 'failed', 'error': 'entry_unavailable'}
        finally:
            connection.close()
    matched = redirected or fingerprints[0] == fingerprints[1]
    return {'status': 'passed' if matched else 'failed',
            'error': None if matched else 'entry_content_mismatch'}


def valid_certificate(value, remote=False):
    try:
        return (value.get('status') == 'passed' and value.get('trust_and_ip_verified') is True
                and isinstance(value.get('certificate_sha256'), str)
                and SHA256.fullmatch(value['certificate_sha256']) is not None
                and math.isfinite(expiry(value['expires_at']))
                and (not remote or (value.get('expected_certificate_checked') is True
                     and value.get('expected_certificate_sha256') == value['certificate_sha256'])))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False


def scheduled_evidence(remote, good, pending):
    try:
        renewal = remote['renewal']
        service, timer = remote['units']['renew_service'], remote['units']['renew_timer']
        trigger, started = timer['LastTriggerUSecMonotonic'], service['ExecMainStartTimestampMonotonic']
        invocation = service['InvocationID']
        return (pending and pending['certificate_sha256'] == good['certificate_sha256']
                and expiry(good['expires_at']) > expiry(pending['previous_expires_at'])
                and renewal['status'] == 'passed' and renewal['certificate_changed_on_disk'] is True
                and re.fullmatch('[0-9a-f]{32}', invocation) is not None
                and invocation == renewal['invocation_id'] and type(trigger) is int and type(started) is int
                and 0 < trigger <= started <= remote['monotonic']*1e6 and started-trigger <= 1000000
                and renewal['served_certificate_sha256'] == good['certificate_sha256']
                and renewal['served_expires_at'] == good['expires_at'])
    except (KeyError, TypeError, ValueError):
        return False


def evaluate(remote, public, entries, previous, now):
    issues, unknown = {}, set()
    units = remote.get('units', {})
    if not isinstance(units, dict): units = {}
    def issue(code, severity, domain): issues[code] = {'severity': severity, 'domain': domain}
    if remote.get('status') != 'passed':
        issue('monitor_unavailable', 'error', 'remote'); unknown.add('remote')
    else:
        mono = remote.get('monotonic')
        for kind, maximum in (('check', 5400), ('renew', 54000)):
            timer, service = units.get(kind+'_timer', {}), units.get(kind+'_service', {})
            try:
                if type(mono) not in (int, float) or not math.isfinite(mono) or mono < 0:
                    raise ValueError('invalid_clock')
                required = ('LastTriggerUSecMonotonic', 'ActiveEnterTimestampMonotonic')
                times = [timer[k] for k in required]+[service['ExecMainStartTimestampMonotonic']]
                if any(type(t) is not int or t < 0 or t > mono*1e6 for t in times):
                    raise ValueError('invalid_time')
                if timer['LoadState'] != 'loaded' or service['LoadState'] != 'loaded':
                    issue(kind+'_unit_missing', 'error', 'remote'); continue
                if timer['ActiveState'] != 'active' or timer['UnitFileState'] != 'enabled':
                    issue(kind+'_timer_disabled', 'error', 'remote')
                if service['ActiveState'] not in ('inactive', 'active', 'activating', 'failed'):
                    raise ValueError('invalid_service_state')
                service_limit = 320 if kind == 'renew' else 330
                running = service['ActiveState'] == 'activating' and times[2] > 0 and mono-times[2]/1e6 <= service_limit
                if not running and (service['Result'] != 'success' or service['ExecMainStatus'] != 0):
                    issue(kind+'_service_failed', 'error', 'remote')
                if service['ActiveState'] == 'activating' and not running:
                    issue(kind+'_service_overdue', 'error', 'remote')
                latest = max(times[0], times[2])
                anchor = latest or times[1]  # First activation grants a bounded grace period.
                if not anchor or mono-anchor/1e6 > maximum:
                    issue(kind+'_not_recent', 'error', 'remote')
            except (KeyError, TypeError, ValueError, AttributeError):
                issue(kind+'_unit_unavailable', 'error', 'remote'); unknown.add('remote')
    remote_cert = remote.get('certificate', {})
    if not isinstance(remote_cert, dict): remote_cert = {}
    renewal = units.get('renew_service', {})
    if not isinstance(renewal, dict): renewal = {}
    started = renewal.get('ExecMainStartTimestampMonotonic', 0)
    deferred = (remote_cert.get('status') == 'deferred'
                and remote_cert.get('error') == 'renewal_in_progress'
                and renewal.get('ActiveState') == 'activating'
                and type(started) is int and started > 0
                and type(remote.get('monotonic')) in (int, float)
                and 0 <= remote['monotonic'] - started / 1e6 <= 320)
    if deferred:
        # In-progress evidence cannot establish recovery or a new certificate.
        unknown.update(('remote', 'public'))
    for value, domain, code in ((remote_cert, 'remote', 'loopback_tls'), (public, 'public', 'public_tls')):
        if deferred and domain == 'remote':
            continue
        if not valid_certificate(value, domain == 'remote'):
            expired = value.get('error') == 'tls_expired'
            issue(code+('_expired' if expired else '_failed'), 'critical' if expired else 'error', domain)
            unknown.add(domain)
    trusted = (valid_certificate(remote_cert, True) and valid_certificate(public)
               and remote_cert['certificate_sha256'] == public['certificate_sha256']
               and remote_cert['expires_at'] == public['expires_at'])
    if valid_certificate(remote_cert, True) and valid_certificate(public) and not trusted:
        issue('public_leaf_mismatch', 'critical', 'public')
    if entries.get('status') != 'passed':
        issue('parallel_entries_failed', 'error', 'entry')
        if entries.get('error') == 'entry_unavailable': unknown.add('entry')
    old_good = previous.get('last_good')
    good = ({'certificate_sha256': public['certificate_sha256'], 'expires_at': public['expires_at']}
            if trusted else old_good)
    if good:
        hours = (expiry(good['expires_at'])-now)/3600
        if hours <= 48:
            issue('certificate_expiry', 'critical' if hours <= 24 else 'warning', 'certificate')
            issues['certificate_expiry']['stage'] = 'expired' if hours <= 0 else ('24h' if hours <= 24 else '48h')
    for code, prior in previous.get('issues', {}).items():
        if prior['domain'] in unknown and code not in issues:
            issues[code] = prior
    changes = [{'kind': 'new' if code not in previous.get('issues', {}) else 'changed',
                'code': code, **value} for code, value in sorted(issues.items())
               if previous.get('issues', {}).get(code) != value]
    changes += [{'kind': 'recovered', 'code': code} for code in sorted(previous.get('issues', {}))
                if code not in issues]
    event = None
    first = previous.get('first_certificate_event', False)
    pending = previous.get('pending_certificate')
    advanced = (trusted and old_good and good['certificate_sha256'] != old_good['certificate_sha256']
                and expiry(good['expires_at']) > expiry(old_good['expires_at']))
    if advanced: pending = dict(good, previous_expires_at=old_good['expires_at'])
    if advanced and not first:
        event = {'type': 'first_new_trusted_certificate_loaded', **good,
                 'scheduled_attribution': 'unknown', 'note': 'scheduled attribution not proven'}
        first = True
    scheduled_event = None
    scheduled_first = previous.get('first_scheduled_certificate_event', False)
    if trusted and not scheduled_first and scheduled_evidence(remote, good, pending):
        scheduled_event = {'type': 'first_new_certificate_with_timer_evidence', **good,
                           'scheduled_attribution': 'consistent_with_timer',
                           'note': 'matching timer record; scheduler causation not proven'}
        scheduled_first, pending = True, None
    status = ('unavailable' if 'monitor_unavailable' in issues else
              'critical' if any(i['severity'] == 'critical' for i in issues.values()) else
              'warning' if issues else 'checking' if deferred else 'healthy')
    renewal = remote.get('renewal', {})
    result = {'status': status, 'issues': [{'code': code, **value} for code, value in sorted(issues.items())],
              'attention_required': bool(changes or event or scheduled_event), 'changes': changes,
              'certificate_event': event, 'scheduled_certificate_event': scheduled_event, 'certificate': good,
              'renewal': {k: renewal[k] for k in ('status', 'attempts', 'certificate_changed_on_disk',
                         'completed_at', 'invocation_id', 'served_certificate_sha256', 'served_expires_at')
                          if isinstance(renewal, dict) and k in renewal}}
    state = {'version': 1, 'issues': issues, 'last_good': good, 'first_certificate_event': first,
             'first_scheduled_certificate_event': scheduled_first, 'pending_certificate': pending}
    return result, state


def state_path(path):
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('unsafe_state_path')
    return path


def read_state(path, scope):
    state_path(path)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return {}
    with os.fdopen(descriptor) as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode): raise ValueError('unsafe_state_file')
        raw = stream.read(32769)
    if len(raw) > 32768: raise ValueError('invalid_state')
    value = json.loads(raw)
    if (not isinstance(value, dict) or value.get('version') != 1 or value.get('scope') != scope
            or not isinstance(value.get('issues'), dict)
            or type(value.get('first_certificate_event')) is not bool
            or type(value.get('first_scheduled_certificate_event', False)) is not bool): raise ValueError('invalid_state')
    for code, issue in value['issues'].items():
        if (not re.fullmatch('[a-z0-9_]{1,60}', code) or not isinstance(issue, dict)
                or issue.get('severity') not in SEVERITY
                or issue.get('domain') not in ('remote', 'public', 'entry', 'certificate')
                or issue.get('stage', '48h') not in ('48h', '24h', 'expired')
                or set(issue)-{'severity', 'domain', 'stage'}): raise ValueError('invalid_state')
    good = value.get('last_good')
    if good is not None and (not isinstance(good, dict) or set(good) != {'certificate_sha256', 'expires_at'}
            or not valid_certificate(dict(good, status='passed', trust_and_ip_verified=True))):
        raise ValueError('invalid_state')
    pending = value.get('pending_certificate')
    if pending is not None:
        if not isinstance(pending, dict) or set(pending) != {'certificate_sha256', 'expires_at', 'previous_expires_at'}:
            raise ValueError('invalid_state')
        if (not valid_certificate(dict(pending, status='passed', trust_and_ip_verified=True))
                or expiry(pending['expires_at']) <= expiry(pending['previous_expires_at'])): raise ValueError('invalid_state')
    return value


def write_state(path, value):
    state_path(path)
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, sort_keys=True); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        state_path(path)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('ip', 'workbench', 'profile', 'region', 'instance-id', 'state-file'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args(argv)
    try:
        if not ipaddress.IPv4Address(args.ip).is_global: raise ValueError('invalid_ip')
        if not Path(args.workbench).is_absolute(): raise ValueError('invalid_workbench_path')
        path = state_path(Path(args.state_file))
        scope = hashlib.sha256(json.dumps([args.ip, args.profile, args.region, args.instance_id]).encode()).hexdigest()
        previous = read_state(path, scope)
        result, state = evaluate(remote_probe(args), public_probe(args.ip), entry_probe(args.ip), previous, time.time())
        state.update(scope=scope, observed_at=iso_now())
        write_state(path, state)
        result['observed_at'] = state['observed_at']
        print(json.dumps(result, sort_keys=True))
        return 0 if result['status'] in ('healthy', 'checking') else 1
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        print(json.dumps({'status': 'unavailable', 'issues': [{'code': 'monitor_state_or_input_invalid',
                          'severity': 'error', 'domain': 'monitor'}], 'attention_required': True,
                          'changes': [], 'certificate_event': None, 'scheduled_certificate_event': None}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
