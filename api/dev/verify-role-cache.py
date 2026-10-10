#!/usr/bin/env python3
"""Observe real permission-cache placement and logout after synthetic role changes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from local_http import FixtureApi
from local_runtime import mysql_command


def verify(args):
    results = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(query):
            return subprocess.check_output(mysql_command(api.runtime) + ["teachingopen_dev", "-e", query], text=True).strip()

        def redis(database, *arguments):
            return subprocess.check_output(api.redis + ["-n", str(database)] + list(arguments), env=api.redis_env, text=True).strip()

        def check(name, passed, **details):
            results.append({"case": name, "passed": bool(passed), **details})
            print(("PASS " if passed else "FAIL ") + name, flush=True)

        config = dict(line.split("=", 1) for line in (api.runtime / "config/application-localtest.properties").read_text().splitlines() if "=" in line and not line.startswith("#"))
        if config.get("spring.redis.database") != "1":
            raise RuntimeError("This counterexample requires the isolated fixture's Redis database 1")
        if sql("SELECT role_id FROM sys_user_role WHERE id='role_fixture_admin'") != "fixture_role_admin":
            raise RuntimeError("Unexpected fixture role; refusing to overwrite")
        key = "shiro:cache:org.jeecg.modules.shiro.authc.ShiroRealm.authorizationCache:fixture_admin"
        # Initial cleanup is limited to this test account in the verified local Redis.
        # There is deliberately no direct cache deletion between role change and check.
        for db in (0, 1):
            redis(db, "DEL", key)
        try:
            api.login("admin")
            status, body, _ = api.request("GET", "/teaching/teachingCourse/list", "admin")
            check("admin management allowed before role change", status == 200 and body and body.get("success") is True)
            expected_database = 0 if args.expect_legacy else 1
            check("permission cache stored in expected database", redis(expected_database, "EXISTS", key) == "1", database=expected_database)
            check("no duplicate permission cache in other database", redis(1 - expected_database, "EXISTS", key) == "0")
            sql("UPDATE sys_user_role SET role_id='fixture_role_teacher' WHERE id='role_fixture_admin'")
            check("synthetic account now has only teacher role", sql("SELECT r.role_code FROM sys_user_role ur JOIN sys_role r ON r.id=ur.role_id WHERE ur.user_id='fixture_admin'") == "teacher")
            status, body, _ = api.request("GET", "/sys/logout", "admin")
            check("actual logout succeeds", status == 200 and body and body.get("success") is True)
            remaining = redis(expected_database, "EXISTS", key)
            check("logout cache result matches candidate", remaining == ("1" if args.expect_legacy else "0"), stale_cache_remains=remaining == "1")
            api.login("admin")
            status, body, _ = api.request("GET", "/teaching/teachingCourse/list", "admin")
            allowed = status == 200 and body and body.get("success") is True
            denied = status == 200 and body and body.get("success") is False and body.get("code") == 510
            check("fresh login enforces expected role state", allowed if args.expect_legacy else denied, http_status=status, code=body.get("code") if body else None, management_allowed=bool(allowed))
            # Restore via the same real logout/login flow, testing both directions.
            sql("UPDATE sys_user_role SET role_id='fixture_role_admin' WHERE id='role_fixture_admin'")
            api.request("GET", "/sys/logout", "admin")
            api.login("admin")
            status, body, _ = api.request("GET", "/teaching/teachingCourse/list", "admin")
            check("restored admin can manage after fresh login", status == 200 and body and body.get("success") is True)
            api.request("GET", "/sys/logout", "admin")
            check("final logout clears configured permission cache", redis(1, "EXISTS", key) == "0")
        finally:
            sql("UPDATE sys_user_role SET role_id='fixture_role_admin' WHERE id='role_fixture_admin'")
            for db in (0, 1):
                redis(db, "DEL", key)
        check("original admin role restored", sql("SELECT role_id FROM sys_user_role WHERE id='role_fixture_admin'") == "fixture_role_admin")
        check("test principal permission caches removed", all(redis(db, "EXISTS", key) == "0" for db in (0, 1)))
        jar_hash = api.jar_sha256
    result = {"observed_utc": datetime.now(timezone.utc).isoformat(), "jar_sha256": jar_hash,
              "expected_legacy": args.expect_legacy, "configured_redis_database": 1,
              "scope": "real synthetic login/logout, database role change and Redis cache readback; no explicit eviction within the tested transition; no production role-editor acceptance",
              "passed": sum(case["passed"] for case in results), "total": len(results), "cases": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(str(result["passed"]) + "/" + str(result["total"]) + " checks passed")
    return result["passed"] == result["total"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--jar", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-legacy", action="store_true")
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
