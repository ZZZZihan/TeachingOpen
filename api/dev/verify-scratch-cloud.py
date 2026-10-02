#!/usr/bin/env python3
"""Real Scratch cloud protocol, restricted to disposable synthetic projects."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import time
from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, private_write, sql

spec = importlib.util.spec_from_file_location('notification_probe', Path(__file__).with_name('verify-notification-websocket.py'))
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
PREFIX = 'fixture_cloud_probe_'


class CloudSocket(base.Socket):
    def __init__(self, port, project, token=None):
        self.sock = socket.create_connection(('127.0.0.1', port), timeout=5)
        self.closed = False; self.project = project; self.token = token
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(('GET /api/websocket/scratch/cloudData HTTP/1.1\r\nHost: 127.0.0.1:' + str(port)
                           + '\r\nOrigin: http://127.0.0.1:' + str(port) + '\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: ' + key + '\r\n\r\n').encode())
        header = b''
        while not header.endswith(b'\r\n\r\n') and len(header) < 16384: header += self.exact(1)
        fields = {k.lower(): v.strip() for k, v in (line.split(b':', 1) for line in header.split(b'\r\n')[1:] if b':' in line)}
        expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        if not header.startswith(b'HTTP/1.1 101') or fields.get(b'sec-websocket-accept') != expected:
            self.sock.close(); raise RuntimeError('Cloud upgrade failed')

    def command(self, method, **fields):
        data = dict(method=method, project_id=self.project, user='untrusted-client-display-name', **fields)
        if self.token is not None: data['token'] = self.token
        self.send(json.dumps(data) + '\n')

    def receive(self, timeout=.2):
        self.sock.settimeout(timeout)
        try:
            first, second = self.exact(2); length = second & 0x7f
            if length == 126: length = struct.unpack('!H', self.exact(2))[0]
            if second & 0x80 or length == 127 or length > 16384: raise RuntimeError('Unexpected cloud frame')
            raw = self.exact(length)
            if first & 15 == 8:
                self.closed = True; return [{'close': struct.unpack('!H', raw[:2])[0] if len(raw) >= 2 else 1005}]
            if first & 15 == 1: return [json.loads(line) for line in raw.splitlines() if line]
            return []
        except socket.timeout: return []
        except (EOFError, ConnectionResetError): self.closed = True; return [{'closed': True}]

    def drain(self, timeout=.12):
        result = []
        while True:
            batch = self.receive(timeout)
            if not batch: break
            result.extend(batch)
            if self.closed: break
        return result


def verify(args):
    cases = []
    def check(name, condition):
        cases.append({'case': name, 'passed': bool(condition)})
        print(('PASS ' if condition else 'FAIL ') + name, flush=True)
    def has(messages, **fields): return any(all(m.get(k) == v for k, v in fields.items()) for m in messages)
    with FixtureApi(args.runtime, args.jar) as api, ExitStack() as stack:
        before, files = database_inventory(api.runtime), file_inventory(api.runtime / 'uploads')
        cloud_before = {key: api.cache('HGETALL', key) for key in api.cache('KEYS', 'scratch:cloud:*').splitlines()}
        if sql(api.runtime, "SELECT COUNT(*) FROM teachingopen_dev.teaching_work WHERE id LIKE 'fixture_cloud_probe_%'") != '0' or any(PREFIX in key for key in cloud_before):
            raise RuntimeError('Probe data already exists; preserve and inspect it')
        process = json.loads((api.runtime / 'backend-process.json').read_text()); log = Path(process['log_path']); offset = log.stat().st_size
        for actor in ('admin', 'student_a', 'student_b', 'teacher_a', 'teacher_b'): api.login(actor)
        tokens = list(api.tokens.values())
        ids = {kind: PREFIX + kind for kind in ('private', 'public', 'other', 'deleted', 'wrongtype', 'capacity')}
        def key(project): return 'scratch:cloud:' + project
        def value(project, name='score'): return api.cache('HGET', key(project), name)
        def connect(project='private', actor=None, handshake=True):
            project = ids.get(project, project)
            ws = CloudSocket(api.ports['frontend'], project, api.tokens.get(actor) if actor else None); stack.callback(ws.close)
            if handshake: ws.command('handshake'); return ws, ws.drain()
            return ws
        try:
            for kind, project in ids.items():
                owner = 'fixture_student_b' if kind == 'other' else 'fixture_student_a'
                depart = 'fixture_class_b' if kind == 'other' else 'fixture_class_a'
                sql(api.runtime, "INSERT INTO teachingopen_dev.teaching_work (id,create_by,create_time,work_file,user_id,depart_id,work_name,work_type,work_status,del_flag,work_scene) VALUES ('" + project + "','fixture_admin','2026-10-03 07:00:00','fixture_file_a','" + owner + "','" + depart + "','合成云变量作品','" + ('5' if kind == 'wrongtype' else '2') + "','" + ('3' if kind == 'public' else '0') + "'," + ('1' if kind == 'deleted' else '0') + ",'create')")
                api.cache('HSET', key(project), 'score', json.dumps('fixture-cloud-private-value'))
            if args.expect_legacy:
                anonymous, messages = connect(); check('legacy anonymous reads private values', has(messages, value='fixture-cloud-private-value'))
                other, messages = connect(actor='student_b'); check('legacy other student reads private values', has(messages, value='fixture-cloud-private-value'))
                teacher, messages = connect(actor='teacher_b'); check('legacy cross-class teacher reads private values', has(messages, value='fixture-cloud-private-value'))
                direct = connect(handshake=False); direct.command('set', name='score', value='anonymous-write'); time.sleep(.1)
                check('legacy anonymous writes without handshake', value(ids['private']) == json.dumps('anonymous-write'))
                missing = connect(PREFIX + 'missing', handshake=False); missing.command('set', name='score', value='orphan'); time.sleep(.1)
                check('legacy nonexistent project accepts writes', value(PREFIX + 'missing') == json.dumps('orphan'))
                owner, _ = connect(actor='student_a'); owner.command('create', name='created', value='1')
                check('legacy owner create fails due service bean lookup', has(owner.drain(), reply='FAIL') and not value(ids['private'], 'created'))
                api.request('GET', '/sys/logout', 'student_a')
                owner.drain(); direct.command('set', name='score', value='after-logout'); time.sleep(.1)
                check('legacy logged-out receiver still receives', has(owner.drain(), value='after-logout'))
                anonymous.drain(); anonymous.project = ids['other']; anonymous.command('handshake'); anonymous.drain()
                direct.command('set', name='score', value='stale-subscription')
                check('legacy project switch leaves old subscription', has(anonymous.drain(), value='stale-subscription'))
                deleted, messages = connect('deleted'); check('legacy deleted work values readable', has(messages, value='fixture-cloud-private-value'))
            else:
                for actor in (None, 'student_b', 'teacher_b'):
                    ws, messages = connect(actor=actor)
                    check('private read denied ' + str(actor), has(messages, close=1008) and not has(messages, method='set'))
                for project in ('deleted', 'wrongtype', PREFIX + 'missing', 'create', 'https://example.invalid/work.sb3'):
                    ws, messages = connect(project, 'student_a')
                    check('invalid/unavailable project denied ' + project, has(messages, close=1008))
                for actor in ('student_a', 'teacher_a', 'admin'):
                    ws, messages = connect(actor=actor)
                    check('private read allowed ' + actor, has(messages, reply='OK') and has(messages, value='fixture-cloud-private-value'))
                    ws.close()
                direct = connect(actor='student_a', handshake=False); direct.command('set', name='score', value='no-handshake')
                check('mutation before handshake denied without write', has(direct.drain(), close=1008) and value(ids['private']) == json.dumps('fixture-cloud-private-value'))
                anonymous, messages = connect('public'); check('anonymous published project is readable', has(messages, reply='OK') and has(messages, method='set'))
                anonymous.command('set', name='score', value='bad-anonymous')
                check('anonymous public mutation denied without write', has(anonymous.drain(), reply='FAIL') and value(ids['public']) == json.dumps('fixture-cloud-private-value'))
                owner, _ = connect('public', 'student_a'); peer, _ = connect('public', 'student_b'); second, _ = connect('public', 'student_a')
                peer.command('set', name='score', value='17'); response = peer.drain()
                check('authorized player updates existing shared variable', has(response, reply='OK') and value(ids['public']) == json.dumps('17'))
                check('both owner tabs receive shared update', has(owner.drain(), value='17') and has(second.drain(), value='17'))
                check('anonymous reader keeps receiving but cannot write', has(anonymous.drain(), value='17'))
                second.close(); peer.command('set', name='score', value='18'); peer.drain()
                check('closing one owner tab preserves other subscription', has(owner.drain(), value='18'))
                anonymous.drain()
                for method, fields in [('create', {'value':'1'}), ('delete', {}), ('rename', {'new_name':'hijacked'}), ('set', {'name':'missing','value':'1'})]:
                    snapshot = api.cache('HGETALL', key(ids['public']))
                    peer.command(method, **dict({'name':'score'}, **fields))
                    check('non-owner schema operation denied ' + method, has(peer.drain(), reply='FAIL') and api.cache('HGETALL', key(ids['public'])) == snapshot)
                owner.command('create', name='created', value=123); reply=owner.drain()
                check('owner creates real Redis variable', has(reply, reply='OK') and value(ids['public'],'created') == json.dumps('123'))
                peer.drain(); anonymous.drain()
                owner.command('create', name='created', value=999); reply=owner.drain()
                check('duplicate create preserves current shared value', has(reply, reply='OK') and value(ids['public'],'created') == json.dumps('123'))
                owner.command('rename', name='created', new_name='renamed'); reply=owner.drain()
                check('owner rename preserves value and removes old field', has(reply, reply='OK') and not value(ids['public'],'created') and value(ids['public'],'renamed') == json.dumps('123'))
                owner.command('rename', name='renamed', new_name='score'); reply=owner.drain()
                check('rename collision preserves both variables', has(reply, reply='FAIL') and value(ids['public'],'renamed') == json.dumps('123') and value(ids['public']) == json.dumps('18'))
                owner.command('delete', name='renamed'); reply=owner.drain()
                check('owner deletes variable', has(reply, reply='OK') and not value(ids['public'],'renamed'))
                switched, _ = connect('public', 'student_a'); switched.project=ids['private']; switched.command('handshake')
                check('project switch requires new connection', has(switched.drain(), close=1008))
                changed, _ = connect('public', 'student_a'); changed.token=api.tokens['student_b']; changed.command('set', name='score', value='changed-token')
                check('identity switch rejected without write', has(changed.drain(), close=1008) and value(ids['public']) == json.dumps('18'))
                invalid = connect('public', handshake=False); invalid.token='invalid-fixture-cloud-token'; invalid.command('handshake')
                check('invalid supplied token cannot downgrade to anonymous', has(invalid.drain(), close=1008))
                # Retraction is checked both before receiving a broadcast and on a mutation.
                sql(api.runtime, "UPDATE teachingopen_dev.teaching_work SET work_status='0' WHERE id='"+ids['public']+"'")
                owner.command('set', name='score', value='private-again'); owner.drain()
                check('withdrawal stops anonymous and other-user receivers', has(anonymous.drain(), close=1008) and has(peer.drain(), close=1008))
                private_peer, _ = connect('private','teacher_a')
                sql(api.runtime, "UPDATE teachingopen_dev.teaching_work SET depart_id='fixture_class_b' WHERE id='"+ids['private']+"'")
                actor, _ = connect('private','student_a'); actor.command('set',name='score',value='class-changed'); actor.drain()
                check('class reassignment stops former teacher receiver',has(private_peer.drain(),close=1008))
                api.request('GET','/sys/logout','student_a'); actor.command('set',name='score',value='logged-out')
                check('logout rejects subsequent writes',has(actor.drain(),close=1008) and value(ids['private'])==json.dumps('class-changed'))
                api.login('student_a'); tokens.append(api.tokens['student_a'])
                # Data-operation error fails closed, then a new connection can retry.
                failure, _=connect('private','student_a'); old=value(ids['private']);api.cache('DEL',key(ids['private']));api.cache('SET',key(ids['private']),'fixture-wrong-type')
                failure.command('set',name='score',value='not-written')
                check('Redis wrong-type failure closes without replacing data',has(failure.drain(),close=1011) and api.cache('GET',key(ids['private']))=='fixture-wrong-type')
                api.cache('DEL',key(ids['private']));api.cache('HSET',key(ids['private']),'score',old)
                recovered,messages=connect('private','student_a');recovered.command('set',name='score',value='recovered');response=recovered.drain()
                check('retry after Redis repair succeeds',has(messages,reply='OK') and has(response,reply='OK') and value(ids['private'])==json.dumps('recovered'))
                for label, payload in [('malformed','{invalid'),('object value',{'method':'set','name':'score','value':{'x':1}}),('long name',{'method':'set','name':'n'*129,'value':'1'}),('long value',{'method':'set','name':'score','value':'v'*1025})]:
                    bad,_=connect('private','student_a'); previous=value(ids['private'])
                    if isinstance(payload,str):bad.send(payload)
                    else:bad.command(payload.pop('method'),**payload)
                    check('invalid payload denied '+label,has(bad.drain(),close=1008) and value(ids['private'])==previous)
                # Concurrent rename uses separate sockets; only one destination can win.
                race1,_=connect('capacity','student_a');race2,_=connect('capacity','student_a')
                with ThreadPoolExecutor(max_workers=2) as pool:
                    list(pool.map(lambda pair:pair[0].command('rename',name='score',new_name=pair[1]),[(race1,'winner1'),(race2,'winner2')]))
                replies=race1.drain()+race2.drain()
                check('concurrent rename has exactly one winner and no lost value',sum(m.get('reply')=='OK' for m in replies)==1 and api.cache('HLEN',key(ids['capacity']))=='1' and not value(ids['capacity'],'score'))
                race1.close();race2.close();api.cache('DEL',key(ids['capacity']))
                capacity,_=connect('capacity','student_a')
                for i in range(64):capacity.command('create',name='v'+str(i),value=i);capacity.drain(.01)
                capacity.command('create',name='overflow',value='1');reply=capacity.drain()
                check('variable count is bounded without partial extra write',has(reply,reply='FAIL') and api.cache('HLEN',key(ids['capacity']))=='64' and not value(ids['capacity'],'overflow'))
                capacity.command('set',name='v0',value='updated');reply=capacity.drain()
                check('existing variable update still works at capacity',has(reply,reply='OK') and value(ids['capacity'],'v0')==json.dumps('updated'))
                again,messages=connect('capacity','student_a')
                check('complete bounded snapshot returned on reconnect',sum(m.get('method')=='set' for m in messages)==64 and has(messages,reply='OK'))
                check('temporary project IDs do not create orphan storage',api.cache('EXISTS',key('create'))==('1' if key('create') in cloud_before else '0') and api.cache('EXISTS',key(PREFIX+'missing'))=='0')
            captured=log.read_bytes()[offset:]
            check('raw cloud credential logging matches expected boundary',any(t.encode() in captured for t in tokens)==args.expect_legacy)
            check('raw cloud value logging matches expected boundary',(b'fixture-cloud-private-value' in captured or b'anonymous-write' in captured)==args.expect_legacy)
        finally:
            stack.close()
            for cache_key in api.cache('KEYS','scratch:cloud:'+PREFIX+'*').splitlines():api.cache('DEL',cache_key)
            sql(api.runtime,"DELETE FROM teachingopen_dev.teaching_work WHERE id LIKE 'fixture_cloud_probe_%'")
        after=database_inventory(api.runtime)
        check('all non-audit database tables restored',all(before[t]==after[t] for t in before if t!='sys_log'))
        check('all attachment bytes unchanged',files==file_inventory(api.runtime/'uploads'))
        check('all original cloud keys and values unchanged',{k:api.cache('HGETALL',k) for k in api.cache('KEYS','scratch:cloud:*').splitlines()}==cloud_before)
        result={'jar_sha256':api.jar_sha256,'expected_legacy':args.expect_legacy,'cases':cases,'passed':sum(c['passed'] for c in cases),'total':len(cases),'scope':'Real Java/Redis/MySQL via local same-origin WebSocket, synthetic projects and CLI login only; not browser or shipped editor acceptance'}
    private_write(args.output,json.dumps(result,indent=2)+'\n')
    return result['passed']==result['total']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--jar',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--expect-legacy',action='store_true')
    raise SystemExit(0 if verify(p.parse_args()) else 1)
