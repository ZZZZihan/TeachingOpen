#!/usr/bin/env python3
"""Exercise authentication and refresh logs without exposing synthetic credentials."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import subprocess
import time

from local_http import FixtureApi
from local_runtime import mysql_command


def encode(value):
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=")


def claims(token):
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def verify(args):
    results = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def check(name, passed):
            results.append({"case": name, "passed": bool(passed)})
            print(("PASS " if passed else "FAIL ") + name, flush=True)

        config = (api.runtime / "config/application-localtest.properties").read_text()
        if "logging.level.org.jeecg.modules.shiro.authc.ShiroRealm=DEBUG" not in config.splitlines():
            raise RuntimeError("Enable the synthetic runtime's ShiroRealm DEBUG logger before this check")
        process = json.loads((api.runtime / "backend-process.json").read_text())
        log = Path(process["log_path"]).resolve()
        if log.parent != (api.runtime / "logs").resolve() or log.stat().st_mode & 0o077:
            raise RuntimeError("Expected private log owned by this synthetic runtime")
        offset = log.stat().st_size
        api.login("student_a")
        token = api.tokens["student_a"]
        route = "/teaching/teachingCourseUnit/getUnitWorkInfo?unitId=fixture_unit_a"
        status, body, _ = api.request("GET", route, "student_a")
        check("valid synthetic session reads assigned unit", status == 200 and body and body.get("success") is True)

        # A genuinely expired, correctly signed cache JWT exercises the refresh
        # branch immediately. Only this fresh synthetic session's cache is changed.
        secret = subprocess.check_output(mysql_command(api.runtime) + ["teachingopen_dev", "-e",
                    "SELECT password FROM sys_user WHERE id='fixture_student_a'"], text=True).strip()
        unsigned = encode({"alg": "HS256", "typ": "JWT"}) + b"." + encode({"username": "fixture_student_a", "exp": int(time.time()) - 60})
        signature = base64.urlsafe_b64encode(hmac.new(secret.encode(), unsigned, hashlib.sha256).digest()).rstrip(b"=")
        expired = (unsigned + b"." + signature).decode()
        key = "userToken:" + token
        if json.loads(api.cache("GET", key)) != token:
            raise RuntimeError("Unexpected initial cache value for fresh synthetic session")
        ttl = int(api.cache("TTL", key))
        if ttl <= 0:
            raise RuntimeError("Synthetic session cache expired before check")
        api.cache("SET", key, json.dumps(expired), "EX", str(ttl))
        check("owned session cache contains an expired signed JWT", claims(expired)["exp"] < time.time() and json.loads(api.cache("GET", key)) == expired)
        status, body, _ = api.request("GET", route, "student_a")
        check("expired cache JWT refresh keeps assigned unit accessible", status == 200 and body and body.get("success") is True)
        refreshed = json.loads(api.cache("GET", key))
        check("refresh writes a live JWT and positive cache lifetime", refreshed != expired and claims(refreshed)["exp"] > time.time() and int(api.cache("TTL", key)) > 0)
        status, body, _ = api.request("GET", route, "student_a")
        check("next request still authenticates after refresh", status == 200 and body and body.get("success") is True)
        status, body, _ = api.request("GET", "/sys/logout", "student_a")
        check("actual logout succeeds and removes session cache", status == 200 and body and body.get("success") is True and api.cache("EXISTS", key) == "0")
        status, body, _ = api.request("GET", route, "student_a")
        check("logged-out credential remains rejected", status == 401 and body and body.get("code") == 401)

        # Never write log excerpts or JWT values to evidence or stdout.
        for _ in range(20):
            with log.open("rb") as stream:
                stream.seek(offset)
                captured = stream.read().decode(errors="replace")
            if "jwtTokenRefresh" in captured:
                break
            time.sleep(0.1)
        auth_lines = [line for line in captured.splitlines() if "checkUserTokenIsEffect" in line and "DEBUG" in line]
        refresh_lines = [line for line in captured.splitlines() if "jwtTokenRefresh" in line and "INFO" in line]
        check("DEBUG authentication event actually observed", bool(auth_lines))
        check("INFO refresh event actually observed", bool(refresh_lines))
        check("authentication log token exposure matches candidate", any(token in line for line in auth_lines) == args.expect_legacy)
        check("refresh log token exposure matches candidate", any(token in line for line in refresh_lines) == args.expect_legacy)
        check("captured request log credential exposure matches candidate", any(value in captured for value in (token, expired, refreshed)) == args.expect_legacy)
        check("no password material in captured request log", secret not in captured and api.credentials["test_user_password"] not in captured)
        jar_hash = api.jar_sha256
    result = {"observed_utc": datetime.now(timezone.utc).isoformat(), "jar_sha256": jar_hash,
              "expected_legacy": args.expect_legacy,
              "scope": "real HTTP authentication, owned Redis cache JWT expiry/refresh, DEBUG and INFO log observation, logout and revocation; no log excerpts or credentials exported",
              "passed": sum(case["passed"] for case in results), "total": len(results), "cases": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(str(result["passed"]) + "/" + str(result["total"]) + " checks passed")
    return result["passed"] == result["total"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--jar", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expect-legacy", action="store_true")
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
