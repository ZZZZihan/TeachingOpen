#!/usr/bin/env python3
"""Serve the built frontend and proxy /api to the isolated loopback backend."""
import argparse
import base64
import hashlib
from http.client import HTTPException, parse_headers
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
from pathlib import Path
import selectors
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from local_runtime import DEFAULT_PORTS, load_ports


class LocalFrontend(SimpleHTTPRequestHandler):
    ports = DEFAULT_PORTS
    # Do not read ahead into the first WebSocket frame while parsing HTTP.
    rbufsize = 0
    websocket_timeout = 5
    websocket_idle_timeout = 90
    websocket_buffer_limit = 65536

    def end_headers(self):
        # Block legacy telemetry and other remote integrations during local tests.
        self.send_header("Content-Security-Policy", "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self'")
        super().end_headers()

    def api(self):
        if self.headers.get("Upgrade") or "upgrade" in self.header_tokens(self.headers, "Connection"):
            self.websocket()
            return
        try:
            remaining = int(self.headers.get("Content-Length", "0"))
            if remaining < 0 or self.headers.get("Transfer-Encoding"):
                raise ValueError()
        except ValueError:
            self.send_error(400, "Invalid request framing")
            return
        body = bytearray()
        # An unbuffered socket read can return fewer bytes than requested.
        while remaining:
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                self.send_error(400, "Incomplete request body")
                return
            body.extend(chunk)
            remaining -= len(chunk)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "connection", "content-length", "accept-encoding")}
        headers["Accept-Encoding"] = "identity"
        req = Request("http://127.0.0.1:" + str(self.ports["backend"]) + self.path, data=body if body else None, headers=headers, method=self.command)
        try:
            response = urlopen(req, timeout=30)
        except HTTPError as error:
            response = error
        except (URLError, TimeoutError):
            self.send_error(502, "Local backend unavailable")
            return
        with response:
            data = response.read()
            self.send_response(response.status)
            for key, value in response.headers.items():
                if key.lower() not in ("transfer-encoding", "connection", "content-length", "content-encoding"):
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    @staticmethod
    def header_tokens(headers, name):
        return {token.strip().lower() for value in headers.get_all(name, []) for token in value.split(",")}

    def websocket(self):
        """Upgrade only the local API's WS routes, then relay opaque bytes."""
        self.close_connection = True
        key = self.headers.get("Sec-WebSocket-Key", "")
        try:
            valid_key = len(self.headers.get_all("Sec-WebSocket-Key", [])) == 1 and len(base64.b64decode(key, validate=True)) == 16
        except ValueError:
            valid_key = False
        if (self.command != "GET" or not self.path.startswith("/api/websocket/")
                or self.request_version != "HTTP/1.1"
                or self.header_tokens(self.headers, "Upgrade") != {"websocket"}
                or "upgrade" not in self.header_tokens(self.headers, "Connection")
                or self.headers.get_all("Sec-WebSocket-Version") != ["13"] or not valid_key
                or self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length", "0") != "0"):
            self.send_error(400, "Invalid local WebSocket upgrade")
            return
        origin = self.headers.get("Origin")
        allowed_origins = {"http://" + host + ":" + str(self.ports["frontend"]) for host in ("127.0.0.1", "localhost")}
        if origin is not None and (len(self.headers.get_all("Origin")) != 1 or origin not in allowed_origins):
            self.send_error(403, "Local WebSocket origin rejected")
            return
        upgraded = False
        try:
            with socket.create_connection(("127.0.0.1", self.ports["backend"]), timeout=self.websocket_timeout) as upstream:
                lines = ["GET " + self.path + " HTTP/1.1", "Host: 127.0.0.1:" + str(self.ports["backend"]),
                         "Connection: Upgrade", "Upgrade: websocket"]
                allowed = {"origin", "cookie", "authorization", "x-access-token", "sec-websocket-key", "sec-websocket-version",
                           "sec-websocket-protocol", "sec-websocket-extensions"}
                for name, value in self.headers.items():
                    if name.lower() in allowed:
                        if "\r" in value or "\n" in value:
                            raise ValueError("Invalid header")
                        lines.append(name + ": " + value)
                upstream.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("iso-8859-1"))
                received = bytearray()
                deadline = time.monotonic() + self.websocket_timeout
                while b"\r\n\r\n" not in received:
                    upstream.settimeout(max(.001, deadline - time.monotonic()))
                    chunk = upstream.recv(4096)
                    if not chunk or len(received) + len(chunk) > 32768 or time.monotonic() > deadline:
                        raise ValueError("Invalid upstream handshake")
                    received.extend(chunk)
                head, extra = bytes(received).split(b"\r\n\r\n", 1)
                status_line, header_bytes = head.split(b"\r\n", 1)
                version, status, _ = status_line.split(b" ", 2)
                headers = parse_headers(io.BytesIO(header_bytes + b"\r\n\r\n"))
                if status != b"101":
                    self.send_error(int(status) if status in (b"400", b"401", b"403", b"404", b"426", b"503") else 502,
                                    "Local backend refused WebSocket upgrade")
                    return
                accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
                if (version != b"HTTP/1.1" or headers.get_all("Sec-WebSocket-Accept") != [accept]
                        or self.header_tokens(headers, "Upgrade") != {"websocket"}
                        or "upgrade" not in self.header_tokens(headers, "Connection")):
                    raise ValueError("Invalid upstream upgrade")
                # HTTP/1.0 remains the default for static/ordinary proxy responses.
                self.protocol_version = "HTTP/1.1"
                self.send_response(101, "Switching Protocols")
                for name, value in headers.items():
                    if name.lower() in {"upgrade", "connection", "sec-websocket-accept", "sec-websocket-protocol", "sec-websocket-extensions", "set-cookie"}:
                        self.send_header(name, value)
                self.end_headers()
                self.wfile.flush()
                upgraded = True
                self.relay_websocket(upstream, extra)
        except (OSError, ValueError, HTTPException):
            # Do not log handshake URLs, credentials, application frames or errors.
            if not upgraded:
                self.send_error(502, "Local WebSocket backend unavailable")

    def relay_websocket(self, upstream, initial):
        """Bound both queues and apply backpressure instead of buffering a stream."""
        client = self.connection
        sockets = (client, upstream)
        peer = {client: upstream, upstream: client}
        pending = {client: bytearray(initial), upstream: bytearray()}
        ended = False
        last_activity = time.monotonic()
        for conn in sockets:
            conn.setblocking(False)
        with selectors.DefaultSelector() as selector:
            while not ended or any(pending.values()):
                for conn in sockets:
                    events = selectors.EVENT_WRITE if pending[conn] else 0
                    if not ended and len(pending[peer[conn]]) < self.websocket_buffer_limit:
                        events |= selectors.EVENT_READ
                    try:
                        selector.get_key(conn)
                    except KeyError:
                        if events:
                            selector.register(conn, events)
                    else:
                        if events:
                            selector.modify(conn, events)
                        else:
                            selector.unregister(conn)
                remaining = self.websocket_idle_timeout - (time.monotonic() - last_activity)
                if remaining <= 0:
                    return
                for key, events in selector.select(min(1, remaining)):
                    conn = key.fileobj
                    if events & selectors.EVENT_WRITE:
                        try:
                            sent = conn.send(pending[conn])
                        except BlockingIOError:
                            sent = 0
                        if sent:
                            del pending[conn][:sent]
                            last_activity = time.monotonic()
                    if events & selectors.EVENT_READ and not ended:
                        try:
                            chunk = conn.recv(self.websocket_buffer_limit - len(pending[peer[conn]]))
                        except BlockingIOError:
                            continue
                        if not chunk:
                            ended = True
                        else:
                            pending[peer[conn]].extend(chunk)
                            last_activity = time.monotonic()

    def do_GET(self):
        if self.path.startswith("/api/"):
            self.api()
        else:
            route = Path(urlsplit(self.path).path)
            if not route.suffix and not Path(self.translate_path(self.path)).exists():
                self.path = "/index.html"
            super().do_GET()

    do_POST = api
    do_PUT = api
    do_DELETE = api
    do_OPTIONS = api

    def log_message(self, format, *args):
        # Even paths can contain tokens (legacy third-party login routes).
        print(self.command, "api" if self.path.startswith("/api/") else "static", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--runtime", type=Path)
    args = parser.parse_args()
    directory = args.dist.resolve()
    if not (directory / "index.html").is_file():
        raise SystemExit("Build web/dist first")
    LocalFrontend.ports = load_ports(args.runtime.resolve()) if args.runtime else DEFAULT_PORTS
    server = ThreadingHTTPServer(("127.0.0.1", LocalFrontend.ports["frontend"]), lambda *a, **kw: LocalFrontend(*a, directory=str(directory), **kw))
    print("Local frontend:", LocalFrontend.ports["frontend"], "API proxy:", LocalFrontend.ports["backend"], flush=True)
    server.serve_forever()
