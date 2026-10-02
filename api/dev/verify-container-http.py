#!/usr/bin/env python3
"""Small multipart boundary and WebSocket transport probes on synthetic data."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import struct
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, private_write, sql


PREFIX = 'fixture-container-probe'


def verify(args):
    cases = []

    def check(name, passed):
        cases.append({'case': name, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)

    with FixtureApi(args.runtime, args.jar) as api:
        folder = api.runtime / 'uploads' / PREFIX
        if folder.exists() or sql(api.runtime, "SELECT COUNT(*) FROM teachingopen_dev.sys_file WHERE file_path LIKE '" + PREFIX + "/%'") != '0':
            raise RuntimeError('Container probe files already exist')
        before, files = database_inventory(api.runtime), file_inventory(api.runtime / 'uploads')
        folder.mkdir()
        try:
            api.login('student_a')

            def upload(parts=2, extra_header=0):
                boundary = 'bounded-container-probe'
                body = ('--' + boundary + '\r\nContent-Disposition: form-data; name="biz"\r\n\r\n' + PREFIX + '\r\n').encode()
                for i in range(parts - 2):
                    body += ('--' + boundary + '\r\nContent-Disposition: form-data; name="field' + str(i) + '"\r\n\r\nx\r\n').encode()
                body += ('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="probe.txt"\r\nContent-Type: text/plain\r\n').encode()
                if extra_header:
                    body += b'X-Probe: ' + b'x' * extra_header + b'\r\n'
                body += b'\r\ncontainer probe\r\n' + ('--' + boundary + '--\r\n').encode()
                assert len(body) < 10000
                request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api/sys/common/upload', body,
                                  {'Content-Type': 'multipart/form-data; boundary=' + boundary,
                                   'X-Access-Token': api.tokens['student_a']})
                try:
                    response = urlopen(request, timeout=15)
                except HTTPError as error:
                    response = error
                with response:
                    payload = json.loads(response.read())
                    return response.status, payload

            for label, parts, header in [('normal', 2, 0), ('part count', 60, 0), ('part header', 2, 600), ('recovery', 2, 0)]:
                previous_files = file_inventory(folder)
                previous_count = sql(api.runtime, "SELECT COUNT(*) FROM teachingopen_dev.sys_file WHERE file_path LIKE '" + PREFIX + "/%'")
                status, body = upload(parts, header)
                allowed = label in ('normal', 'recovery') or args.expect_legacy
                if allowed:
                    key = body.get('message', '')
                    path = (api.runtime / 'uploads' / key).resolve()
                    check(label + ' multipart succeeds with exact bytes', status == 200 and body.get('success') is True
                          and path.is_relative_to(folder) and path.is_file() and path.read_bytes() == b'container probe')
                else:
                    check(label + ' multipart rejected before file/record writes', body.get('success') is False
                          and file_inventory(folder) == previous_files and sql(api.runtime, "SELECT COUNT(*) FROM teachingopen_dev.sys_file WHERE file_path LIKE '" + PREFIX + "/%'") == previous_count)

            def recv_exact(sock, size):
                data = b''
                while len(data) < size:
                    block = sock.recv(size - len(data))
                    if not block:
                        raise RuntimeError('WebSocket closed before frame completed')
                    data += block
                return data

            def send_frame(sock, opcode, data):
                assert len(data) < 126
                mask = os.urandom(4)
                sock.sendall(bytes([0x80 | opcode, 0x80 | len(data)]) + mask
                             + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

            def frame(sock):
                first, second = recv_exact(sock, 2)
                if second & 0x80 or second & 0x7f > 125:
                    raise RuntimeError('Unexpected server control frame')
                return first & 0xf, recv_exact(sock, second & 0x7f)

            # No application message, account subscription or cloud-data write.
            # This checks the container protocol, not application authorization.
            with socket.create_connection(('127.0.0.1', api.ports['backend']), timeout=10) as sock:
                key = base64.b64encode(os.urandom(16)).decode()
                sock.sendall(('GET /api/websocket/scratch/cloudData HTTP/1.1\r\nHost: 127.0.0.1:' + str(api.ports['backend'])
                              + '\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: ' + key + '\r\n\r\n').encode())
                headers = b''
                while not headers.endswith(b'\r\n\r\n') and len(headers) < 16384:
                    headers += recv_exact(sock, 1)
                expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
                check('WebSocket upgrade has HTTP 101 and matching accept', headers.startswith(b'HTTP/1.1 101') and b'sec-websocket-accept: ' + expected.lower() in headers.lower())
                send_frame(sock, 9, b'container-probe')
                check('WebSocket masked ping receives matching pong', frame(sock) == (10, b'container-probe'))
                send_frame(sock, 8, struct.pack('!H', 1000))
                opcode, payload = frame(sock)
                check('WebSocket close handshake completes', opcode == 8 and payload[:2] == struct.pack('!H', 1000))
            jar_hash = api.jar_sha256
        finally:
            sql(api.runtime, "DELETE FROM teachingopen_dev.sys_file WHERE file_path LIKE '" + PREFIX + "/%'")
            shutil.rmtree(folder)
        after = database_inventory(api.runtime)
        check('all non-audit-log tables restored', all(before[t] == after[t] for t in before if t != 'sys_log'))
        check('all original attachment bytes unchanged', file_inventory(api.runtime / 'uploads') == files)
    result = {'jar_sha256': jar_hash, 'expected_legacy': args.expect_legacy, 'cases': cases,
              'passed': sum(x['passed'] for x in cases), 'total': len(cases),
              'scope': 'Bounded multipart inputs below 10 KB and actual WebSocket protocol on synthetic localhost. Not a CVE exploit test, WebSocket authorization, HTTP/2, TLS or load test.'}
    private_write(args.output, json.dumps(result, indent=2) + '\n')
    return result['passed'] == result['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--jar', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
