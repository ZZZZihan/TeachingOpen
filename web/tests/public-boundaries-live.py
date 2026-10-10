#!/usr/bin/env python3
"""Read-only HTTP regression for a local synthetic TeachingOpen instance.

Set PUBLIC_BOUNDARY_BASE_URL to the API base URL and
PUBLIC_BOUNDARY_{STUDENT,TEACHER,DEV,ADMIN}_TOKEN to synthetic account tokens.
The test refuses non-loopback hosts and never writes application data.
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


def main():
    base = os.environ.get("PUBLIC_BOUNDARY_BASE_URL", "http://127.0.0.1:8089/jeecg-boot").rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("This regression accepts only a loopback synthetic API URL")
    tokens = {role: os.environ.get("PUBLIC_BOUNDARY_" + role.upper() + "_TOKEN")
              for role in ("student", "teacher", "dev", "admin")}
    if not all(tokens.values()):
        raise ValueError("All four synthetic role tokens are required")
    calls = 0
    checks = []
    outgoing = []

    class Sink(BaseHTTPRequestHandler):
        def do_GET(self):
            outgoing.append(self.command)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"probe":true}')

        do_POST = do_GET
        do_PUT = do_GET
        do_DELETE = do_GET
        do_PATCH = do_GET

        def log_message(self, *args):
            pass

    def request(path, role=None, params=None, method="GET"):
        nonlocal calls
        calls += 1
        address = base + path
        if params:
            address += "?" + urlencode(params)
        headers = {"Accept": "application/json"}
        if role:
            headers["X-Access-Token"] = tokens[role]
        req = Request(address, headers=headers, method=method)
        try:
            with urlopen(req, timeout=15) as response:
                return response.status, json.load(response)
        except HTTPError as failure:
            try:
                payload = json.load(failure)
            except (ValueError, TypeError):
                payload = None
            return failure.code, payload

    def denied(path, role=None, params=None, method="GET"):
        status, payload = request(path, role, params, method)
        assert status in {400, 401, 403} or (
            status == 200 and isinstance(payload, dict) and payload.get("success") is False
        ), "Request was not denied: " + str((role, method, path, status))
        checks.append({"case": str((role, method, path, params, "denied")), "passed": True})

    def permitted(path, role=None, params=None):
        status, payload = request(path, role, params)
        assert status == 200 and payload.get("success") is True, "Control failed: " + str((role, path, status))
        checks.append({"case": str((role, path, params, "permitted")), "passed": True})
        return payload.get("result")

    permitted("/sys/dict/getDictItems/sex")
    purposes = ["course_options", "registration_roles", "category_tree", "system_users"]
    for role in (None, "student", "teacher"):
        for purpose in purposes + ["sys_user,realname,id"]:
            encoded = quote(purpose, safe="")
            denied("/sys/dict/getDictItems/" + encoded, role)
            denied("/sys/dict/loadDict/" + encoded, role, {"keyword": "合成"})
            denied("/sys/dict/loadDictItem/" + encoded, role, {"key": "synthetic-id"})
        denied("/sys/dict/loadTreeData", role, {"dictCode": "category_tree", "pid": "0"})
        denied("/sys/dict/queryTableData", role, {"table": "sys_user", "text": "password", "code": "id"})

    for role in ("admin", "dev"):
        for purpose in ["sys_user,password,id", "sys_user,salt,id", "sys_user,phone,id",
                        "sys_user,realname,id,username!='admin'", "sys_user,realname,id,",
                        "sys_user%2Cpassword%2Cid"]:
            encoded = quote(purpose, safe="")
            denied("/sys/dict/getDictItems/" + encoded, role)
            denied("/sys/dict/loadDict/" + encoded, role, {"keyword": "合成"})
            denied("/sys/dict/loadDictItem/" + encoded, role, {"key": "synthetic-id"})
        denied("/sys/dict/queryTableData", role, {"table": "sys_user", "text": "password", "code": "id"})
        for mutation in [{"pidField": "password"}, {"hasChildField": "salt"},
                         {"condition": '{"password":"probe"}'},
                         {"tableName": "sys_user", "text": "password", "code": "id"}]:
            denied("/sys/dict/loadTreeData", role, {"dictCode": "category_tree", "pid": "0", **mutation})
        named = permitted("/sys/dict/getDictItems/course_options", role)
        legacy = permitted("/sys/dict/getDictItems/teaching_course%2Ccourse_name%2Cid", role)
        assert named == legacy, "Named and legacy course options differ"
        permitted("/sys/dict/loadTreeData", role, {"dictCode": "category_tree", "pid": "0"})
        permitted("/sys/dict/loadDict/system_departments", role, {"keyword": "合成"})
        permitted("/sys/dict/loadDictItem/system_departments", role, {"key": "synthetic-id"})
    denied("/sys/dict/getDictItems/registration_roles", "dev")
    permitted("/sys/dict/getDictItems/registration_roles", "admin")

    sink = ThreadingHTTPServer(("127.0.0.1", 0), Sink)
    worker = threading.Thread(target=sink.serve_forever, daemon=True)
    worker.start()
    destination = "http://127.0.0.1:" + str(sink.server_port) + "/probe"
    try:
        for role in (None, "student", "teacher", "dev", "admin"):
            for method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                for address in (destination, quote(destination, safe="")):
                    denied("/sys/common/transitRESTful", role, {"url": address}, method)
        assert not outgoing, "Disabled transit initiated an outbound request"
    finally:
        sink.shutdown()
        sink.server_close()
        worker.join(timeout=2)
    result = {"success": True, "requests": calls, "outboundRequests": len(outgoing),
              "scope": "local synthetic HTTP", "roles": list(tokens), "checks": checks}
    print(json.dumps({key: value for key, value in result.items() if key != "checks"}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    main()
