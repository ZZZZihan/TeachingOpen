#!/usr/bin/env python3
"""Verify actual missing/invalid/revoked login responses against a local JAR."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from local_http import FixtureApi


def verify(args):
    results = []
    with FixtureApi(args.runtime, args.jar) as api:
        path = "/teaching/teachingCourse/mineCourse"
        expected = 500 if args.expect_legacy else 401
        def check(name, method, route, expected_status, **kwargs):
            status, payload, content_type = api.request(method, route, **kwargs)
            passed = status == expected_status
            if expected_status == 401:
                passed = passed and content_type.startswith("application/json") and payload is not None and payload.get("success") is False and payload.get("code") == 401
            if expected_status == 200 and method != "OPTIONS":
                passed = passed and payload is not None and payload.get("success") is True
            results.append({"case": name, "http_status": status, "passed": bool(passed)})
        check("missing login credential", "GET", path, expected)
        check("empty login credential", "GET", path, expected, token="")
        check("malformed login credential", "GET", path, expected, token="invalid-fixture-token")
        check("anonymous public courses", "GET", "/teaching/teachingCourse/getHomeCourse", 200)
        check("preflight remains available", "OPTIONS", path, 200)
        api.login("student_a")
        check("valid student credential", "GET", path, 200, actor="student_a")
        api.request("GET", "/sys/logout", "student_a")
        check("revoked login credential", "GET", path, expected, actor="student_a")
        jar_sha256 = api.jar_sha256
    result = {"observed_utc": datetime.now(timezone.utc).isoformat(), "jar_sha256": jar_sha256,
              "expected_legacy_500": args.expect_legacy, "cases": results,
              "passed": sum(item["passed"] for item in results), "total": len(results),
              "scope": "real local HTTP, CAPTCHA, login and logout; no role/asset permission acceptance"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    if result["passed"] != result["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--jar", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-legacy", action="store_true")
    verify(parser.parse_args())
