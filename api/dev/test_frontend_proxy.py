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

    def do_GET(self):
        self.server.requests.append((self.path, dict(self.headers)))
        if not self.headers.get('Upgrade'):
            self.send_response(200)
            self.send_header('Set-Cookie', 'fixture=one; HttpOnly')
            self.send_header('Set-Cookie', 'fixture2=two; HttpOnly')
            self.end_headers()
            self.wfile.write(b'ordinary response')
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
