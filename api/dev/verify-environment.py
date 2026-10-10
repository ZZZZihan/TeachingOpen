#!/usr/bin/env python3
"""Verify runtime ownership, packaged app health and synthetic seed data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.request import urlopen
from local_runtime import assert_database, load_ports, mysql_command


def verify(runtime, output):
    assert_database(runtime)
    ports = load_ports(runtime)
    process = json.loads((runtime / "backend-process.json").read_text())
    jar = Path(__file__).resolve().parents[1] / "jeecg-boot-module-system/target/teaching-open-2.8.0.jar"
    command = subprocess.check_output(["ps", "-p", str(process["pid"]), "-o", "command="], text=True)
    if process["jar_path"] != str(jar) or str(jar) not in command or "--spring.profiles.active=dev,localtest" not in command:
        raise RuntimeError("Running process does not belong to this source worktree")
    if process["jar_sha256"] != hashlib.sha256(jar.read_bytes()).hexdigest():
        raise RuntimeError("Running app differs from current packaged artifact")
    def query(sql):
        return subprocess.check_output(mysql_command(runtime) + ["teachingopen_dev", "-e", sql], text=True).strip()
    credentials = json.loads((runtime / "config/credentials.json").read_text())
    redis = [str(runtime / "tools/redis-7.2.9/src/redis-cli"), "-h", "127.0.0.1", "-p", str(ports["redis"]), "--raw"]
    env = dict(os.environ, REDISCLI_AUTH=credentials["redis_password"])
    redis_dir = subprocess.check_output(redis + ["CONFIG", "GET", "dir"], env=env, text=True).strip().splitlines()
    def get(path):
        with urlopen("http://127.0.0.1:" + str(ports["backend"]) + "/api" + path, timeout=5) as response:
            return json.loads(response.read())
    courses = get("/teaching/teachingCourse/getHomeCourse")
    checks = {
        "owned_synthetic_database": True,
        "owned_redis": redis_dir == ["dir", str(runtime / "redis-data")],
        "packaged_app_matches_worktree": True,
        "health_up": get("/actuator/health").get("status") == "UP",
        "schema_69_tables": query("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='teachingopen_dev'") == "69",
        "three_roles": query("SELECT COUNT(*) FROM sys_role WHERE role_code IN ('admin','teacher','student')") == "3",
        "two_courses": courses.get("success") is True and {r["id"] for r in courses.get("result", {}).get("records", [])} == {"fixture_course_a", "fixture_course_b"},
        "fixture_attachments": all((runtime / "uploads" / ("fixture-work-" + suffix + ".txt")).read_text() == "synthetic work " + suffix + "\n" for suffix in ("a", "b")),
        "private_credentials": not (runtime / "config/credentials.json").stat().st_mode & 0o077,
    }
    result = {"observed_utc": datetime.now(timezone.utc).isoformat(), "ports": ports,
              "jar_sha256": process["jar_sha256"], "checks": checks,
              "passed": sum(checks.values()), "total": len(checks),
              "scope": "environment readiness only; no role/authorization/business acceptance"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify(args.runtime.resolve(), args.output.resolve())
