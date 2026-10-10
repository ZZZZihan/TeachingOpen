#!/usr/bin/env python3
"""Monthly ECS public egress control. Python 3.10+, standard library only.

Minute samples are CloudMonitor's Average bit/s integrated over 60 seconds.
They are a control estimate, not a replacement for Alibaba Cloud billing.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')
MINUTE = 60000


class ControlError(RuntimeError):
    pass


def parse_time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ControlError('created_at must include timezone')
    return result


@dataclass(frozen=True)
class Config:
    instance_id: str
    public_ip: str
    region: str
    created_at: str
    baseline_mbps: int = 100
    tiers: tuple = ((150, 5), (200, 1))
    enabled: bool = False
    settle_seconds: int = 300
    role_name: str = 'TeachingOpenTrafficControl'
    state_path: str = '/var/lib/teachingopen-traffic-control/state.sqlite3'

    @classmethod
    def from_dict(cls, data):
        c = cls(**data)
        if not c.instance_id.startswith('i-') or not c.public_ip or not c.region:
            raise ControlError('missing resource identity')
        parse_time(c.created_at)
        if type(c.enabled) is not bool or type(c.baseline_mbps) is not int:
            raise ControlError('enabled must be bool; bandwidth must be integer')
        if not 1 <= c.baseline_mbps <= 100 or not 60 <= c.settle_seconds <= 3600:
            raise ControlError('invalid baseline or settle_seconds')
        previous_gb, previous_cap = Decimal(0), c.baseline_mbps
        if not c.tiers:
            raise ControlError('tiers must not be empty')
        for gb, cap in c.tiers:
            gb = Decimal(str(gb))
            if not gb.is_finite() or gb <= previous_gb or type(cap) is not int or not 1 <= cap < previous_cap:
                raise ControlError('thresholds must increase and positive integer caps must decrease')
            previous_gb, previous_cap = gb, cap
        return c

    def identity(self):
        return [self.region, self.instance_id, self.public_ip, self.created_at]

    def cap(self, total_bytes):
        cap = self.baseline_mbps
        for gb, speed in self.tiers:
            if total_bytes >= Decimal(str(gb)) * Decimal(1000000000):
                cap = speed
        return cap


class Ledger:
    def __init__(self, path, initialize=False):
        path = Path(path)
        if not path.exists() and not initialize:
            raise ControlError('ledger missing; explicit --initialize and historical backfill required')
        path.parent.mkdir(parents=True, exist_ok=True)
        # mode=rw prevents a missing production ledger silently becoming a new zero ledger.
        mode = 'rwc' if initialize else 'rw'
        self.db = sqlite3.connect(path.resolve().as_uri() + '?mode=' + mode, uri=True)
        self.db.execute('PRAGMA synchronous=FULL')
        if initialize:
            with self.db:
                self.db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
                self.db.execute('CREATE TABLE IF NOT EXISTS samples (ts INTEGER PRIMARY KEY, bytes TEXT NOT NULL)')
        if self.db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ControlError('ledger integrity check failed')
        # Missing tables/corruption raises, never repaired or replaced automatically.
        sample_count = self.db.execute('SELECT count(*) FROM samples').fetchone()[0]
        if self.state() is None and sample_count:
            self.db.close()
            raise ControlError('ledger has samples but no resource/control state; explicit reconciliation required')
        # Additive migration for existing, valid ledgers. Never replace cloud samples
        # with invented zeros: separately record operator-reviewed stopped intervals.
        with self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS stopped_intervals ('
                            'id INTEGER PRIMARY KEY, start INTEGER NOT NULL, end INTEGER NOT NULL, '
                            'identity TEXT NOT NULL, evidence TEXT NOT NULL, recorded_at TEXT NOT NULL)')
        if self.state() is None and self.db.execute('SELECT count(*) FROM stopped_intervals').fetchone()[0]:
            self.db.close()
            raise ControlError('ledger has stopped reviews but no resource/control state; explicit reconciliation required')

    def state(self):
        row = self.db.execute('SELECT value FROM state WHERE id=1').fetchone()
        return json.loads(row[0]) if row else None

    def save(self, state):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO state VALUES (1,?)', (json.dumps(state, sort_keys=True),))

    def samples(self, start, end):
        return {ts: Decimal(value) for ts, value in self.db.execute(
            'SELECT ts,bytes FROM samples WHERE ts>? AND ts<=?', (start, end))}

    def stopped_intervals(self, c, start, end):
        records = []
        for begin, finish, identity, evidence, recorded in self.db.execute(
                'SELECT start,end,identity,evidence,recorded_at FROM stopped_intervals '
                'WHERE start<? AND end>? ORDER BY start', (end, start)):
            if json.loads(identity) != c.identity():
                raise ControlError('stopped-interval resource identity mismatch')
            records.append({'start_ms': begin, 'end_ms': finish,
                            'evidence': evidence, 'recorded_at': recorded})
        return records

    def reconciled_minutes(self, c, start, end):
        records = self.stopped_intervals(c, start, end)
        minutes = set()
        for record in records:
            minutes.update(range(max(start, record['start_ms']) + MINUTE,
                                 min(end, record['end_ms']) + 1, MINUTE))
        known = self.samples(start, end)
        if any(known.get(ts, Decimal(0)) != 0 for ts in minutes):
            raise ControlError('nonzero monitor traffic conflicts with reviewed stopped interval')
        return minutes, records

    def record_stopped_interval(self, c, beginning, ending, evidence, now, dry_run=False):
        if c.enabled or not dry_run:
            raise ControlError('stopped-interval review requires enabled=false and --dry-run')
        state = self.state()
        if not state or state['identity'] != c.identity() or state['baseline_mbps'] != c.baseline_mbps:
            raise ControlError('cannot reconcile missing or different-resource/control ledger')
        begin_time, end_time = parse_time(beginning), parse_time(ending)
        begin, finish = int(begin_time.timestamp() * 1000), int(end_time.timestamp() * 1000)
        if (begin_time.microsecond or end_time.microsecond or begin % MINUTE or finish % MINUTE
                or begin >= finish or begin_time < parse_time(c.created_at)
                or finish > int((now.timestamp() - c.settle_seconds) // 60) * MINUTE):
            raise ControlError('stopped interval must contain only past settled whole minutes after creation')
        evidence = evidence.strip() if isinstance(evidence, str) else ''
        if not evidence:
            raise ControlError('stopped interval requires an authoritative evidence reference')
        if self.stopped_intervals(c, begin, finish):
            raise ControlError('stopped interval overlaps an existing review; preserve its audit record')
        if any(value != 0 for value in self.samples(begin, finish).values()):
            raise ControlError('cannot mark observed nonzero traffic as a stopped interval')
        with self.db:
            self.db.execute('INSERT INTO stopped_intervals (start,end,identity,evidence,recorded_at) '
                            'VALUES (?,?,?,?,?)',
                            (begin, finish, json.dumps(c.identity()), evidence, now.isoformat()))

    def ingest(self, points, c, start, end):
        values = []
        stopped, _ = self.reconciled_minutes(c, start, end)
        for p in points:
            ts = p.get('timestamp')
            if type(ts) is not int or ts % MINUTE or not start < ts <= end:
                raise ControlError('invalid metric timestamp/window')
            if p.get('instanceId') != c.instance_id or p.get('ip') != c.public_ip:
                raise ControlError('metric resource mismatch')
            rate = Decimal(str(p['Average']))
            if not rate.is_finite() or rate < 0:
                raise ControlError('invalid metric Average')
            if ts in stopped and rate != 0:
                raise ControlError('nonzero monitor traffic conflicts with reviewed stopped interval')
            values.append((ts, str(rate * Decimal('7.5'))))
        with self.db:
            self.db.executemany('INSERT OR REPLACE INTO samples VALUES (?,?)', values)

    def close(self):
        self.db.close()


@contextmanager
def process_lock(state_path):
    path = Path(str(state_path) + '.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise ControlError('another controller holds the lock') from e
        yield


def validate_instance(c, instance):
    if instance.get('InstanceId') != c.instance_id or instance.get('RegionId') != c.region:
        raise ControlError('ECS identity mismatch')
    if not instance.get('CreationTime') or parse_time(instance['CreationTime']) != parse_time(c.created_at):
        raise ControlError('creation time differs from ECS; refusing incomplete historical coverage')
    if instance.get('InternetChargeType') != 'PayByTraffic':
        raise ControlError('ECS is no longer PayByTraffic')
    if instance.get('EipAddress', {}).get('AllocationId'):
        raise ControlError('EIP not supported by this fixed-public-IP controller')
    if instance.get('PublicIpAddress', {}).get('IpAddress') != [c.public_ip]:
        raise ControlError('public IP changed; manual reconciliation required')
    speed = instance.get('InternetMaxBandwidthOut')
    if type(speed) is not int or not 1 <= speed <= 100:
        raise ControlError('unexpected bandwidth, including zero; refusing automatic repair')
    return speed


def month_window(c, now):
    if now.tzinfo is None:
        raise ControlError('now must include timezone')
    local = now.astimezone(TZ)
    beginning = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = max(int(beginning.timestamp() * 1000), int(parse_time(c.created_at).timestamp() * 1000))
    # A partial creation minute is included in the next minute-end sample.
    start = start // MINUTE * MINUTE
    end = int((now.timestamp() - c.settle_seconds) // 60) * MINUTE
    return local.strftime('%Y-%m'), start, end


def adopt_current(c, ledger, cloud, now, dry_run=False, evidence=None):
    if c.enabled or not dry_run:
        raise ControlError('bandwidth adoption requires enabled=false and --dry-run')
    state = ledger.state()
    if not state or state['identity'] != c.identity():
        raise ControlError('cannot adopt missing or different-resource ledger')
    actual = validate_instance(c, cloud.describe())
    pending = state.get('pending')
    evidence = evidence.strip() if isinstance(evidence, str) else ''
    if pending and actual != pending['target'] and not evidence:
        raise ControlError('unresolved write requires authoritative outcome evidence before adoption')
    adoption_evidence = evidence or ('current bandwidth readback matches pending target' if pending else '')
    state.setdefault('bandwidth_adoptions', []).append(
        {'recorded_at': now.isoformat(), 'actual_mbps': actual,
         'previous_confirmed_mbps': state['confirmed_mbps'], 'previous_pending': pending,
         'evidence': adoption_evidence})
    state.update(confirmed_mbps=actual, pending=None, conflict=None, baseline_mbps=c.baseline_mbps)
    ledger.save(state)


def run_once(c, ledger, cloud, now, dry_run=False):
    month, start, end = month_window(c, now)
    actual = validate_instance(c, cloud.describe())
    state = ledger.state()
    if state is None:
        if ledger.db.execute('SELECT count(*) FROM samples').fetchone()[0]:
            raise ControlError('ledger has samples but no resource/control state; explicit reconciliation required')
        if ledger.db.execute('SELECT count(*) FROM stopped_intervals').fetchone()[0]:
            raise ControlError('ledger has stopped reviews but no resource/control state; explicit reconciliation required')
        state = {'identity': c.identity(), 'control_month': month, 'confirmed_mbps': actual,
                 'baseline_mbps': c.baseline_mbps, 'pending': None, 'conflict': None,
                 'review_cursor': start}
        if actual != c.baseline_mbps:
            state['conflict'] = 'initial bandwidth differs from configured baseline; adopt explicitly'
        ledger.save(state)
    if state['identity'] != c.identity() or state['baseline_mbps'] != c.baseline_mbps:
        raise ControlError('resource/baseline configuration changed; explicit review required')
    if month < state['control_month']:
        raise ControlError('clock moved backwards across month')

    pending = state.get('pending')
    if pending and actual == pending['target']:
        state.update(confirmed_mbps=actual, control_month=pending['month'], pending=None)
        ledger.save(state)
    elif actual != state['confirmed_mbps']:
        state['conflict'] = 'actual bandwidth differs from last confirmed controller value'
        ledger.save(state)

    # Fetch latest 30 minutes, then the earliest missing block. Full first-month backfill
    # is bounded by 31 daily requests. Every successful block is durably committed.
    if end > start:
        tail = max(start, end - 30 * MINUTE)
        ledger.ingest(cloud.metrics(tail, end), c, tail, end)
        expected = set(range(start + MINUTE, end + 1, MINUTE))
        known = ledger.samples(start, end)
        reconciled, reconciliations = ledger.reconciled_minutes(c, start, end)
        missing = sorted(expected - known.keys() - reconciled)
        # Try each missing daily block once; an empty response is not proof of zero use.
        queried = set()
        for ts in missing:
            block_start = start + ((ts - start - MINUTE) // (1440 * MINUTE)) * 1440 * MINUTE
            if block_start in queried:
                continue
            block_end = min(end, block_start + 1440 * MINUTE)
            ledger.ingest(cloud.metrics(block_start, block_end), c, block_start, block_end)
            queried.add(block_start)
        # Refresh old complete data too, so late corrections outside the tail are seen.
        cursor = state.get('review_cursor', start)
        if not start <= cursor < end:
            cursor = start
        review_end = min(end, cursor + 1440 * MINUTE)
        if review_end > cursor and cursor not in queried:
            ledger.ingest(cloud.metrics(cursor, review_end), c, cursor, review_end)
        state['review_cursor'] = start if review_end >= end else review_end
        known = ledger.samples(start, end)
        reconciled, reconciliations = ledger.reconciled_minutes(c, start, end)
        missing = sorted(expected - known.keys() - reconciled)
        total = sum(known.values(), Decimal(0))
        complete = not missing
    else:
        total, missing, complete = Decimal(0), [], False
        reconciled, reconciliations, known = set(), [], {}

    cap = c.cap(total)
    new_month = month > state['control_month']
    # Never raise within a managed month. A new month may restore only after complete
    # history and only while the actual bandwidth still matches our last confirmed write.
    target = cap if new_month and complete else min(actual, cap)
    status = 'ok' if complete else 'incomplete'
    report = {'month': month, 'observed_gb': float(total / Decimal(1000000000)),
              'coverage_complete': complete, 'missing_minutes': len(missing),
              'reconciled_zero_minutes': len(reconciled - known.keys()),
              'stopped_interval_reviews': reconciliations,
              'first_missing_ms': missing[0] if missing else None,
              'through_utc': datetime.fromtimestamp(max(start, end) / 1000, timezone.utc).isoformat(),
              'current_mbps': actual, 'target_mbps': target, 'action': 'none', 'status': status,
              'enabled': c.enabled, 'checked_at': now.isoformat()}
    if state.get('conflict'):
        report.update(status='conflict', action='blocked', detail=state['conflict'])
    elif state.get('pending') and (state['pending']['target'] != target or state['pending']['month'] != month):
        # An earlier request may still take effect. Do not discard it or issue a
        # different request until its target is observed or explicitly reconciled.
        report.update(status='pending', action='awaiting-prior-write',
                      detail='previous bandwidth write outcome unresolved; retain intent before changing target/month')
    elif dry_run or not c.enabled:
        report['action'] = 'dry-run' if dry_run else 'paused'
    elif target != actual:
        # Re-read immediately before a write; keep changes in time/config outside this run.
        write_now = cloud.now() if hasattr(cloud, 'now') else now
        if month_window(c, write_now)[0] != month:
            raise ControlError('month changed during collection; retry without writing')
        if validate_instance(c, cloud.describe()) != actual:
            raise ControlError('bandwidth changed during collection; retry without writing')
        if not (state.get('pending') and state['pending']['target'] == target and state['pending']['month'] == month):
            state['pending'] = {'target': target, 'from': actual, 'month': month, 'token': str(uuid.uuid4())}
        state['last_report'] = report
        ledger.save(state)  # Persist intent BEFORE cloud mutation.
        cloud.set_bandwidth(target, state['pending']['token'])
        observed = validate_instance(c, cloud.describe())
        report['current_mbps'] = observed
        if observed == target:
            state.update(confirmed_mbps=target, control_month=month, pending=None)
            report['action'] = 'applied'
        else:
            report.update(status='pending', action='awaiting-readback')
    elif complete:
        # If a new month needs no write, the current speed already equals its computed cap.
        state['control_month'] = month
        state['pending'] = None

    state['last_report'] = report
    ledger.save(state)
    return report


class AlibabaCloud:
    def __init__(self, config):
        self.c = config
        self.credentials = self._metadata_credentials()

    def now(self):
        return datetime.now(timezone.utc)

    def _metadata_credentials(self):
        # IMDSv2 only, and explicitly bypass any host HTTP proxy for link-local metadata.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        root = 'http://100.100.100.200/latest/'
        request = urllib.request.Request(root + 'api/token', data=b'', method='PUT',
            headers={'X-aliyun-ecs-metadata-token-ttl-seconds': '600'})
        try:
            with opener.open(request, timeout=5) as response:
                token = response.read().decode()
            request = urllib.request.Request(root + 'meta-data/ram/security-credentials/' + urllib.parse.quote(self.c.role_name, safe=''),
                headers={'X-aliyun-ecs-metadata-token': token})
            with opener.open(request, timeout=5) as response:
                result = json.load(response)
            if result.get('Code') != 'Success':
                raise ControlError('instance role credentials unavailable')
            return result
        except (OSError, ValueError) as e:
            raise ControlError('IMDSv2 credentials unavailable; check attached role') from e

    def rpc(self, endpoint, version, action, **params):
        creds = self.credentials
        q = dict(Action=action, Version=version, Format='JSON', AccessKeyId=creds['AccessKeyId'],
                 SecurityToken=creds['SecurityToken'], SignatureMethod='HMAC-SHA1', SignatureVersion='1.0',
                 SignatureNonce=str(uuid.uuid4()), Timestamp=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), **params)
        enc = lambda x: urllib.parse.quote(str(x), safe='~')
        canonical = '&'.join(enc(k) + '=' + enc(v) for k, v in sorted(q.items()))
        to_sign = ('POST&%2F&' + enc(canonical)).encode()
        q['Signature'] = base64.b64encode(hmac.new((creds['AccessKeySecret'] + '&').encode(), to_sign, hashlib.sha1).digest()).decode()
        request = urllib.request.Request('https://' + endpoint + '/', data=urllib.parse.urlencode(q).encode(), method='POST')
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.load(response)
        except urllib.error.HTTPError as e:
            try:
                error = json.load(e)
            except ValueError:
                error = {}
            # Never log a signed request, security token, credentials or raw exception body.
            raise ControlError(f"{action} failed: {error.get('Code', e.code)} request={error.get('RequestId', 'unknown')}") from None
        except (OSError, ValueError):
            raise ControlError(f'{action} network/response failure') from None
        if 'Code' in result and str(result['Code']) not in ('200', 'Success'):
            raise ControlError(f"{action} failed: {result['Code']}")
        return result

    def describe(self):
        result = self.rpc('ecs.' + self.c.region + '.aliyuncs.com', '2014-05-26', 'DescribeInstances',
                          RegionId=self.c.region, InstanceIds=json.dumps([self.c.instance_id]))
        items = result.get('Instances', {}).get('Instance', [])
        if len(items) != 1:
            raise ControlError('expected exactly one target ECS')
        return items[0]

    def metrics(self, start_ms, end_ms):
        params = dict(Namespace='acs_ecs_dashboard', MetricName='VPC_PublicIP_InternetOutRate', Period='60',
                      Dimensions=json.dumps([{'instanceId': self.c.instance_id, 'ip': self.c.public_ip}]),
                      StartTime=str(start_ms), EndTime=str(end_ms), Length='1440')
        points, tokens = [], set()
        while True:
            result = self.rpc('metrics.' + self.c.region + '.aliyuncs.com', '2019-01-01', 'DescribeMetricList', **params)
            if result.get('Success') is not True or str(result.get('Period')) != '60':
                raise ControlError('CloudMonitor failed or did not return 60-second data')
            points.extend(json.loads(result['Datapoints']))
            token = result.get('NextToken')
            if not token:
                return points
            if token in tokens:
                raise ControlError('CloudMonitor pagination loop')
            tokens.add(token)
            params['NextToken'] = token

    def set_bandwidth(self, target, token):
        if hasattr(self, 'config_path'):
            current = Config.from_dict(json.loads(Path(self.config_path).read_text()))
            if current != self.c or not current.enabled:
                raise ControlError('configuration changed or paused before write; retry without writing')
        if type(target) is not int or not 1 <= target <= self.c.baseline_mbps:
            raise ControlError('unsafe bandwidth target')
        return self.rpc('ecs.' + self.c.region + '.aliyuncs.com', '2014-05-26', 'ModifyInstanceNetworkSpec',
                        RegionId=self.c.region, InstanceId=self.c.instance_id, InternetMaxBandwidthOut=str(target), ClientToken=token)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--initialize', action='store_true', help='explicitly create a missing ledger')
    parser.add_argument('--dry-run', action='store_true', help='collect data without bandwidth writes')
    parser.add_argument('--adopt-current', action='store_true', help='acknowledge external bandwidth change; preserve samples')
    parser.add_argument('--verify-write', action='store_true', help='write the CURRENT speed and read back; does not test lower tiers')
    parser.add_argument('--record-stopped-interval', nargs=2, metavar=('START', 'END'),
                        help='record operator-verified zero-use whole minutes; requires paused dry-run and evidence')
    parser.add_argument('--evidence', help='authoritative stopped-interval or pending-write outcome reference; no credentials')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        c = Config.from_dict(json.loads(Path(args.config).read_text()))
        if args.record_stopped_interval:
            if c.enabled or not args.dry_run or args.adopt_current or args.verify_write or args.initialize:
                raise ControlError('stopped-interval review requires a paused existing ledger and --dry-run only')
            if not args.evidence:
                raise ControlError('stopped-interval review requires --evidence')
        elif args.evidence and not args.adopt_current:
            raise ControlError('--evidence requires --record-stopped-interval or --adopt-current')
        if args.adopt_current and (c.enabled or not args.dry_run or args.verify_write or args.initialize):
            raise ControlError('bandwidth adoption requires a paused existing ledger and --dry-run only')
        with process_lock(c.state_path):
            ledger = Ledger(c.state_path, args.initialize)
            cloud = AlibabaCloud(c)
            cloud.config_path = args.config
            if args.record_stopped_interval:
                validate_instance(c, cloud.describe())
                ledger.record_stopped_interval(c, *args.record_stopped_interval,
                                              args.evidence, datetime.now(timezone.utc), args.dry_run)
            if args.adopt_current:
                adopt_current(c, ledger, cloud, datetime.now(timezone.utc), args.dry_run, args.evidence)
            if args.verify_write:
                if not c.enabled or args.dry_run:
                    raise ControlError('write verification requires enabled=true and no dry-run')
                report = run_once(c, ledger, cloud, datetime.now(timezone.utc), dry_run=True)
                if (report['status'] != 'ok' or report['current_mbps'] != report['target_mbps']):
                    raise ControlError('write verification requires complete data and no pending bandwidth change')
                actual = validate_instance(c, cloud.describe())
                cloud.set_bandwidth(actual, str(uuid.uuid4()))
                if validate_instance(c, cloud.describe()) != actual:
                    raise ControlError('same-bandwidth write readback mismatch')
                report['action'] = 'verified-current-bandwidth'
                report['same_bandwidth_write_verified'] = True
            else:
                report = run_once(c, ledger, cloud, datetime.now(timezone.utc), args.dry_run)
            print(json.dumps(report, ensure_ascii=False, sort_keys=True))
            ledger.close()
            return 0 if report['status'] == 'ok' else 2
    except Exception as e:
        # Known ControlError messages exclude credentials; unexpected errors show type only.
        detail = str(e) if isinstance(e, ControlError) else type(e).__name__
        print(json.dumps({'status': 'error', 'detail': detail}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
