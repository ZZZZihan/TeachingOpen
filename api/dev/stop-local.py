#!/usr/bin/env python3
"""Stop only the database/Redis owned by the supplied local runtime."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import socket
import time
from local_runtime import assert_mysql_owner, load_ports


def stop(runtime):
    # Stopping remains possible if initialization stopped before fixtures were
    # seeded. Ownership is sufficient; shutdown must not depend on business rows.
    assert_mysql_owner(runtime)
    ports = load_ports(runtime)
    mysql = [str(runtime / "tools/mysql-8.4.6-macos15-arm64/bin/mysql"), "--defaults-extra-file=" + str(runtime / "config/mysql-admin-client.cnf"), "--batch", "--skip-column-names"]
    owned = subprocess.check_output(mysql + ["-e", "SELECT @@datadir"], text=True).strip()
    if owned != str(runtime / "mysql-data") + "/":
        raise RuntimeError("Refusing to stop another MySQL instance")
    credentials = json.loads((runtime / "config/credentials.json").read_text())
    redis = [str(runtime / "tools/redis-7.2.9/src/redis-cli"), "-h", "127.0.0.1", "-p", str(ports["redis"]), "--raw"]
    env = dict(os.environ, REDISCLI_AUTH=credentials["redis_password"])
    owned = subprocess.check_output(redis + ["CONFIG", "GET", "dir"], text=True, env=env).strip().splitlines()
    if owned != ["dir", str(runtime / "redis-data")]:
        raise RuntimeError("Refusing to stop another Redis instance")
    subprocess.run(redis + ["SHUTDOWN", "NOSAVE"], env=env, check=True)
    subprocess.run(mysql + ["-e", "SHUTDOWN"], check=True)
    for service in ("mysql", "redis"):
        for _ in range(80):
            with socket.socket() as probe:
                probe.settimeout(0.2)
                if probe.connect_ex(("127.0.0.1", ports[service])) != 0:
                    break
            time.sleep(0.25)
        else:
            raise RuntimeError("Task service still listening after shutdown: " + service)
    print("Stopped task-owned MySQL and Redis; data/configuration retained:", runtime)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    stop(args.runtime.resolve())
