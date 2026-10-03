"""Local transport fault checks; the backend here is a controlled TCP fixture."""
import base64
from contextlib import contextmanager
import hashlib
from http.client import parse_headers
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

spec = importlib.util.spec_from_file_location('frontend_proxy', Path(__file__).with_name('serve-frontend.py'))
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)
KEY = base64.b64encode(b'0123456789abcdef').decode()


def exact(conn, size):
    result = bytearray()
    while len(result) < size:
        chunk = conn.recv(size - len(result))
        if not chunk:
            raise EOFError('Transport closed')
        result.extend(chunk)
    return bytes(result)


def head(conn):
    result = b''
    while not result.endswith(b'\r\n\r\n'):
        result += exact(conn, 1)
    return result


class Backend(BaseHTTPRequestHandler):
    rbufsize = 0

    def ordinary_response(self):
        status, headers, body = self.server.http_response
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def do_HEAD(self):
        self.server.requests.append((self.path, dict(self.headers)))
        self.server.head_requests.append((self.path, dict(self.headers)))
        self.ordinary_response()

    def do_GET(self):
        self.server.requests.append((self.path, dict(self.headers)))
        if not self.headers.get('Upgrade'):
            self.ordinary_response()
            return
        mode = self.server.mode
        if mode == 'unresponsive':
            time.sleep(.5)
            return
        if mode == 'refuse':
            self.send_error(403)
            return
        if mode == 'huge':
            self.connection.sendall(b'HTTP/1.1 101 Switching Protocols\r\nX-Large: ' + b'x' * 34000)
            return
        accept = base64.b64encode(hashlib.sha1((self.headers['Sec-WebSocket-Key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        if mode == 'invalid':
            accept = 'wrong'
        handshake = ('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept
                     + '\r\nSec-WebSocket-Protocol: fixture\r\n\r\n').encode()
        self.connection.sendall(handshake + (b'\x81\x02ok' if mode == 'early' else b''))
        if mode == 'disconnect':
            return
        self.connection.settimeout(2)
        try:
            while True:
                data = self.connection.recv(4096)
                if not data:
                    break
                self.connection.sendall(data)
        except OSError:
            pass
        finally:
            self.server.disconnected.set()

    def do_POST(self):
        remaining = int(self.headers['Content-Length'])
        chunks = []
        while remaining:
            chunk = self.rfile.read(remaining)
            if not chunk:
                return
            remaining -= len(chunk)
            chunks.append(chunk)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b''.join(chunks))

    def log_message(self, *args):
        pass


class FrontendProxyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        Path(self.tmp.name, 'index.html').write_bytes(b'fixture index')
        self.backend = ThreadingHTTPServer(('127.0.0.1', 0), Backend)
        self.backend.mode = 'echo'
        self.backend.requests = []
        self.backend.head_requests = []
        self.backend.http_response = (200, [('Set-Cookie', 'fixture=one; HttpOnly'),
                                           ('Set-Cookie', 'fixture2=two; HttpOnly')], b'ordinary response')
        self.backend.disconnected = threading.Event()
        handler = type('FixtureProxy', (proxy.LocalFrontend,), {'websocket_timeout': .2, 'websocket_idle_timeout': .3})
        self.handler = handler
        self.frontend = ThreadingHTTPServer(('127.0.0.1', 0), lambda *a, **kw: handler(*a, directory=self.tmp.name, **kw))
        handler.ports = {'frontend': self.frontend.server_port, 'backend': self.backend.server_port}
        for server in (self.backend, self.frontend):
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
            thread.start()
            self.addCleanup(lambda s=server, t=thread: (s.shutdown(), s.server_close(), t.join(2)))

    @contextmanager
    def connect(self, overrides=None, path='/api/websocket/fixture', method='GET', early=b''):
        headers = {'Host': '127.0.0.1:' + str(self.frontend.server_port), 'Connection': 'keep-alive, Upgrade',
                   'Upgrade': 'websocket', 'Sec-WebSocket-Version': '13', 'Sec-WebSocket-Key': KEY,
                   'Origin': 'http://127.0.0.1:' + str(self.frontend.server_port), 'Sec-WebSocket-Protocol': 'fixture'}
        headers.update(overrides or {})
        request = method + ' ' + path + ' HTTP/1.1\r\n' + ''.join(k + ': ' + v + '\r\n' for k, v in headers.items() if v is not None) + '\r\n'
        with socket.create_connection(('127.0.0.1', self.frontend.server_port), timeout=2) as conn:
            conn.sendall(request.encode() + early)
            yield conn, head(conn)

    def assert_local_csp(self, headers):
        policies = headers.get_all('Content-Security-Policy', [])
        self.assertEqual(len(policies), 1)
        directives = {}
        for value in policies[0].split(';'):
            name, *sources = value.split()
            self.assertNotIn(name, directives)
            directives[name] = set(sources)
        # Read from a served response: workers get blob support, while ordinary
        # scripts and connections retain the local-only isolation contract.
        self.assertEqual(directives, {
            'default-src': {"'self'", 'data:', 'blob:'},
            'script-src': {"'self'", "'unsafe-inline'", "'unsafe-eval'"},
            'worker-src': {"'self'", 'blob:'},
            'style-src': {"'self'", "'unsafe-inline'"},
            'connect-src': {"'self'"},
        })

    def http_response(self, method, path, headers=None):
        # HTTP clients discard HEAD bodies themselves. Read raw TCP through EOF
        # so an accidental proxy body write cannot pass this check unnoticed.
        fields = {'Host': '127.0.0.1:' + str(self.frontend.server_port), 'Connection': 'close'}
        fields.update(headers or {})
        request = method + ' ' + path + ' HTTP/1.1\r\n' + ''.join(k + ': ' + v + '\r\n' for k, v in fields.items()) + '\r\n'
        with socket.create_connection(('127.0.0.1', self.frontend.server_port), timeout=2) as conn:
            conn.sendall(request.encode('ascii'))
            response = head(conn)
            body = bytearray()
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                body.extend(chunk)
        status_line, fields = response.split(b'\r\n', 1)
        return int(status_line.split()[1]), parse_headers(io.BytesIO(fields)), bytes(body)

    def test_api_head_preserves_representation_headers_without_body(self):
        body = bytes(range(256)) * 17
        self.backend.http_response = (200, [
            ('Content-Type', 'image/png'), ('Content-Length', str(len(body))),
            ('Accept-Ranges', 'bytes'), ('ETag', '"fixture-media"'),
            ('Last-Modified', 'Thu, 01 Oct 2026 00:00:00 GMT'),
            ('Content-Disposition', 'inline; filename="fixture.png"'),
            ('Set-Cookie', 'fixture=one; HttpOnly'), ('Set-Cookie', 'fixture2=two; HttpOnly'),
        ], body)
        path = '/api/sys/common/static/%E4%B8%AD%E6%96%87.png?fixture=1'
        get_status, get_headers, get_body = self.http_response('GET', path)
        status, headers, head_body = self.http_response('HEAD', path, {
            'X-Access-Token': 'fixture-token', 'Cookie': 'fixture=session', 'Accept-Encoding': 'gzip',
        })
        self.assertEqual((status, get_status), (200, 200))
        self.assertEqual(get_body, body)
        self.assertEqual(head_body, b'')
        for name in ('Content-Type', 'Content-Length', 'Accept-Ranges', 'ETag', 'Last-Modified', 'Content-Disposition', 'Set-Cookie'):
            self.assertEqual(headers.get_all(name), get_headers.get_all(name), name)
        self.assertEqual(headers.get_all('Content-Length'), [str(len(body))])
        self.assert_local_csp(headers)
        self.assertEqual(len(self.backend.head_requests), 1)
        upstream_path, upstream_headers = self.backend.head_requests[0]
        self.assertEqual(upstream_path, path)
        self.assertEqual(upstream_headers['X-Access-Token'], 'fixture-token')
        self.assertEqual(upstream_headers['Cookie'], 'fixture=session')
        self.assertEqual(upstream_headers['Accept-Encoding'], 'identity')

    def test_api_head_preserves_upstream_range_metadata(self):
        # The backend decides how to handle Range on HEAD; the proxy must keep
        # its status and metadata instead of deriving a length from an empty body.
        for status, body, content_range in ((206, b'part', 'bytes 2-5/20'),
                                             (416, b'range unavailable', 'bytes */20')):
            with self.subTest(status=status):
                self.backend.http_response = (status, [
                    ('Content-Type', 'application/octet-stream'), ('Content-Length', str(len(body))),
                    ('Content-Range', content_range), ('Accept-Ranges', 'bytes'),
                ], body)
                request_headers = {'Range': 'bytes=2-5', 'If-Range': '"fixture-media"'}
                get_status, get_headers, get_body = self.http_response('GET', '/api/media', request_headers)
                head_status, headers, head_body = self.http_response('HEAD', '/api/media', request_headers)
                self.assertEqual((head_status, get_status), (status, status))
                self.assertEqual(get_body, body)
                self.assertEqual(head_body, b'')
                for name in ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges'):
                    self.assertEqual(headers.get_all(name), get_headers.get_all(name), name)
                self.assertEqual(self.backend.head_requests[-1][1]['Range'], 'bytes=2-5')
                self.assertEqual(self.backend.head_requests[-1][1]['If-Range'], '"fixture-media"')
                self.assert_local_csp(headers)

    def test_api_head_does_not_invent_content_length(self):
        for upstream_status, declared_length in ((200, None), (204, None), (304, None),
                                                   (304, '1234'), (200, '0')):
            with self.subTest(status=upstream_status, length=declared_length):
                upstream_headers = [('ETag', '"fixture-media"')]
                if declared_length is not None:
                    upstream_headers.append(('Content-Length', declared_length))
                self.backend.http_response = (upstream_status, upstream_headers, b'')
                status, headers, body = self.http_response('HEAD', '/api/media')
                self.assertEqual(status, upstream_status)
                self.assertEqual(headers.get_all('Content-Length', []),
                                 [] if declared_length is None else [declared_length])
                self.assertEqual(headers['ETag'], '"fixture-media"')
                self.assertEqual(body, b'')
                self.assert_local_csp(headers)

    def test_api_head_error_responses_keep_status_and_length_without_body(self):
        for upstream_status in (401, 403, 404):
            with self.subTest(status=upstream_status):
                payload = ('fixture error ' + str(upstream_status)).encode()
                self.backend.http_response = (upstream_status, [
                    ('Content-Type', 'application/json'), ('Content-Length', str(len(payload))),
                    ('WWW-Authenticate', 'Bearer realm="fixture"'),
                ], payload)
                get_status, get_headers, get_body = self.http_response('GET', '/api/media')
                status, headers, body = self.http_response('HEAD', '/api/media')
                self.assertEqual((status, get_status), (upstream_status, upstream_status))
                self.assertEqual(get_body, payload)
                self.assertEqual(body, b'')
                for name in ('Content-Type', 'Content-Length', 'WWW-Authenticate'):
                    self.assertEqual(headers.get_all(name), get_headers.get_all(name), name)
                self.assert_local_csp(headers)

    def test_api_head_local_errors_do_not_send_body(self):
        old = self.handler.ports['backend']
        with socket.socket() as unavailable:
            unavailable.bind(('127.0.0.1', 0))
            self.handler.ports['backend'] = unavailable.getsockname()[1]
            try:
                # Some hosts wait for timeout on a bound, unlistened socket.
                # Keep the real TCP failure path, but bound this fixture's wait.
                with patch.object(proxy, 'urlopen', lambda request, timeout: urlopen(request, timeout=.2)):
                    status, headers, body = self.http_response('HEAD', '/api/media')
                self.assertEqual(status, 502)
                self.assertEqual(body, b'')
                self.assertGreater(int(headers['Content-Length']), 0)
                self.assert_local_csp(headers)
            finally:
                self.handler.ports['backend'] = old
        for fields in ({'Content-Length': '-1'}, {'Transfer-Encoding': 'chunked'},
                       {'Upgrade': 'websocket', 'Connection': 'Upgrade'}):
            with self.subTest(headers=fields):
                status, headers, body = self.http_response('HEAD', '/api/media', fields)
                self.assertEqual(status, 400)
                self.assertEqual(body, b'')
                self.assert_local_csp(headers)
        self.assertFalse(self.backend.requests)

    def test_static_and_spa_head_match_get_without_body(self):
        Path(self.tmp.name, 'fixture.js').write_bytes(b'fixture javascript')
        Path(self.tmp.name, '\u4e2d\u6587.txt').write_bytes('fixture \u4e2d\u6587'.encode())
        directory = Path(self.tmp.name, 'nested')
        directory.mkdir()
        (directory / 'index.html').write_bytes(b'nested index')
        for path in ('/index.html', '/fixture.js?version=1', '/%E4%B8%AD%E6%96%87.txt',
                     '/nested/spa-route?fixture=1', '/nested', '/nested/'):
            with self.subTest(path=path):
                get_status, get_headers, get_body = self.http_response('GET', path)
                status, headers, body = self.http_response('HEAD', path)
                self.assertEqual(status, get_status)
                self.assertEqual(body, b'')
                for name in ('Content-Type', 'Content-Length', 'Last-Modified', 'Location'):
                    self.assertEqual(headers.get_all(name), get_headers.get_all(name), name)
                if get_status == 200:
                    self.assertEqual(int(headers['Content-Length']), len(get_body))
                self.assert_local_csp(headers)
        self.assertFalse(self.backend.requests)

    def test_static_head_conditional_and_missing_responses(self):
        _, get_headers, _ = self.http_response('GET', '/index.html')
        for path, fields, expected in (('/index.html', {'If-Modified-Since': get_headers['Last-Modified']}, 304),
                                        ('/missing.js', {}, 404)):
            with self.subTest(path=path):
                get_status, get_headers, get_body = self.http_response('GET', path, fields)
                status, headers, body = self.http_response('HEAD', path, fields)
                self.assertEqual((status, get_status), (expected, expected))
                self.assertEqual(body, b'')
                for name in ('Content-Type', 'Content-Length'):
                    self.assertEqual(headers.get_all(name), get_headers.get_all(name), name)
                if expected == 404:
                    self.assertEqual(int(headers['Content-Length']), len(get_body))
                self.assert_local_csp(headers)

    def test_handshake_and_early_frames_preserved(self):
        self.backend.mode = 'early'
        data = b'\x89\x04ping\x82\x04\x00\xff\x80\x01\x88\x02\x03\xe8'
        with self.connect(early=data) as (conn, response):
            self.assertTrue(response.startswith(b'HTTP/1.1 101'))
            self.assertIn(b'Sec-WebSocket-Protocol: fixture', response)
            self.assert_local_csp(parse_headers(io.BytesIO(response.split(b'\r\n', 1)[1])))
            self.assertEqual(exact(conn, 4 + len(data)), b'\x81\x02ok' + data)

    def test_large_stream_and_concurrent_connection(self):
        data = bytes(range(256)) * 4096
        with self.connect() as (conn, response):
            self.assertIn(b'101', response)
            errors = []
            def send():
                try:
                    conn.sendall(data)
                except OSError as error:
                    errors.append(type(error).__name__)
            worker = threading.Thread(target=send, daemon=True)
            worker.start()
            with self.connect() as (other, response2):
                self.assertIn(b'101', response2)
                other.sendall(b'parallel'); self.assertEqual(exact(other, 8), b'parallel')
            self.assertEqual(exact(conn, len(data)), data)
            worker.join(2); self.assertFalse(worker.is_alive()); self.assertFalse(errors)

    def test_client_disconnect_closes_upstream(self):
        with self.connect() as (_, response):
            self.assertIn(b'101', response)
        self.assertTrue(self.backend.disconnected.wait(1))

    def test_backend_disconnect_closes_client(self):
        self.backend.mode = 'disconnect'
        with self.connect() as (conn, response):
            self.assertIn(b'101', response)
            self.assertEqual(conn.recv(1), b'')

    def test_idle_connection_is_reaped(self):
        with self.connect() as (conn, response):
            self.assertIn(b'101', response)
            self.assertEqual(conn.recv(1), b'')
        self.assertTrue(self.backend.disconnected.wait(1))

    def test_invalid_upgrade_requests_do_not_reach_backend(self):
        for change in ({'Sec-WebSocket-Key': 'bad'}, {'Sec-WebSocket-Version': '12'}, {'Connection': 'close'},
                       {'Upgrade': 'other'}, {'Content-Length': '1'}, {'Transfer-Encoding': 'chunked'}):
            with self.subTest(change=change), self.connect(change) as (_, response):
                self.assertIn(b'400', response)
        for method, path in (('POST', '/api/websocket/fixture'), ('GET', '/api/sys/user/list')):
            with self.subTest(method=method, path=path), self.connect(method=method, path=path) as (_, response):
                self.assertIn(b'400', response)
        self.assertFalse(self.backend.requests)

    def test_foreign_origin_is_rejected_before_backend(self):
        with self.connect({'Origin': 'https://example.invalid'}) as (_, response):
            self.assertIn(b'403', response)
        self.assertFalse(self.backend.requests)

    def test_nonbrowser_client_without_origin_is_supported(self):
        with self.connect({'Origin': None}) as (_, response):
            self.assertIn(b'101', response)

    def test_upstream_refusal_and_invalid_handshakes(self):
        for mode, status in (('refuse', b'403'), ('invalid', b'502'), ('huge', b'502'), ('unresponsive', b'502')):
            self.backend.mode = mode
            with self.subTest(mode=mode), self.connect() as (_, response):
                self.assertIn(status, response.split(b'\r\n')[0])

    def test_missing_backend_fails_and_recovers(self):
        # Hold an unlistened bound port to avoid connecting to an unrelated process.
        handler = self.handler
        old = handler.ports['backend']
        with socket.socket() as unavailable:
            unavailable.bind(('127.0.0.1', 0))
            handler.ports['backend'] = unavailable.getsockname()[1]
            with self.connect() as (_, response):
                self.assertIn(b'502', response)
        handler.ports['backend'] = old
        with self.connect() as (_, response):
            self.assertIn(b'101', response)

    def test_ordinary_http_and_static_routes_keep_contract(self):
        url = 'http://127.0.0.1:' + str(self.frontend.server_port)
        with urlopen(url + '/api/fixture') as response:
            self.assertEqual(response.read(), b'ordinary response')
            self.assertEqual(len(response.headers.get_all('Set-Cookie')), 2)
            self.assert_local_csp(response.headers)
        for path in ('/index.html', '/nested/spa-route'):
            with urlopen(url + path) as response:
                self.assertEqual(response.read(), b'fixture index')
                self.assert_local_csp(response.headers)

    def test_error_responses_keep_local_csp(self):
        url = 'http://127.0.0.1:' + str(self.frontend.server_port)
        with self.assertRaises(HTTPError) as missing:
            urlopen(url + '/missing.js')
        with missing.exception as response:
            self.assertEqual(response.code, 404)
            self.assert_local_csp(response.headers)
        # A reserved, unlistened loopback port cannot be another local service.
        old = self.handler.ports['backend']
        with socket.socket() as unavailable:
            unavailable.bind(('127.0.0.1', 0))
            self.handler.ports['backend'] = unavailable.getsockname()[1]
            try:
                with self.assertRaises(HTTPError) as failed:
                    urlopen(url + '/api/fixture')
                with failed.exception as response:
                    self.assertEqual(response.code, 502)
                    self.assert_local_csp(response.headers)
            finally:
                self.handler.ports['backend'] = old

    def test_fragmented_http_body_is_not_truncated(self):
        body = b'fixture-body-' * 10000
        with socket.create_connection(('127.0.0.1', self.frontend.server_port), timeout=2) as conn:
            conn.sendall(('POST /api/fixture HTTP/1.1\r\nHost: localhost\r\nContent-Length: ' + str(len(body)) + '\r\n\r\n').encode())
            conn.sendall(body[:2]); time.sleep(.03); conn.sendall(body[2:9000]); time.sleep(.03); conn.sendall(body[9000:])
            self.assertIn(b'200', head(conn))
            self.assertEqual(exact(conn, len(body)), body)


if __name__ == '__main__':
    unittest.main()
