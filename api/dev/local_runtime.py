"""Shared addressing and ownership checks for local synthetic runtimes."""
import json
import subprocess

DEFAULT_PORTS = {"mysql": 13306, "redis": 16379, "backend": 18091, "frontend": 18092}


def validate_ports(ports):
    if set(ports) != set(DEFAULT_PORTS) or any(type(p) is not int or not 1024 <= p <= 65535 for p in ports.values()):
        raise ValueError("Use four integer ports between 1024 and 65535")
    if len(set(ports.values())) != 4:
        raise ValueError("MySQL, Redis, backend and frontend need distinct ports")
    return ports


def load_ports(runtime):
    manifest = runtime / "ports.json"
    # Existing task runtimes predate the manifest and use these exact ports.
    return validate_ports(json.loads(manifest.read_text()) if manifest.is_file() else dict(DEFAULT_PORTS))


def mysql_command(runtime):
    return [str(runtime / "tools/mysql-8.4.6-macos15-arm64/bin/mysql"),
            "--defaults-extra-file=" + str(runtime / "config/mysql-admin-client.cnf"),
            "--batch", "--skip-column-names"]


def assert_mysql_owner(runtime):
    actual = subprocess.check_output(mysql_command(runtime) + ["-e", "SELECT CONCAT(@@datadir,'|',@@port)"], text=True).strip()
    if actual != str(runtime / "mysql-data") + "/|" + str(load_ports(runtime)["mysql"]):
        raise RuntimeError("Actual MySQL instance is not owned by this runtime")


def assert_database(runtime, empty=False):
    query = "SELECT CONCAT(@@datadir,'|',@@port,'|',COUNT(*),'|',COALESCE(SUM(username LIKE 'fixture_%'),0)) FROM teachingopen_dev.sys_user"
    actual = subprocess.check_output(mysql_command(runtime) + ["-e", query], text=True).strip()
    count = "0|0" if empty else "5|5"
    if actual != str(runtime / "mysql-data") + "/|" + str(load_ports(runtime)["mysql"]) + "|" + count:
        raise RuntimeError("Actual database is not the expected isolated synthetic fixture")


def assert_app_config(runtime):
    config = runtime / "config/application-localtest.properties"
    if not config.is_file() or config.stat().st_mode & 0o077:
        raise RuntimeError("Missing private localtest configuration or unsafe permissions")
    values = dict(line.split("=", 1) for line in config.read_text().splitlines() if line and not line.startswith("#") and "=" in line)
    ports = load_ports(runtime)
    expected = {"server.address": "127.0.0.1", "server.port": str(ports["backend"]),
                "server.servlet.context-path": "/api", "spring.redis.host": "127.0.0.1",
                "spring.redis.port": str(ports["redis"]), "spring.quartz.auto-startup": "false",
                "justauth.enabled": "false", "jeecg.path.upload": str(runtime / "uploads")}
    if any(values.get(key) != value for key, value in expected.items()):
        raise RuntimeError("App configuration escaped this local synthetic runtime")
    if not values.get("spring.datasource.dynamic.datasource.master.url", "").startswith("jdbc:mysql://127.0.0.1:" + str(ports["mysql"]) + "/teachingopen_dev?"):
        raise RuntimeError("App database URL escaped this local synthetic runtime")
