#!/usr/bin/env python3
"""Observe exact-JAR Shiro context and narrow HTTP compatibility in an owned local fixture.

Context creates and closes its own random-loopback-port application; run serially
with fixture mutations. HTTP does not login unless --actor is explicitly supplied.
No account, credential, response body, or raw application log enters the report.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import uuid
import zipfile

from local_runtime import assert_app_config, assert_database, mysql_command

JAVA_SOURCE = Path(__file__).resolve().parents[1] / "jeecg-boot-module-system/src/test/java/org/jeecg/maintenance/VerifyShiroMaintenance.java"
MARKER = "SHIRO_MAINTENANCE_JSON "


def exact_jar_probe(args):
    with tempfile.TemporaryDirectory(prefix="teaching-shiro-context-") as temporary:
        root = Path(temporary)
        classes, libraries, probe = root / "classes", root / "lib", root / "probe"
        classes.mkdir(); libraries.mkdir(); probe.mkdir()
        shiro = []
        with zipfile.ZipFile(args.jar) as jar:
            for name in jar.namelist():
                if name.startswith("BOOT-INF/lib/") and name.endswith(".jar"):
                    (libraries / Path(name).name).write_bytes(jar.read(name))
                    if Path(name).name.startswith("shiro-"):
                        shiro.append(Path(name).name)
                elif name.startswith("BOOT-INF/classes/") and not name.endswith("/"):
                    target = classes / name.removeprefix("BOOT-INF/classes/")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(jar.read(name))
        classpath = str(probe) + ":" + str(classes) + ":" + str(libraries / "*")
        compiled = subprocess.run([str(args.java_home / "bin/javac"), "-encoding", "UTF-8", "-cp", classpath,
                                   "-d", str(probe), str(JAVA_SOURCE)], capture_output=True, text=True, timeout=60)
        if compiled.returncode:
            # Compiler output contains only test source paths/type diagnostics.
            raise RuntimeError("Test harness compilation failed:\n" + compiled.stderr)
        if args.phase == "compile":
            return {"scope": "exact packaged libraries and classes; compilation only, no application started",
                    "checks": [{"case": "Java 8 test launcher compiles against candidate JAR", "passed": True}],
                    "observations": [{"case": "packaged Shiro libraries", "value": sorted(shiro)}]}
        assert_app_config(args.runtime)
        assert_database(args.runtime)
        command = [str(args.java_home / "bin/java"), "-Xms128m", "-Xmx768m", "-cp", classpath,
                   "org.jeecg.maintenance.VerifyShiroMaintenance", "--spring.profiles.active=dev,localtest",
                   "--spring.config.additional-location=file:" + str(args.runtime / "config") + "/",
                   "--server.address=127.0.0.1", "--server.port=0"]
        with subprocess.Popen(command, cwd=args.runtime / "webapp", stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
            try:
                stdout, _ = process.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, _ = process.communicate()
                progress = [line[len("SHIRO_MAINTENANCE_PROGRESS "):] for line in stdout.splitlines() if line.startswith("SHIRO_MAINTENANCE_PROGRESS ")]
                return {"scope": "exact JAR context probe; timeout and raw application logs withheld",
                        "checks": [{"case": "owned test-only context completes within 120 seconds", "passed": False}],
                        "observations": [{"case": "sanitized stages before timeout", "value": progress},
                                         {"case": "owned context process terminated", "value": {"pid": process.pid, "exit_status": process.returncode, "exited": True}}]}
            process_pid, exit_status = process.pid, process.returncode
        # Startup diagnostics can contain private fixture configuration. Retain
        # only the explicit sanitized marker, never the surrounding logs.
        reports = [json.loads(line[len(MARKER):]) for line in stdout.splitlines() if line.startswith(MARKER)]
        if len(reports) != 1:
            return {"scope": "exact JAR context probe; raw startup output withheld",
                    "checks": [{"case": "test launcher produced one sanitized result", "passed": False}],
                    "observations": [{"case": "launcher exit status", "value": exit_status}, {"case": "owned context process exited", "value": {"pid": process_pid, "exited": True}}]}
        report = reports[0]
        if exit_status != 0 and all(value["passed"] for value in report["checks"]):
            report["checks"].append({"case": "owned test launcher exits successfully", "passed": False})
        report["observations"].append({"case": "owned context process exited", "value": {"pid": process_pid, "exit_status": exit_status, "exited": True}})
        report["observations"].append({"case": "packaged Shiro libraries", "value": sorted(shiro)})
        return report


def verify_disabled_account(api, actor, manager_actor=None):
    """One narrow state-change case. Preserve cached behavior; do not evict it."""
    checks, observations = [], []
    def check(name, passed):
        checks.append({"case": name, "passed": bool(passed)})
    def sql(value):
        return subprocess.check_output(mysql_command(api.runtime) + ["teachingopen_dev", "-e", value], text=True).strip()
    def literal(value):
        return "CONVERT(0x" + value.encode("utf-8").hex() + " USING utf8mb4)"
    if actor not in api.tokens:
        api.login(actor)
    status, result, _ = api.request("GET", "/teaching/teachingCourse/mineCourse", actor)
    check("credential is valid before temporary account disable", status == 200 and result and result.get("success") is True)
    encoded = api.tokens[actor].split(".")[1]
    principal = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))["username"]
    row = sql("SELECT id,status FROM sys_user WHERE username=" + literal(principal)).split("\t")
    if len(row) != 2 or not principal.startswith("fixture_"):
        raise RuntimeError("Only the synthetic fixture principal may be disabled")
    identity, before = row
    if manager_actor is not None:
        if manager_actor == actor:
            raise ValueError("Freeze and restore require a separate synthetic manager")
        if manager_actor not in api.tokens:
            api.login(manager_actor)
    def update(value, operation):
        if manager_actor is None:
            sql("UPDATE sys_user SET status=" + str(int(value)) + " WHERE id=" + literal(identity))
        else:
            changed_status, changed, _ = api.request("PUT", "/sys/user/frozenBatch", manager_actor, data={"ids": identity, "status": str(value)})
            check("normal account " + operation + " endpoint updates database state", changed_status == 200 and changed
                  and changed.get("success") is True and sql("SELECT status FROM sys_user WHERE id=" + literal(identity)) == str(value))
    try:
        update(2, "freeze")
        confirmed = sql("SELECT status FROM sys_user WHERE id=" + literal(identity)) == "2"
        status, result, _ = api.request("GET", "/teaching/teachingCourse/mineCourse", actor)
        observations.append({"case": "previously valid credential while fixture account disabled; cache untouched",
                             "fixture_disabled_in_database": confirmed, "http_status": status,
                             "api_code": (result or {}).get("code"), "api_success": (result or {}).get("success")})
        check("disabled account rejects its previously valid credential", confirmed and status == 401 and result and result.get("code") == 401)
    finally:
        try:
            update(int(before), "restore")
        finally:
            # Even a network exception during the application restore must not
            # leave this one owned fixture row disabled.
            if sql("SELECT status FROM sys_user WHERE id=" + literal(identity)) != before:
                sql("UPDATE sys_user SET status=" + str(int(before)) + " WHERE id=" + literal(identity))
    check("disabled account state is restored", sql("SELECT status FROM sys_user WHERE id=" + literal(identity)) == before)
    status, result, _ = api.request("GET", "/teaching/teachingCourse/mineCourse", actor)
    check("same credential works after account state restoration", status == 200 and result and result.get("success") is True)
    return {"scope": "actual candidate JAR HTTP; one owned fixture account disabled via " + ("normal frozenBatch endpoint" if manager_actor is not None else "SQL") + " and restored; user cache untouched; no production",
            "checks": checks, "observations": observations}


def verify_http(api, actor=None):
    """Root may call this serially with its existing authenticated FixtureApi."""
    checks, observations = [], []
    prefix = "shiro_name_" + uuid.uuid4().hex[:12]
    sandbox = api.runtime / "uploads" / prefix
    payload = b"Synthetic Shiro maintenance media bytes\n"
    def check(name, passed):
        checks.append({"case": name, "passed": bool(passed)})
    def sql(value):
        return subprocess.check_output(mysql_command(api.runtime) + ["teachingopen_dev", "-e", value], text=True).strip()
    def literal(value):
        return "CONVERT(0x" + value.encode("utf-8").hex() + " USING utf8mb4)"
    def get(path, headers=None):
        request = Request("http://127.0.0.1:" + str(api.ports["backend"]) + "/api" + path, headers=headers or {}, method="GET")
        try:
            response = urlopen(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read(), response.headers
    def snapshot():
        return hashlib.sha256(sql("SELECT * FROM sys_config ORDER BY id").encode()).hexdigest()
    original = snapshot()
    if sandbox.exists() or sql("SELECT COUNT(*) FROM sys_config WHERE id LIKE '" + prefix + "%'") != "0":
        raise RuntimeError("Probe namespace already exists")
    sandbox.mkdir()
    try:
        for index, name in enumerate(["space name.txt", "plus+name.txt", "50%name.txt", "课程.txt"]):
            (sandbox / name).write_bytes(payload)
            # URI references must be valid paths: encode spaces/percent while
            # retaining literal plus, which is a path character, not form data.
            reference = "/api/sys/common/static/" + quote(prefix + "/" + name, safe="/+")
            sql("INSERT INTO sys_config (id,config_key,config_value,config_enabled) VALUES (" + literal(prefix + str(index))
                + "," + literal(prefix + str(index)) + "," + literal('<img src="' + reference + '">') + ",1)")
            status, body, headers = get("/sys/common/static/" + quote(prefix + "/" + name, safe="/"))
            if name == "课程.txt":
                observations.append({"case": "Unicode media filename existing restriction; not support acceptance", "http_status": status,
                                     "returned_expected_bytes": body == payload})
            else:
                check("public media preserves " + name + " bytes", status == 200 and body == payload and headers.get("Cache-Control") == "no-store")
        finite = ["/sys/common/static/" + prefix + "/a;segment.txt", "/sys/common/static/" + prefix + "/a%5cb.txt",
                  "/sys/common/static/" + prefix + "/%2e%2e/missing.txt", "/sys/common/static/" + prefix + "/a%2fb.txt"]
        for index, path in enumerate(finite):
            status, body, _ = get(path)
            check("finite invalid media path denied " + str(index + 1), status in (400, 401, 403, 404) and body != payload)
        optional = "/teaching/teachingWork/getWorkComments?workId=" + quote(prefix)
        status, body, _ = get(optional, {"X-Access-Token": "synthetic-malformed-credential"})
        try:
            denied = json.loads(body)
        except ValueError:
            denied = {}
        check("optional JWT rejects a supplied malformed credential", status == 401 and denied.get("success") is False and denied.get("code") == 401)
        status, body, headers = get("/teaching/teachingCourse/mineCourse", {"Cookie": "rememberMe=not-a-session"})
        check("harmless rememberMe cookie cannot authenticate", status == 401)
        check("disabled rememberMe emits no rememberMe cookie", not any(value.startswith("rememberMe=") for value in headers.get_all("Set-Cookie", [])))
        if actor is not None:
            disabled = verify_disabled_account(api, actor)
            checks.extend(disabled["checks"])
            observations.extend(disabled["observations"])
        else:
            observations.append({"case": "disabled account check", "value": "not run; requires root's explicit synthetic actor"})
    finally:
        sql("DELETE FROM sys_config WHERE id LIKE '" + prefix + "%'")
        for path in sandbox.iterdir():
            path.unlink()
        sandbox.rmdir()
    check("public media reference rows restored", snapshot() == original)
    check("owned media files removed", not sandbox.exists())
    return {"scope": "actual candidate JAR HTTP in owned synthetic runtime; finite media paths and optional-JWT/rememberMe compatibility; no production or browser acceptance",
            "checks": checks, "observations": observations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--java-home", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--phase", choices=("compile", "context", "http", "disabled", "frozen"), default="context")
    parser.add_argument("--actor", help="Explicit synthetic actor for root's serial disabled-account case; never recorded")
    parser.add_argument("--manager-actor", help="Explicit separate synthetic manager for normal freeze/restore; never recorded")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.jar = args.jar.resolve()
    if args.runtime:
        args.runtime = args.runtime.resolve()
    if (args.phase in ("compile", "context") and not args.java_home) or (args.phase != "compile" and not args.runtime):
        parser.error("context needs --java-home/--runtime; compile needs --java-home; http needs --runtime")
    if args.phase in ("disabled", "frozen") and not args.actor:
        parser.error("disabled needs an explicit synthetic --actor")
    if args.phase == "frozen" and not args.manager_actor:
        parser.error("frozen needs an explicit separate --manager-actor")
    if args.phase in ("http", "disabled", "frozen"):
        from local_http import FixtureApi
        with FixtureApi(args.runtime, args.jar) as api:
            result = verify_http(api, args.actor) if args.phase == "http" else verify_disabled_account(api, args.actor, args.manager_actor if args.phase == "frozen" else None)
    else:
        result = exact_jar_probe(args)
    result.update({"observed_utc": datetime.now(timezone.utc).isoformat(), "jar_sha256": hashlib.sha256(args.jar.read_bytes()).hexdigest(),
                   "phase": args.phase, "passed": sum(value["passed"] for value in result["checks"]), "total": len(result["checks"])})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(str(result["passed"]) + "/" + str(result["total"]) + " checks passed; observations are separate")
    raise SystemExit(0 if result["passed"] == result["total"] else 1)


if __name__ == "__main__":
    main()
