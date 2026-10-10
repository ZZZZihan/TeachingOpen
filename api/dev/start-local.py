#!/usr/bin/env python3
"""Restart this retained local database/Redis without recreating any data."""
import argparse
from pathlib import Path
import socket
import subprocess
from local_runtime import load_ports


def start(runtime):
    ports = load_ports(runtime)
    mysql_config = runtime / "config/mysql.cnf"
    redis_config = runtime / "config/redis.conf"
    for config in (mysql_config, redis_config):
        if not config.is_file() or config.stat().st_mode & 0o077:
            raise RuntimeError("Expected private retained runtime configuration")
    mysql = mysql_config.read_text().splitlines()
    redis = redis_config.read_text().splitlines()
    if any(line not in mysql for line in ("bind-address=127.0.0.1", "datadir=" + str(runtime / "mysql-data"), "port=" + str(ports["mysql"]))):
        raise RuntimeError("MySQL configuration is not owned by this runtime")
    if any(line not in redis for line in ("bind 127.0.0.1", "dir " + str(runtime / "redis-data"), "port " + str(ports["redis"]))):
        raise RuntimeError("Redis configuration is not owned by this runtime")
    for service in ("mysql", "redis"):
        with socket.socket() as probe:
            # Match prepare-local: recently closed TCP connections can retain
            # TIME_WAIT sockets even after the listening service has exited.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", ports[service]))
    subprocess.run([str(runtime / "tools/mysql-8.4.6-macos15-arm64/bin/mysqld"), "--defaults-file=" + str(mysql_config), "--daemonize"], check=True)
    subprocess.run([str(runtime / "tools/redis-7.2.9/src/redis-server"), str(redis_config)], check=True)
    print("Restarted retained task database/Redis; no data imported:", runtime)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    start(parser.parse_args().runtime.resolve())
