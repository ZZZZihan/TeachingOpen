#!/usr/bin/env python3
"""Opt-in, isolated Nginx/TLS integration checks; no public CA or live service.

Requires Docker, an already available official Nginx image and local OpenSSL.
Every client TCP connection targets a random, loopback-only published port.
8.8.8.8 is only a certificate identity/configuration fixture, never a destination.
Temporary keys and the owned container are removed even when a check fails.
"""

import argparse
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import selectors
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "8.8.8.8"
WRONG_IDENTITY = "8.8.4.4"
DEFAULT_IMAGE = "nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94"
RESPONSE_PREVIEW_BYTES = 4096
DOCKER_LOG_CHARACTERS = 16384
SECURITY_HEADERS = {
    "x-frame-options": "SAMEORIGIN",
    "x-content-type-options": "nosniff",
    "x-xss-protection": "1; mode=block",
    "referrer-policy": "strict-origin-when-cross-origin",
    "content-security-policy": "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: ws: wss:;",
    "x-download-options": "noopen",
    "x-permitted-cross-domain-policies": "none",
    "permission-policy": "camera=(), geolocation=(), microphone=()",
    "cross-origin-opener-policy": "same-origin",
}


def native_source():
    """Synthetic copy of the reviewed native site's extra business rules.

    Build from repository-owned source; never copy a live site or its identity
    into the test, report or TCP destination.
    """
    source = (ROOT / "web/nginx/default.conf").read_text()
    anchors = {
        "    listen 80 default_server;": "    listen 80 default_server;\n    listen 127.0.0.1:8088;",
        "    server_name localhost;": f"    server_name {IDENTITY};",
        "root /usr/share/nginx/html;": "root /fixture/web;",
        "proxy_pass              http://api:8080;": "proxy_pass              http://127.0.0.1:18080;",
        "    add_header Cross-Origin-Resource-Policy $teaching_python_resource_policy always;":
            "    add_header Cross-Origin-Resource-Policy $teaching_python_resource_policy always;\n"
            "    add_header Cache-Control $teaching_html_cache_policy always;",
        "    location / {": r'''    # A missing script/style is not a client-side page route.
    location ~* \.(js|css)(\.gz)?$ {
        root /fixture/web;
        try_files $uri =404;
        gzip on;
        gzip_min_length 1k;
        gzip_comp_level 9;
        gzip_types application/javascript text/css;
        gzip_vary on;
        gzip_disable "MSIE [1-6]\.";
    }

    location / {''',
    }
    for old, new in anchors.items():
        if source.count(old) != 1:
            raise AssertionError(f"synthetic native source anchor changed: {old}")
        source = source.replace(old, new, 1)
    return r'''map $uri $teaching_html_cache_policy {
    default "";
    ~*\.html$ "no-cache";
}

''' + source

# BusyBox nc is present in the official alpine image. This deliberately small
# fixture checks HTTP request forwarding and exchanges a real WebSocket frame.
# It is an isolated upstream, not the TeachingOpen Java application.
UPSTREAM = r'''#!/bin/sh
cr=$(printf '\r')
IFS=' ' read -r method uri version || exit 0
length=0
scheme=''
forwarded=''
forwarded_for=''
forwarded_host=''
forwarded_port=''
real_ip=''
host=''
upgrade=''
connection=''
key=''
while IFS= read -r header; do
    header=${header%"$cr"}
    [ -n "$header" ] || break
    name=$(printf '%s' "${header%%:*}" | tr '[:upper:]' '[:lower:]')
    value=${header#*:}
    value=${value# }
    case "$name" in
        content-length) length=$value ;;
        x-scheme) scheme=$value ;;
        x-forwarded-proto) forwarded=$value ;;
        x-forwarded-for) forwarded_for=$value ;;
        x-forwarded-host) forwarded_host=$value ;;
        x-forwarded-port) forwarded_port=$value ;;
        x-real-ip) real_ip=$value ;;
        host) host=$value ;;
        upgrade) upgrade=$value ;;
        connection) connection=$value ;;
        sec-websocket-key) key=$value ;;
    esac
done
if [ "$uri" = '/api/runtime-websocket?probe=1' ] &&
   [ "$upgrade" = websocket ] && [ "$connection" = upgrade ] &&
   [ "$key" = 'dGhlIHNhbXBsZSBub25jZQ==' ]; then
    printf 'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n'
    frame=$(dd bs=1 count=10 2>/dev/null | od -An -tx1 | tr -d ' \n')
    [ "$frame" = '818401020304716b6d63' ] || exit 1
    printf '\201\004ping'
    exit 0
fi
body=''
if [ "$length" -gt 0 ]; then
    body=$(dd bs=1 count="$length" 2>/dev/null)
fi
response=$(printf 'method=%s\nuri=%s\nscheme=%s\nforwarded_proto=%s\nforwarded_for=%s\nforwarded_host=%s\nforwarded_port=%s\nreal_ip=%s\nhost=%s\nbody=%s' "$method" "$uri" "$scheme" "$forwarded" "$forwarded_for" "$forwarded_host" "$forwarded_port" "$real_ip" "$host" "$body")
printf 'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: %s\r\nConnection: close\r\n\r\n%s' "${#response}" "$response"
'''


def command(args, *, check=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if check and result.returncode:
        # Commands contain only fixture paths and public test identities.
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(map(str, args))}\n"
                           f"{result.stdout}{result.stderr}")
    return result


class FixtureHTTPSConnection(http.client.HTTPSConnection):
    """Connect to loopback while verifying the certificate's IP SAN normally."""

    def __init__(self, port, context, identity=IDENTITY):
        super().__init__("127.0.0.1", port, timeout=5, context=context)
        self.identity = identity

    def connect(self):
        plain = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            self.sock = self._context.wrap_socket(plain, server_hostname=self.identity)
        except BaseException:
            plain.close()
            raise


