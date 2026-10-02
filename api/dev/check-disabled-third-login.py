#!/usr/bin/env python3
"""Probe a packaged app with third-party login disabled in the local fixture only."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from local_runtime import assert_database, load_ports


def check(args):
    runtime = args.runtime.resolve()
    jar = args.jar.resolve()
    config = runtime / "config/application-localtest.properties"
    ports = load_ports(runtime)
    if not config.is_file() or config.stat().st_mode & 0o077:
        raise RuntimeError("Expected private local fixture configuration")
    properties = {}
    for line in config.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            properties[key.strip()] = value.strip()
    required = {
        "server.address": "127.0.0.1",
        "server.servlet.context-path": "/api",
        "spring.redis.host": "127.0.0.1",
        "spring.redis.port": str(ports["redis"]),
        "spring.quartz.auto-startup": "false",
    }
    if any(properties.get(key) != value for key, value in required.items()):
        raise RuntimeError("Refusing a configuration outside the local fixture")
    url = properties.get("spring.datasource.dynamic.datasource.master.url", "")
    if not url.startswith("jdbc:mysql://127.0.0.1:" + str(ports["mysql"]) + "/teachingopen_dev?"):
        raise RuntimeError("Refusing a database outside the local fixture")
    accounts = json.loads((runtime / "fixture-accounts.json").read_text())
    if set(accounts) != {"fixture_admin", "fixture_teacher_a", "fixture_teacher_b", "fixture_student_a", "fixture_student_b"}:
        raise RuntimeError("Unexpected fixture account manifest")
    assert_database(runtime)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    evidence_dir = Path(tempfile.mkdtemp(prefix="disabled-login-", dir=runtime))
    log_path = evidence_dir / "boot.log"
    command = [str(args.java_home.resolve() / "bin/java"), "-Xms128m", "-Xmx768m", "-jar", str(jar),
               "--spring.profiles.active=dev,localtest",
               "--spring.config.additional-location=file:" + str(runtime / "config") + "/",
               "--server.port=" + str(args.port), "--justauth.enabled=false"]
    result = {"jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
              "expected": args.expect, "port": args.port, "profile": "dev,localtest",
              "justauth_enabled": False, "healthy": False, "public_courses": False}
    process = None
    try:
        with log_path.open("xb") as log:
            log_path.chmod(0o600)
            process = subprocess.Popen(command, cwd=evidence_dir, stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 60
            base = "http://127.0.0.1:" + str(args.port) + "/api"
            while time.monotonic() < deadline and process.poll() is None:
                try:
                    with urlopen(base + "/actuator/health", timeout=1) as response:
                        result["healthy"] = json.loads(response.read()).get("status") == "UP"
                    if result["healthy"]:
                        break
                except (URLError, HTTPError, TimeoutError, ValueError):
                    pass
                time.sleep(0.25)
            if result["healthy"]:
                with urlopen(base + "/teaching/teachingCourse/getHomeCourse", timeout=5) as response:
                    result["public_courses"] = json.loads(response.read()).get("success") is True
            else:
                # Retain only diagnostic markers, never the full private log/config.
                log_text = log_path.read_text(errors="replace")
                result["missing_factory_failure"] = (
                    process.poll() is not None and "AuthRequestFactory" in log_text
                    and "thirdLoginController" in log_text
                    and ("could not be found" in log_text or "No qualifying bean" in log_text))
                result["process_exit_code"] = process.poll()
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        result["probe_process_stopped"] = process is not None and process.poll() is not None
    result["passed"] = result["probe_process_stopped"] and (
        result["healthy"] and result["public_courses"] if args.expect == "up"
        else not result["healthy"] and result.get("missing_factory_failure") is True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--jar", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18093)
    parser.add_argument("--expect", choices=("up", "missing-factory"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    check(parser.parse_args())
