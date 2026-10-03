"""Read-only, loopback-only product/probe fixture; no real API or login.

Run with an explicitly owned free port:
python3 web/tests/python-execution-frame/server.py --port PORT --directory web/public
Record the returned shell PID; terminate only that PID when finished.
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument('--port', required=True, type=int)
parser.add_argument('--directory', required=True, type=Path)
args = parser.parse_args()
fixtures = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        route = urlparse(self.path).path
        if route == '/__frame_probe.js':
            data = (fixtures / 'browser-probe.js').read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)
            return
        if route == '/fixtures/seed.py':
            data = b'print("finite fixture")\nprint(sum(range(10000)))\n'
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        # Expose no submit/upload/state-changing endpoints. This server only serves
        # the actual public files plus the explicitly named self-authored probe.
        if route.startswith('/api/'):
            self.send_error(404, 'No API in execution fixture')
            return
        super().do_GET()

    def do_POST(self):
        self.send_error(405, 'Read-only execution fixture')


server = ThreadingHTTPServer(('127.0.0.1', args.port), partial(Handler, directory=str(args.directory.resolve())))
print('execution fixture listening on http://127.0.0.1:' + str(args.port), flush=True)
server.serve_forever()
