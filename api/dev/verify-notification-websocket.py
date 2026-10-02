#!/usr/bin/env python3
"""Actual notification transport, identity, revocation and delivery on synthetic data."""
import argparse
import base64
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import time
from urllib.parse import quote

from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, private_write


class Socket:
    def __init__(self, port, user):
        self.sock = socket.create_connection(('127.0.0.1', port), timeout=5)
        key = base64.b64encode(os.urandom(16)).decode()
        request = ('GET /api/websocket/' + quote(user, safe='') + ' HTTP/1.1\r\nHost: 127.0.0.1:' + str(port)
                   + '\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: ' + key + '\r\n\r\n')
        self.sock.sendall(request.encode())
        header = b''
        while not header.endswith(b'\r\n\r\n') and len(header) < 16384:
            header += self.exact(1)
        fields = {k.lower(): v.strip() for k, v in (line.split(b':', 1) for line in header.split(b'\r\n')[1:] if b':' in line)}
        accept = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        if not header.startswith(b'HTTP/1.1 101') or fields.get(b'sec-websocket-accept') != accept:
            self.sock.close()
            raise RuntimeError('Expected actual WebSocket upgrade')
        self.closed = False

    def exact(self, count):
        result = b''
        while len(result) < count:
            data = self.sock.recv(count - len(result))
            if not data:
                raise EOFError('Socket closed')
            result += data
        return result

    def send(self, value, opcode=1):
        data = value if isinstance(value, bytes) else (value if isinstance(value, str) else json.dumps(value)).encode()
        if len(data) > 16384:
            raise ValueError('Probe messages must remain small')
        mask = os.urandom(4)
        length = bytes([0x80 | len(data)]) if len(data) < 126 else bytes([0x80 | 126]) + struct.pack('!H', len(data))
        self.sock.sendall(bytes([0x80 | opcode]) + length + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def receive(self, timeout=1):
        self.sock.settimeout(timeout)
        try:
            first, second = self.exact(2)
            length = second & 0x7f
            if length == 126:
                length = struct.unpack('!H', self.exact(2))[0]
            if second & 0x80 or length == 127 or length > 16384 or not first & 0x80:
                raise RuntimeError('Unexpected server frame')
            data = self.exact(length)
            if first & 0xf == 8:
                self.closed = True
                return {'close': struct.unpack('!H', data[:2])[0] if len(data) >= 2 else 1005}
            if first & 0xf == 1:
                return json.loads(data)
            return {'opcode': first & 0xf}
        except socket.timeout:
            return None
        except (EOFError, ConnectionResetError):
            self.closed = True
            return {'closed': True}

    def close(self):
        try:
            if not self.closed:
                self.send(struct.pack('!H', 1000), opcode=8)
                self.receive(.5)
        except OSError:
            pass
        finally:
            self.sock.close()


def verify(args):
    cases = []
    def check(name, passed):
        cases.append({'case': name, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)

    with FixtureApi(args.runtime, args.jar) as api, ExitStack() as stack:
        before, files = database_inventory(api.runtime), file_inventory(api.runtime / 'uploads')
        process = json.loads((api.runtime / 'backend-process.json').read_text())
        log = Path(process['log_path']); offset = log.stat().st_size
        for actor in ('admin', 'student_a', 'student_b', 'teacher_a'):
            api.login(actor)

        def connect(user='fixture_student_a', actor=None, raw_token=None):
            ws = Socket(api.ports['backend'], user)
            stack.callback(ws.close)
            if actor or raw_token is not None:
                ws.send({'type': 'authenticate', 'token': raw_token if raw_token is not None else api.tokens[actor]})
                reply = ws.receive()
                return ws, reply
            return ws

        serial = 0
        def send(actor='admin', target='fixture_student_a', broadcast=False):
            nonlocal serial
            serial += 1
            marker = 'fixture-notification-private-' + str(serial)
            status, body, _ = api.request('POST', '/webSocketApi/' + ('sendAll' if broadcast else 'sendUser'), actor,
                                          {'userId': target, 'message': marker})
            return marker, status == 200 and body and body.get('success') is True

        def received(ws, marker):
            body = ws.receive(.35)
            return isinstance(body, dict) and body.get('msgTxt') == marker

        try:
            anonymous = connect()
            marker, ok = send()
            check('administrator can send a targeted notification', ok)
            check('anonymous path identity delivery matches expected boundary', received(anonymous, marker) == args.expect_legacy)
            anonymous.close()

            wrong, reply = connect(actor='student_b')
            check('cross-user authentication rejected', (reply or {}).get('close') == 1008 if not args.expect_legacy else (reply or {}).get('cmd') == 'heartcheck')
            marker, _ = send()
            check('other account cannot receive target private notification', received(wrong, marker) == args.expect_legacy)
            wrong.close()

            invalid, reply = connect(raw_token='fixture-invalid-notification-token')
            check('invalid token rejected', (reply or {}).get('close') == 1008 if not args.expect_legacy else (reply or {}).get('cmd') == 'heartcheck')
            invalid.close()

            first, reply = connect(actor='student_a')
            check('owner authentication response', (reply or {}).get('cmd') == ('heartcheck' if args.expect_legacy else 'authenticated'))
            second, reply = connect(actor='student_a')
            check('second owner connection authenticates', (reply or {}).get('cmd') == ('heartcheck' if args.expect_legacy else 'authenticated'))
            other, reply = connect(user='fixture_student_b', actor='student_b')
            check('other owner authenticates separately', (reply or {}).get('cmd') == ('heartcheck' if args.expect_legacy else 'authenticated'))
            marker, _ = send()
            check('first owner tab receives targeted notification', received(first, marker) != args.expect_legacy)
            check('second owner tab receives targeted notification', received(second, marker))
            check('targeted notification does not reach other owner', not received(other, marker))
            second.close()
            marker, _ = send()
            check('closing one tab preserves other owner connection', received(first, marker) != args.expect_legacy)

            for broadcast in (False, True):
                marker, allowed = send(actor=None, target='fixture_student_b', broadcast=broadcast)
                check('anonymous HTTP sender denied ' + str(broadcast), not allowed)
                check('anonymous HTTP send has no delivery ' + str(broadcast), not received(other, marker))

            for actor in ('student_a', 'student_b', 'teacher_a'):
                # Use the other active recipient so sender identity cannot hide delivery.
                marker, allowed = send(actor=actor, target='fixture_student_b')
                check(actor + ' direct test sending restricted to administrators', bool(allowed) == args.expect_legacy)
                check(actor + ' rejected direct send has no delivery', received(other, marker) == args.expect_legacy)
                marker, allowed = send(actor=actor, broadcast=True)
                check(actor + ' test broadcast restricted to administrators', bool(allowed) == args.expect_legacy)
                check(actor + ' rejected broadcast has no delivery', received(other, marker) == args.expect_legacy)
                if args.expect_legacy:
                    first.receive(.35)  # Legacy broadcasts also reach the first tab.
            marker, ok = send(broadcast=True)
            check('administrator broadcast succeeds', ok)
            check('administrator broadcast reaches owner', received(first, marker))
            check('administrator broadcast reaches other authenticated owner', received(other, marker))

            first.send('HeartBeat')
            check('authenticated heartbeat remains compatible', (first.receive() or {}).get('cmd') == 'heartcheck')
            api.request('GET', '/sys/logout', 'student_b')
            marker, _ = send(target='fixture_student_b')
            reply = other.receive(.5)
            check('logged-out token no longer receives notifications', ((reply or {}).get('msgTxt') == marker) == args.expect_legacy)
            if not args.expect_legacy:
                check('revoked receiver closes with policy code', (reply or {}).get('close') == 1008)
                first.send({'type': 'authenticate', 'token': api.tokens['admin']})
                check('authenticated socket cannot switch identity', (first.receive() or {}).get('close') == 1008)
                malformed = connect(); malformed.send('{bad-json')
                check('malformed first frame closes safely', (malformed.receive() or {}).get('close') == 1008)
                heartbeat = connect(); heartbeat.send('HeartBeat')
                check('heartbeat does not authenticate an anonymous socket', (heartbeat.receive() or {}).get('close') == 1008)
                forged = api.tokens['student_a'][:-1] + ('A' if api.tokens['student_a'][-1] != 'A' else 'B')
                altered, reply = connect(raw_token=forged)
                check('altered credential cannot authenticate a known user ID', (reply or {}).get('close') == 1008)
                altered.close()
                api.login('student_b')
                fresh, reply = connect(user='fixture_student_b', actor='student_b')
                check('new login can authenticate again', (reply or {}).get('cmd') == 'authenticated')
                marker, _ = send(target='fixture_student_b')
                check('new login receives its own notification', received(fresh, marker))
            time.sleep(.1)
            captured = log.read_bytes()[offset:]
            check('notification content logging matches expected privacy boundary', (b'fixture-notification-private-' in captured) == args.expect_legacy)
            check('active credentials absent from ordinary notification logs', all(token.encode() not in captured for token in api.tokens.values()))
        finally:
            stack.close()
        after = database_inventory(api.runtime)
        check('all non-audit-log database tables unchanged', all(before[t] == after[t] for t in before if t != 'sys_log'))
        check('all original attachment bytes unchanged', file_inventory(api.runtime / 'uploads') == files)
        result = {'jar_sha256': api.jar_sha256, 'expected_legacy': args.expect_legacy, 'cases': cases,
                  'passed': sum(c['passed'] for c in cases), 'total': len(cases),
                  'scope': 'Actual local synthetic WebSocket and HTTP notification delivery; no external or real-user messages. Notification endpoint only, not Scratch cloud data or all announcement REST authorization.'}
    private_write(args.output, json.dumps(result, indent=2) + '\n')
    return result['passed'] == result['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
