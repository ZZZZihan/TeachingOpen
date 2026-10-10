#!/usr/bin/env python3
"""Start/stop only this workspace's backend with its private localtest profile."""
import argparse
import hashlib
import json
from pathlib import Path
import os
import signal
import socket
import subprocess
import time
from uuid import uuid4
from local_runtime import load_ports, assert_database, assert_app_config


def run(runtime, java_home, action, log_name, jar=None):
    api = Path(__file__).resolve().parents[1]
    packaged = jar is not None
    jar = jar or api / "jeecg-boot-module-system/target/teaching-open-2.8.0.jar"
    config_arg = "--spring.config.additional-location=file:" + str(runtime / "config") + "/"
    pid_file = runtime / "backend.pid"
    if action == "stop":
        if not pid_file.exists():
            print("No recorded backend PID")
            return
        pid = int(pid_file.read_text().strip())
        result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True)
        if result.returncode:
            print("Recorded backend has already exited")
        elif str(jar) not in result.stdout or "--spring.profiles.active=dev,localtest" not in result.stdout or config_arg not in result.stdout:
            raise RuntimeError("PID belongs to another process; refusing to stop it")
        else:
            os.kill(pid, signal.SIGTERM)
            for _ in range(80):
                status = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True)
                if status.returncode or status.stdout.strip().startswith("Z"):
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError("Task backend did not exit after SIGTERM; inspect its private log")
            print("Stopped task backend PID", pid)
        return
    if not jar.is_file() or not os.access(java_home / "bin/java", os.X_OK):
        raise RuntimeError("Build the candidate JAR and provide an executable Java runtime first")
    assert_app_config(runtime)
    assert_database(runtime)
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", load_ports(runtime)["backend"]))
    log = runtime / "logs" / (log_name or "backend-" + uuid4().hex[:12] + ".log")
    if log.parent.resolve() != (runtime / "logs").resolve():
        raise RuntimeError("Log name must be a file directly inside the runtime logs directory")
    log.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as out:
        process = subprocess.Popen([str(java_home / "bin/java"), "-Xms256m", "-Xmx1g", "-jar", str(jar), "--spring.profiles.active=dev,localtest", config_arg], cwd=runtime / "webapp" if packaged else jar.parent, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    pid_file.write_text(str(process.pid) + "\n")
    (runtime / "backend-process.json").write_text(json.dumps({"pid": process.pid, "jar_path": str(jar), "jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(), "profile": "dev,localtest", "log_path": str(log)}, indent=2) + "\n")
    print("Started task backend PID", process.pid)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop"))
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--log-name")
    args = parser.parse_args()
    run(args.runtime.resolve(), args.java_home.resolve(), args.action, args.log_name)
