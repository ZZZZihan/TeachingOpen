#!/usr/bin/env python3
"""Serve the built frontend and proxy /api to the isolated loopback backend."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from local_runtime import DEFAULT_PORTS, load_ports


class LocalFrontend(SimpleHTTPRequestHandler):
    ports = DEFAULT_PORTS

    def end_headers(self):
        # Block legacy telemetry and other remote integrations during local tests.
        self.send_header("Content-Security-Policy", "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self'")
        super().end_headers()

    def api(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
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
        data = response.read()
        self.send_response(response.status)
        for key, value in response.headers.items():
            if key.lower() not in ("transfer-encoding", "connection", "content-length", "content-encoding"):
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

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