class Runtime:
    def __init__(self, directory, image, report, source_mode="template"):
        self.directory = directory
        self.image = image
        self.report = report
        self.name = f"teachingopen-ip-https-test-{uuid.uuid4().hex[:12]}"
        self.started = False
        self.http_port = None
        self.https_port = None
        self.context = None
        self.source_mode = source_mode

    def record(self, name, condition, details=None):
        row = {"name": name, "passed": bool(condition)}
        if details is not None:
            row["details"] = details
        self.report["checks"].append(row)
        if not condition:
            raise AssertionError(f"runtime check failed: {name}: {details}")

    def echo_response(self, stage, method, path, status, headers, body):
        """Reject non-echo responses with the original HTTP failure evidence."""
        details = {"stage": stage, "method": method, "path": path, "status": status,
                   "content_type": headers.get("content-type"), "body_bytes": len(body),
                   "body_preview": body[:RESPONSE_PREVIEW_BYTES].decode("utf-8", errors="replace"),
                   "body_truncated": len(body) > RESPONSE_PREVIEW_BYTES}
        name = f"{stage} API {method} returns HTTP 200 and key/value echo"
        if status != 200:
            self.record(name, False, details)
        try:
            lines = body.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            details["format_error"] = "echo body is not UTF-8"
            self.record(name, False, details)
        values = {}
        if not lines:
            details["format_error"] = "echo body is empty"
            self.record(name, False, details)
        for number, line in enumerate(lines, 1):
            key, separator, value = line.partition("=")
            if not separator or not key or key in values:
                details["format_error"] = f"invalid or duplicate echo key on line {number}"
                self.record(name, False, details)
            values[key] = value
        self.record(name, True, details)
        return values, details

    def capture_diagnostics(self):
        # These files and this named container belong only to the synthetic test.
        # Diagnostic failures must not replace the original verification failure.
        try:
            diagnostics = self.directory / "fixture-nginx-diagnostics.log"
            if diagnostics.exists():
                self.report["nginx_diagnostics"] = diagnostics.read_text()[-4096:]
        except Exception as exc:
            self.report["nginx_diagnostics_error"] = f"{type(exc).__name__}: {exc}"
        if self.started:
            try:
                result = command(["docker", "logs", "--timestamps", "--tail", "100", self.name], check=False)
                logs = result.stdout + result.stderr
                self.report["docker_logs"] = {"exit_code": result.returncode,
                    "text": logs[-DOCKER_LOG_CHARACTERS:], "truncated": len(logs) > DOCKER_LOG_CHARACTERS}
            except Exception as exc:
                self.report["docker_logs_error"] = f"{type(exc).__name__}: {exc}"

    def prepare(self):
        image = command(["docker", "image", "inspect", self.image])
        image_info = json.loads(image.stdout)[0]
        self.report["image"] = {"requested": self.image, "id": image_info["Id"],
                                "repo_digests": image_info.get("RepoDigests", [])}
        for path in ("web/python", "acme/.well-known/acme-challenge", "certs"):
            (self.directory / path).mkdir(parents=True, exist_ok=True)
        (self.directory / "web/index.html").write_text("<html>synthetic-ip-https-spa</html>\n")
        (self.directory / "web/python/runner.js").write_text("/* synthetic runtime asset */\n")
        (self.directory / "web/python/secret.py").write_text("# synthetic private source\n")
        (self.directory / "web/python/runner.html").write_text("<html>synthetic runner</html>\n")
        for path in ("runtime-private.map", "runtime-private.sql", "logfiles/runtime-private.txt"):
            private = self.directory / "web" / path
            private.parent.mkdir(parents=True, exist_ok=True)
            private.write_text("synthetic-denied-resource\n")
        (self.directory / "web/runtime-video.mp4").write_bytes(bytes(range(256)) * 16)
        (self.directory / "acme/.well-known/acme-challenge/runtime-token").write_text("synthetic-acme-response")
        (self.directory / "upstream.sh").write_text(UPSTREAM)
        (self.directory / "upstream.sh").chmod(0o755)
        certs = self.directory / "certs"
        command(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256",
                 "-days", "2", "-subj", "/CN=TeachingOpen isolated test CA",
                 "-addext", "basicConstraints=critical,CA:TRUE",
                 "-addext", "keyUsage=critical,keyCertSign,cRLSign",
                 "-keyout", str(certs / "ca.key"), "-out", str(certs / "ca.pem")])
        command(["openssl", "req", "-new", "-newkey", "rsa:2048", "-nodes", "-sha256",
                 "-subj", f"/CN={IDENTITY}", "-keyout", str(certs / "server.key"),
                 "-out", str(certs / "server.csr")])
        (certs / "server.ext").write_text(f"subjectAltName=IP:{IDENTITY}\n"
                                          "basicConstraints=critical,CA:FALSE\n"
                                          "keyUsage=critical,digitalSignature,keyEncipherment\n"
                                          "extendedKeyUsage=serverAuth\n")
        command(["openssl", "x509", "-req", "-in", str(certs / "server.csr"),
                 "-CA", str(certs / "ca.pem"), "-CAkey", str(certs / "ca.key"),
                 "-CAcreateserial", "-days", "2", "-sha256", "-extfile", str(certs / "server.ext"),
                 "-out", str(certs / "server.pem")])
        # Another site's CA-trusted leaf has a different IP SAN. Its ordinary
        # vhost is included first to expose IP clients that send no TLS SNI.
        (certs / "other-site.ext").write_text(f"subjectAltName=IP:{WRONG_IDENTITY}\n"
                                               "basicConstraints=critical,CA:FALSE\n"
                                               "keyUsage=critical,digitalSignature,keyEncipherment\n"
                                               "extendedKeyUsage=serverAuth\n")
        command(["openssl", "x509", "-req", "-in", str(certs / "server.csr"),
                 "-CA", str(certs / "ca.pem"), "-CAkey", str(certs / "ca.key"),
                 "-CAserial", str(certs / "ca.srl"), "-days", "2", "-sha256",
                 "-extfile", str(certs / "other-site.ext"), "-out", str(certs / "other-site.pem")])
        # A TemporaryDirectory starts at 0700. Native Linux bind mounts retain
        # that mode, so non-root Nginx workers need traversal through /fixture.
        # Keep only the public static trees readable; CA/server keys stay private.
        self.directory.chmod(0o711)
        public_paths = []
        for public in (self.directory / "web", self.directory / "acme"):
            for path in (public, *public.rglob("*")):
                path.chmod(0o755 if path.is_dir() else 0o644)
                public_paths.append(path)
        certs.chmod(0o700)
        for key in (certs / "ca.key", certs / "server.key"):
            key.chmod(0o600)
        self.record("fixture root permits worker traversal without directory listing",
                    stat.S_IMODE(self.directory.stat().st_mode) == 0o711)
        self.record("public web and ACME paths have explicit worker-readable permissions", all(
            stat.S_IMODE(path.stat().st_mode) == (0o755 if path.is_dir() else 0o644)
            for path in public_paths))
        self.record("certificate directory and both private keys keep private permissions",
                    stat.S_IMODE(certs.stat().st_mode) == 0o700 and all(
                        stat.S_IMODE(key.stat().st_mode) == 0o600
                        for key in (certs / "ca.key", certs / "server.key")))
        self.context = ssl.create_default_context(cafile=str(certs / "ca.pem"))
        render_args = [sys.executable, str(ROOT / "deploy/ip_https.py"), "render",
                       "--ip", IDENTITY, "--web-root", "/fixture/web",
                       "--api-upstream", "http://127.0.0.1:18080",
                       "--acme-root", "/fixture/acme", "--certificate", "/fixture/certs/server.pem",
                       "--private-key", "/fixture/certs/server.key", "--output", str(self.directory / "rendered")]
        if self.source_mode == "reviewed-native":
            self.original_source = native_source().encode()
            source_path = self.directory / "native-source.conf"
            source_path.write_bytes(self.original_source)
            source_hash = hashlib.sha256(self.original_source).hexdigest()
            render_args.extend(["--source-config", str(source_path), "--source-sha256", source_hash])
            self.report["synthetic_native_source_sha256"] = source_hash
        command(render_args)
        self.report["source_sha256"] = {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in ("deploy/ip_https.py", "deploy/check_ip_certificate.py",
                         "deploy/test_ip_https_runtime.py", "web/nginx/default.conf")}
        self.report["renderer_sha256"] = hashlib.sha256((ROOT / "deploy/ip_https.py").read_bytes()).hexdigest()
        self.report["config_sha256"] = {
            mode: hashlib.sha256((self.directory / "rendered" / f"{mode}.conf").read_bytes()).hexdigest()
            for mode in ("bootstrap", "trial", "https")}
        if self.source_mode == "reviewed-native":
            self.record("rendering keeps the reviewed synthetic source bytes unchanged",
                        source_path.read_bytes() == self.original_source)
            for mode in ("bootstrap", "trial", "https"):
                config = (self.directory / "rendered" / f"{mode}.conf").read_text()
                self.record(f"{mode} retains exactly one loopback-only native listener",
                            config.count("    listen 127.0.0.1:8088;") == 1
                            and "    listen 8088;" not in config)
        (self.directory / "other-vhost.conf").write_text("")
        (self.directory / "nginx.conf").write_text("worker_processes 1;\npid /tmp/nginx.pid;\n"
                                                   "error_log /dev/stderr notice;\nevents { worker_connections 128; }\n"
                                                   "http { include /etc/nginx/mime.types; access_log off; "
                                                   "include /fixture/other-vhost.conf; include /fixture/active.conf; }\n")
        if self.source_mode == "reviewed-native":
            shutil.copyfile(self.directory / "native-source.conf", self.directory / "active.conf")
        else:
            shutil.copyfile(self.directory / "rendered/bootstrap.conf", self.directory / "active.conf")
        self.shim = self.directory / "nginx-shim"
        # macOS Docker bind mounts can momentarily expose replacement bytes
        # with the previous file's size. Synchronize this fixture's transfer
        # boundary before testing/reloading the exact host-side candidate.
        self.shim.write_text("#!" + sys.executable + "\n" + '''import hashlib, pathlib, subprocess, sys, time
docker = ''' + repr(shutil.which("docker")) + '''
container = ''' + repr(self.name) + '''
target = pathlib.Path(''' + repr(str(self.directory / "active.conf")) + ''')
diagnostics = pathlib.Path(''' + repr(str(self.directory / "fixture-nginx-diagnostics.log")) + ''')
expected = hashlib.sha256(target.read_bytes()).hexdigest()
deadline = time.monotonic() + 10
attempts = 0
while time.monotonic() < deadline:
    visible = subprocess.run([docker, "exec", container, "sha256sum", "/fixture/active.conf"],
                             capture_output=True, text=True, timeout=5)
    attempts += 1
    if visible.returncode == 0 and visible.stdout.split()[0] == expected:
        break
    time.sleep(0.05)
else:
    with diagnostics.open("a") as log:
        log.write("fixture bind mount did not expose exact host config bytes\\n")
    sys.exit(1)
with diagnostics.open("a") as log:
    log.write(f"fixture config SHA256 {expected} visible after {attempts} probes\\n")
    result = subprocess.run([docker, "exec", container, "nginx", "-c", "/fixture/nginx.conf", *sys.argv[1:]],
                            stderr=log, timeout=20)
sys.exit(result.returncode)
''')
        self.shim.chmod(0o755)
        self.report["fixture_config_visibility"] = "each CLI Nginx operation requires exact host/container SHA-256 equality"

    def start(self):
        # Docker allocates the ports atomically; no reserve/release port race.
        result = command(["docker", "run", "--detach", "--name", self.name,
                          "--label", "teachingopen.test=ip-https", "--pull=never",
                          "--publish", "127.0.0.1::80", "--publish", "127.0.0.1::443",
                          "--mount", f"type=bind,source={self.directory},target=/fixture,readonly",
                          "--entrypoint", "/bin/sh", self.image, "-c",
                          "while true; do nc -l -s 127.0.0.1 -p 18080 -e /fixture/upstream.sh; done & "
                          "exec nginx -c /fixture/nginx.conf -g 'daemon off;'"])
        self.started = bool(result.stdout.strip())
        inspection = json.loads(command(["docker", "inspect", self.name]).stdout)[0]
        ports = inspection["NetworkSettings"]["Ports"]
        self.http_port = int(ports["80/tcp"][0]["HostPort"])
        self.https_port = int(ports["443/tcp"][0]["HostPort"])
        self.record("container ports bind loopback only", all(
            binding["HostIp"] == "127.0.0.1" for bindings in ports.values()
            for binding in bindings or []))
        self.wait_until(lambda: self.request("GET", "/")[0] == 200)
        initial = "original native" if self.source_mode == "reviewed-native" else "bootstrap"
        self.record(f"{initial} nginx configuration validates", self.nginx("-t").returncode == 0)
        self.worker_permissions()
        if self.source_mode == "reviewed-native":
            self.native_business("original native HTTP", original=True)
            self.native_business("original native loopback HTTP", internal=True, original=True)
            self.switch("bootstrap")

    def worker_permissions(self):
        # Copy the actual fixture to the container's native Linux filesystem.
        # This checks POSIX access independently of macOS bind-mount translation.
        worker = next(iter(self.workers()))
        process = command(["docker", "exec", self.name, "cat", f"/proc/{worker}/status"]).stdout
        worker_uid = next(line.split()[2] for line in process.splitlines() if line.startswith("Uid:"))
        self.record("Nginx serves content with a non-root worker", worker_uid != "0")
        native = "/tmp/ip-https-native-permissions"
        command(["docker", "exec", self.name, "cp", "-a", "/fixture", native])
        command(["docker", "exec", "--user", worker_uid, self.name, "/bin/sh", "-c",
                 'test "$(cat "$1/web/index.html")" = "<html>synthetic-ip-https-spa</html>" && '
                 'test "$(cat "$1/acme/.well-known/acme-challenge/runtime-token")" = synthetic-acme-response',
                 "permission-probe", native])
        self.record("non-root worker reads web and ACME files on native Linux permissions", True)
        command(["docker", "exec", "--user", worker_uid, self.name, "/bin/sh", "-c",
                 '! test -r "$1/certs/ca.key" && ! test -r "$1/certs/server.key"',
                 "permission-probe", native])
        self.record("non-root worker cannot read either private key on native Linux permissions", True)

    def nginx(self, action):
        return command(["docker", "exec", self.name, "nginx", "-c", "/fixture/nginx.conf", action])

    @staticmethod
    def wait_until(probe):
        end = time.monotonic() + 15
        last_error = None
        while time.monotonic() < end:
            try:
                if probe():
                    return
            except (OSError, http.client.HTTPException) as exc:
                last_error = str(exc)
            time.sleep(0.1)
        raise AssertionError(f"runtime readiness timed out: {last_error}")

    def request(self, method, path, *, tls=False, body=None, headers=None, identity=IDENTITY, internal=False):
        if internal:
            if tls:
                raise ValueError("The native 8088 listener is internal HTTP")
            return self.internal_request(method, path, body=body, headers=headers)
        connection = (FixtureHTTPSConnection(self.https_port, self.context, identity)
                      if tls else http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=5))
        merged = {"Host": IDENTITY, "Connection": "close", **(headers or {})}
        try:
            connection.request(method, path, body=body, headers=merged)
            response = connection.getresponse()
            return response.status, dict((key.lower(), value) for key, value in response.getheaders()), response.read()
        finally:
            connection.close()

    def internal_request(self, method, path, *, body=None, headers=None):
        """Reach only the container's retained loopback listener, never expose it."""
        payload = (body or "").encode()
        merged = {"Host": IDENTITY, "Connection": "close", **(headers or {})}
        if body is not None:
            merged["Content-Length"] = str(len(payload))
        request = (f"{method} {path} HTTP/1.1\r\n"
                   + "".join(f"{key}: {value}\r\n" for key, value in merged.items())
                   + "\r\n").encode() + payload
        # BusyBox nc may exit at stdin EOF before Nginx finishes proxying a POST.
        # Read the bounded response before closing input. Waiting for nc itself
        # first would deadlock because it can keep waiting for stdin after EOF
        # from the HTTP peer.
        with subprocess.Popen(["docker", "exec", "-i", self.name, "nc", "-w", "5", "127.0.0.1", "8088"],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            try:
                process.stdin.write(request)
                process.stdin.flush()
                output = bytearray()
                deadline = time.monotonic() + 10
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while True:
                        if not selector.select(max(0, deadline - time.monotonic())):
                            raise RuntimeError("isolated container loopback HTTP response timed out")
                        chunk = os.read(process.stdout.fileno(), 4096)
                        output.extend(chunk)
                        if len(output) > 65536:
                            raise RuntimeError("isolated container loopback response exceeded fixture bound")
                        boundary = output.find(b"\r\n\r\n")
                        if boundary < 0:
                            if not chunk:
                                raise RuntimeError("isolated container loopback closed before response headers")
                            continue

                        class ResponseSocket:
                            def makefile(self, *_args):
                                return io.BytesIO(output)

                        response = http.client.HTTPResponse(ResponseSocket())
                        try:
                            response.begin()
                            if response.length is not None and len(output) < boundary + 4 + response.length:
                                if not chunk:
                                    raise RuntimeError("isolated container loopback closed before response body")
                                continue
                            if response.length is None and not response.chunked and chunk:
                                continue
                            try:
                                received = response.status, dict((key.lower(), value) for key, value in response.getheaders()), response.read()
                            except http.client.IncompleteRead:
                                if not chunk:
                                    raise
                                continue
                            break
                        finally:
                            response.close()
                process.stdin.close()
                process.wait(timeout=10)
                errors = process.stderr.read()
                if process.returncode:
                    raise RuntimeError("isolated container loopback HTTP probe failed: " + errors.decode())
                return received
            finally:
                if process.poll() is None:
                    process.kill()

    def control(self, action, backup, candidate=None, check=True, expected_target_sha256=None,
                expected_candidate_sha256=None):
        arguments = [sys.executable, str(ROOT / "deploy/ip_https.py"), action,
                     "--target", str(self.directory / "active.conf"),
                     "--backup", str(self.directory / backup), "--nginx", str(self.shim)]
        if candidate:
            arguments.extend(["--candidate", str(self.directory / candidate)])
            if expected_candidate_sha256 is None:
                # Rendered candidates bind the original preparation manifest,
                # rather than recalculating a review hash from later bytes.
                if Path(candidate).parent == Path("rendered"):
                    expected_candidate_sha256 = self.report["config_sha256"][Path(candidate).stem]
                else:
                    expected_candidate_sha256 = hashlib.sha256((self.directory / candidate).read_bytes()).hexdigest()
            arguments.extend(["--expected-candidate-sha256", expected_candidate_sha256])
            if self.source_mode == "reviewed-native":
                reviewed_hash = expected_target_sha256 or hashlib.sha256((self.directory / "active.conf").read_bytes()).hexdigest()
                arguments.extend(["--expected-target-sha256", reviewed_hash])
        return command(arguments, check=check)

    def switch(self, mode, *, rollback=None):
        previous_workers = self.workers()
        if rollback:
            self.control("rollback", rollback)
        else:
            self.control("activate", f"backup-{mode}", f"rendered/{mode}.conf")
        # nginx -s reload returns before old workers finish retiring. Do not
        # mistake one response from a new worker for a completed transition.
        self.wait_until(lambda: bool(self.workers()) and not previous_workers.intersection(self.workers()))
        expected = 307 if mode == "https" else 200
        self.wait_until(lambda: self.request("GET", "/")[0] == expected)
        if mode != "bootstrap":
            self.wait_until(lambda: self.request("GET", "/", tls=True)[0] == 200)
        self.record(f"{'rollback' if rollback else 'activate'} CLI validates and serves {mode} configuration", True)

    def workers(self):
        output = command(["docker", "exec", self.name, "ps", "-o", "pid,args"]).stdout
        return {parts[0] for line in output.splitlines() if len(parts := line.split(None, 1)) == 2
                and parts[1].startswith("nginx: worker process")}

    def certificate_probe(self):
        arguments = [sys.executable, str(ROOT / "deploy/check_ip_certificate.py"),
                     "--port", str(self.https_port), "--connect-host", "127.0.0.1"]
        trusted = ["--ca-file", str(self.directory / "certs/ca.pem")]
        result = command(arguments + trusted + ["--ip", IDENTITY, "--min-hours", "24"])
        details = json.loads(result.stdout)
        self.record("served certificate probe validates CA, IP and remaining lifetime",
                    details.get("trust_and_ip_verified") is True and details.get("public_reachability_checked") is False)
        for name, extra in (
                ("wrong IP SAN", trusted + ["--ip", WRONG_IDENTITY, "--min-hours", "24"]),
                ("untrusted CA", ["--ip", IDENTITY, "--min-hours", "24"]),
                ("insufficient remaining lifetime", trusted + ["--ip", IDENTITY, "--min-hours", "72"])):
            result = command(arguments + extra, check=False)
            details = json.loads(result.stdout)
            self.record(f"served certificate probe rejects {name}", result.returncode == 1 and details.get("status") == "failed")

    def other_tls_vhost(self, *, default=False, remove=False):
        path = self.directory / "other-vhost.conf"
        flag = " default_server" if default else ""
        content = "" if remove else f'''server {{
    listen 443 ssl{flag};
    server_name other-fixture.invalid;
    ssl_certificate /fixture/certs/other-site.pem;
    ssl_certificate_key /fixture/certs/server.key;
    return 200 "other-site";
}}
'''
        path.write_text(content)
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        self.wait_until(lambda: command(["docker", "exec", self.name, "sha256sum",
                                        "/fixture/other-vhost.conf"]).stdout.split()[0] == expected)
        previous_workers = self.workers()
        self.nginx("-t")
        command([str(self.shim), "-s", "reload"])
        self.wait_until(lambda: bool(self.workers()) and not previous_workers.intersection(self.workers()))

    def no_sni_certificate(self, stage):
        context = ssl.create_default_context(cafile=str(self.directory / "certs/ca.pem"))
        # The chain remains verified. IP SAN and the exact fixture leaf are
        # checked explicitly because no server_hostname means no built-in
        # hostname check and, crucially, no SNI extension in this handshake.
        context.check_hostname = False
        with socket.create_connection(("127.0.0.1", self.https_port), timeout=5) as plain:
            with context.wrap_socket(plain, server_hostname=None) as secure:
                certificate = secure.getpeercert()
                actual = hashlib.sha256(secure.getpeercert(binary_form=True)).hexdigest()
        expected = hashlib.sha256(ssl.PEM_cert_to_DER_cert(
            (self.directory / "certs/server.pem").read_text())).hexdigest()
        self.record(f"{stage} no-SNI handshake verifies CA, exact TeachingOpen leaf and IP SAN despite earlier vhost",
                    actual == expected and ("IP Address", IDENTITY) in certificate.get("subjectAltName", ()),
                    {"sha256": actual, "san": certificate.get("subjectAltName")})

    def acme(self, stage, tls=False, internal=False):
        status, _, body = self.request("GET", "/.well-known/acme-challenge/runtime-token", tls=tls, internal=internal)
        self.record(f"{stage} ACME challenge serves exact body", status == 200 and body == b"synthetic-acme-response")
        status, _, body = self.request("GET", "/.well-known/acme-challenge/missing", tls=tls, internal=internal)
        self.record(f"{stage} absent ACME token returns 404 without SPA", status == 404 and b"synthetic-ip-https-spa" not in body)

    def native_business(self, stage, *, tls=False, internal=False, original=False):
        """Preserve the reviewed site's observable business rules at each stage."""
        def request(method, path, **kwargs):
            return self.request(method, path, tls=tls, internal=internal, **kwargs)

        def secure(headers, policy="same-site"):
            return all(headers.get(key) == value for key, value in SECURITY_HEADERS.items()) \
                and headers.get("cross-origin-resource-policy") == policy

        status, headers, body = request("GET", "/courses/native-fixture")
        self.record(f"{stage} SPA page preserves the original HTML body", status == 200
                    and body == b"<html>synthetic-ip-https-spa</html>\n")
        self.record(f"{stage} HTML fallback keeps no-cache", headers.get("cache-control") == "no-cache")
        self.record(f"{stage} HTML retains every reviewed security header", secure(headers), headers)
        self.record(f"{stage} preserves reversible deployment without HSTS", "strict-transport-security" not in headers)
        status, headers, body = request("GET", "/python/runner.js")
        self.record(f"{stage} public runner asset keeps body, security headers and cross-origin CORP",
                    status == 200 and body == b"/* synthetic runtime asset */\n"
                    and secure(headers, "cross-origin") and "cache-control" not in headers)
        status, headers, body = request("GET", "/python/runner.html")
        self.record(f"{stage} existing HTML keeps no-cache and same-site security policy",
                    status == 200 and body == b"<html>synthetic runner</html>\n"
                    and headers.get("cache-control") == "no-cache" and secure(headers))
        missing = []
        for path in ("/runtime-missing.js", "/runtime-missing.css", "/runtime-missing.js.gz", "/runtime-missing.css.gz"):
            status, headers, body = request("GET", path)
            missing.append({"path": path, "status": status, "safe": status == 404
                            and b"synthetic-ip-https-spa" not in body and secure(headers)})
        self.record(f"{stage} missing scripts/styles including gzip variants keep 404 and security headers",
                    all(row["safe"] for row in missing), missing)
        denied = []
        for path in ("/runtime-private.map", "/runtime-private.sql", "/logfiles/runtime-private.txt"):
            status, headers, body = request("GET", path)
            denied.append({"path": path, "status": status, "safe": status == 404
                           and b"synthetic-denied-resource" not in body and secure(headers)})
        self.record(f"{stage} existing sensitive files stay inaccessible with security headers",
                    all(row["safe"] for row in denied), denied)
        status, headers, _ = request("TRACE", "/courses/native-fixture")
        self.record(f"{stage} reviewed method restriction remains active", status == 405 and secure(headers))
        status, headers, body = request("GET", "/runtime-video.mp4", headers={"Range": "bytes=100-199"})
        self.record(f"{stage} media keeps exact byte Range and security headers", status == 206
                    and headers.get("content-range") == "bytes 100-199/4096"
                    and body == bytes(range(100, 200)) and secure(headers))
        status, headers, body = request("POST", "/api/native-loopback?probe=1", body="native-unchanged-body")
        values, details = self.echo_response(stage, "POST", "/api/native-loopback?probe=1", status, headers, body)
        self.record(f"{stage} API writes preserve method, URI, body and original scheme", status == 200
                    and values.get("method") == "POST" and values.get("uri") == "/api/native-loopback?probe=1"
                    and values.get("body") == "native-unchanged-body"
                    and values.get("scheme") == ("https" if tls else "http")
                    and (original or values.get("forwarded_proto") == ("https" if tls else "http")), details)
        self.record(f"{stage} API retains every reviewed security header", secure(headers), headers)
        if internal:
            listeners = command(["docker", "exec", self.name, "netstat", "-lnt"]).stdout
            native = [line.split()[3] for line in listeners.splitlines() if ":8088" in line]
            self.record(f"{stage} native socket listens only on container loopback", native == ["127.0.0.1:8088"], native)
            if not original:
                self.acme(stage, internal=True)
                status, headers, _ = request("GET", "/api?probe=1")
                self.record(f"{stage} bare API redirect stays relative and preserves query",
                            status == 308 and headers.get("location") == "/api/?probe=1", headers.get("location"))

    def native_stage(self, mode):
        if self.source_mode != "reviewed-native":
            return
        if mode != "https":
            self.native_business(f"{mode} HTTP")
        if mode != "bootstrap":
            self.native_business(f"{mode} HTTPS", tls=True)
        self.native_business(f"{mode} loopback HTTP", internal=True)

    def api(self, stage, tls=False):
        for method in ("GET", "POST", "PUT", "DELETE"):
            path = f"/api/runtime-echo/item%20one?method={method}&literal=a%2Fb"
            body = "synthetic-write-sentinel" if method != "GET" else None
            status, headers, response = self.request(method, path, tls=tls, body=body)
            values, details = self.echo_response(stage, method, path, status, headers, response)
            self.record(f"{stage} API {method} preserves URI, method and body",
                        status == 200 and values.get("method") == method and values.get("uri") == path
                        and values.get("body") == (body or ""), details)
            self.record(f"{stage} API {method} forwards original scheme",
                        values.get("scheme") == ("https" if tls else "http")
                        and values.get("forwarded_proto") == ("https" if tls else "http"), values.get("scheme"))
            self.record(f"{stage} API {method} keeps same-site CORP", headers.get("cross-origin-resource-policy") == "same-site")

    def api_stability(self, stage):
        """Exercise consecutive fixture connections without sleeps or retries."""
        progress = {"rounds_required": 10, "rounds_completed": 0,
                    "methods_per_round": ["GET", "POST", "PUT", "DELETE"],
                    "maximum_requests": 40, "request_retries": 0, "inter_request_delay_seconds": 0}
        self.report["api_stability"] = progress
        for number in range(1, progress["rounds_required"] + 1):
            self.api(f"{stage} consecutive round {number}/{progress['rounds_required']}")
            progress["rounds_completed"] = number
        self.record(f"{stage} consecutive API fixture stability completes 10 rounds", True, progress)

    def websocket(self):
        plain = socket.create_connection(("127.0.0.1", self.https_port), timeout=5)
        with self.context.wrap_socket(plain, server_hostname=IDENTITY) as connection:
            connection.sendall(("GET /api/runtime-websocket?probe=1 HTTP/1.1\r\n"
                                f"Host: {IDENTITY}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                                "Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n").encode())
            response = b""
            while b"\r\n\r\n" not in response:
                received = connection.recv(4096)
                if not received:
                    raise AssertionError("WebSocket handshake closed prematurely")
                response += received
            self.record("HTTPS WebSocket upgrade reaches upstream", response.startswith(b"HTTP/1.1 101 ")
                        and b"s3pPLMBiTxaQ9kYGzzhZRbK+xOo=" in response)
            connection.sendall(bytes.fromhex("818401020304716b6d63"))
            frame = b""
            while len(frame) < 6:
                received = connection.recv(6 - len(frame))
                if not received:
                    break
                frame += received
            self.record("HTTPS WebSocket tunnel echoes an actual masked text frame", frame == b"\x81\x04ping")

    def forwarded_header_boundary(self):
        spoofed_ip = "203.0.113.66"
        status, headers, response = self.request("GET", "/api/forwarded-boundary", tls=True, headers={
            "Host": f"{IDENTITY}:{self.https_port}",
            "X-Forwarded-For": f"{spoofed_ip}, 127.0.0.1",
            "X-Forwarded-Proto": "http", "X-Forwarded-Host": "attacker.invalid",
            "X-Forwarded-Port": "81", "X-Real-IP": spoofed_ip, "X-Scheme": "http"})
        values, details = self.echo_response("HTTPS forwarding boundary", "GET", "/api/forwarded-boundary",
                                            status, headers, response)
        self.record("HTTPS forwarding-boundary probe reaches synthetic API", status == 200, details)
        self.record("HTTPS overwrites forged X-Forwarded-For with the connected client address",
                    bool(values.get("forwarded_for"))
                    and values["forwarded_for"] == values.get("real_ip")
                    and values["forwarded_for"] not in (spoofed_ip, "127.0.0.1")
                    and "," not in values["forwarded_for"], values.get("forwarded_for"))
        self.record("HTTPS overwrites forged X-Real-IP", bool(values.get("real_ip"))
                    and values["real_ip"] != spoofed_ip, values.get("real_ip"))
        self.record("HTTPS overwrites forged X-Forwarded-Proto", values.get("forwarded_proto") == "https")
        self.record("HTTPS overwrites forged X-Scheme", values.get("scheme") == "https")
        self.record("HTTPS overwrites forged X-Forwarded-Host and normalizes upstream Host",
                    values.get("forwarded_host") == IDENTITY and values.get("host") == IDENTITY)
        self.record("HTTPS overwrites forged X-Forwarded-Port", values.get("forwarded_port") == "443")

    def verify(self):
        self.native_stage("bootstrap")
        self.record("bootstrap HTTP SPA fallback works", b"synthetic-ip-https-spa" in self.request("GET", "/courses/fixture")[2])
        self.acme("bootstrap HTTP")
        self.api("bootstrap HTTP")
        self.api_stability("bootstrap HTTP")
        original = (self.directory / "active.conf").read_bytes()
        previous_workers = self.workers()
        modified = self.directory / "modified-trial.conf"
        modified.write_bytes((self.directory / "rendered/trial.conf").read_bytes() + b"\n# unreviewed valid change\n")
        rejected = self.control("activate", "backup-candidate-drift", "modified-trial.conf", check=False,
                                expected_candidate_sha256=self.report["config_sha256"]["trial"])
        self.record("modified but syntactically valid candidate rejects activation before files or workers change",
                    rejected.returncode != 0 and (self.directory / "active.conf").read_bytes() == original
                    and not (self.directory / "backup-candidate-drift").exists()
                    and self.workers() == previous_workers)
        if self.source_mode == "reviewed-native":
            rejected = self.control("activate", "backup-stale-review", "rendered/trial.conf", check=False,
                                    expected_target_sha256="0" * 64)
            self.record("stale reviewed target hash rejects activation before modifying files or workers",
                        rejected.returncode != 0 and (self.directory / "active.conf").read_bytes() == original
                        and not (self.directory / "backup-stale-review").exists()
                        and self.workers() == previous_workers)
        (self.directory / "invalid.conf").write_text("invalid_nginx_directive;\n")
        failed = self.control("activate", "backup-invalid", "invalid.conf", check=False)
        self.record("invalid candidate fails and restores original bytes", failed.returncode != 0
                    and (self.directory / "active.conf").read_bytes() == original)
        self.wait_until(lambda: bool(self.workers()) and not previous_workers.intersection(self.workers()))
        self.wait_until(lambda: self.request("GET", "/")[0] == 200)
        self.record("failed activation leaves original HTTP service available", True)
        if self.source_mode == "reviewed-native":
            self.native_business("failed activation loopback HTTP", internal=True)
        self.other_tls_vhost(default=True)
        previous_workers = self.workers()
        failed = self.control("activate", "backup-default-conflict", "rendered/trial.conf", check=False)
        receipt = json.loads((self.directory / "backup-default-conflict/receipt.json").read_text())
        self.record("an existing explicit 443 default rejects activation and records exact-byte recovery",
                    failed.returncode != 0 and (self.directory / "active.conf").read_bytes() == original
                    and receipt.get("status") == "activation_failed_recovered")
        self.wait_until(lambda: bool(self.workers()) and not previous_workers.intersection(self.workers()))
        self.record("existing 443 default conflict leaves original HTTP business available",
                    self.request("GET", "/")[0] == 200)
        self.other_tls_vhost(default=False)
        self.switch("trial")
        self.no_sni_certificate("trial")
        self.native_stage("trial")
        self.acme("trial HTTP")
        self.record("trial keeps HTTP available", self.request("GET", "/")[0] == 200)
        self.record("HTTPS verifies trusted test CA and exact IP SAN", self.request("GET", "/", tls=True)[0] == 200)
        try:
            self.request("GET", "/", tls=True, identity=WRONG_IDENTITY)
        except ssl.SSLCertVerificationError:
            rejected = True
        else:
            rejected = False
        self.record("HTTPS rejects incorrect IP identity with the same trusted CA", rejected)
        self.certificate_probe()
        self.api("trial HTTPS", tls=True)
        self.forwarded_header_boundary()
        status, headers, _ = self.request("GET", "/api?probe=1", tls=True)
        self.record("HTTPS bare API redirect remains relative and preserves query",
                    status == 308 and headers.get("location") == "/api/?probe=1", headers.get("location"))
        status, headers, body = self.request("GET", "/runtime-video.mp4", tls=True, headers={"Range": "bytes=100-199"})
        self.record("HTTPS media byte Range returns exact 206 slice",
                    status == 206 and headers.get("content-range") == "bytes 100-199/4096"
                    and body == bytes(range(100, 200)))
        for path, policy in (("/python/runner.js", "cross-origin"), ("/python/runner.html", "same-site"),
                             ("/python/secret.py", "same-site")):
            status, headers, _ = self.request("GET", path, tls=True)
            self.record(f"HTTPS CORP policy {path}", status == 200 and headers.get("cross-origin-resource-policy") == policy)
        self.websocket()
        self.switch("https")
        self.no_sni_certificate("https-only")
        self.other_tls_vhost(remove=True)
        self.native_stage("https")
        self.acme("HTTPS-only mode HTTP")
        status, headers, _ = self.request("GET", "/courses/fixture?lesson=1", headers={"Host": "untrusted.invalid"})
        self.record("HTTP page temporarily redirects to fixed configured IP preserving URI",
                    status == 307 and headers.get("location") == f"https://{IDENTITY}/courses/fixture?lesson=1",
                    {"status": status, "location": headers.get("location")})
        for method, path in (("GET", "/api"), ("GET", "/api/runtime-echo"), ("POST", "/api/login"),
                             ("PUT", "/api/fixture"), ("DELETE", "/api/fixture"), ("POST", "/courses/fixture")):
            status, headers, _ = self.request(method, path, body="synthetic-sentinel" if method != "GET" else None)
            self.record(f"HTTP rejects {method} {path} without replay redirect", status == 426 and "location" not in headers)
        self.api("HTTPS-only mode HTTPS", tls=True)
        _, headers, _ = self.request("GET", "/", tls=True)
        self.record("trial deployment does not pin HSTS during reversible rollout", "strict-transport-security" not in headers)
        self.switch("trial", rollback="backup-https")
        if self.source_mode == "reviewed-native":
            self.native_business("rollback trial HTTPS", tls=True)
            self.native_business("rollback trial loopback HTTP", internal=True)
        self.record("rollback to trial restores HTTP API behavior", self.request("PUT", "/api/rollback", body="restore")[0] == 200)
        self.switch("bootstrap", rollback="backup-trial")
        if self.source_mode == "reviewed-native":
            self.native_business("rollback bootstrap HTTP")
            self.native_business("rollback bootstrap loopback HTTP", internal=True)
        self.acme("rollback bootstrap HTTP")
        self.record("rollback to bootstrap restores original HTTP site", self.request("GET", "/courses/fixture")[0] == 200)
        if self.source_mode == "reviewed-native":
            self.switch("bootstrap", rollback="backup-bootstrap")
            self.record("rollback of bootstrap restores exact original native configuration bytes",
                        (self.directory / "active.conf").read_bytes() == self.original_source)
            self.native_business("rollback original native HTTP", original=True)
            self.native_business("rollback original native loopback HTTP", internal=True, original=True)
            try:
                self.request("GET", "/", tls=True)
            except (OSError, http.client.HTTPException):
                closed = True
            else:
                closed = False
            self.record("full rollback removes the added TLS service", closed)

    def cleanup(self):
        if self.started:
            result = command(["docker", "rm", "--force", self.name], check=False)
            self.record("owned runtime container removed", result.returncode == 0)
            self.started = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="Already available official Nginx image; never pulled automatically")
    parser.add_argument("--output", type=Path, help="Save a summary JSON outside the temporary fixture directory")
    args = parser.parse_args()
    report = {"scope": "local synthetic Nginx/TLS integration; not production or real business acceptance",
              "public_ca_requested": False, "production_accessed": False,
              "client_tcp_destination": "127.0.0.1 with Docker-allocated ports and isolated container loopback:8088",
              "certificate_identity_only": IDENTITY, "checks": [], "scenarios": {}, "passed": False}
    result = 1
    try:
        for source_mode in ("template", "reviewed-native"):
            scenario = {"checks": [], "passed": False}
            with tempfile.TemporaryDirectory(prefix="teachingopen-ip-https-runtime-") as temporary:
                runtime = Runtime(Path(temporary).resolve(), args.image, scenario, source_mode)
                verification_error = None
                try:
                    runtime.prepare()
                    runtime.start()
                    runtime.verify()
                    scenario["passed"] = True
                except BaseException as exc:
                    verification_error = exc
                    scenario["error_type"] = type(exc).__name__
                    scenario["error"] = str(exc)
                    runtime.capture_diagnostics()
                    raise
                finally:
                    try:
                        runtime.cleanup()
                    except BaseException as exc:
                        scenario["passed"] = False
                        scenario["cleanup_error"] = f"{type(exc).__name__}: {exc}"
                        if verification_error is None:
                            runtime.capture_diagnostics()
                            raise
                    finally:
                        checks = scenario.pop("checks")
                        scenario["checks_passed"] = sum(check["passed"] for check in checks)
                        scenario["checks_total"] = len(checks)
                        report["scenarios"][source_mode] = scenario
                        report["checks"].extend(dict(check, scenario=source_mode) for check in checks)
                        for field in ("source_sha256", "renderer_sha256", "image"):
                            if field in scenario:
                                report[field] = scenario[field]
        report["passed"] = all(scenario["passed"] for scenario in report["scenarios"].values())
        result = 0
    except (Exception, KeyboardInterrupt) as exc:
        report["error"] = str(exc)
        report["error_type"] = type(exc).__name__
        report["passed"] = False
    report["checks_passed"] = sum(check["passed"] for check in report["checks"])
    report["checks_total"] = len(report["checks"])
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return result if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
