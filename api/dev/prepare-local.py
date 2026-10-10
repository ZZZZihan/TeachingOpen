#!/usr/bin/env python3
"""Create a fresh, isolated macOS arm64 test runtime using verified portable tools."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
from xml.sax.saxutils import escape
from local_runtime import DEFAULT_PORTS, validate_ports


def private_file(path, content):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
        file.write(content)


def prepare(runtime, tools, ports, seed_fixtures=True):
    api = Path(__file__).resolve().parents[1]
    if runtime.parent.name != ".devspace" or runtime.exists():
        raise RuntimeError("Use a new direct child of .devspace; existing data is never overwritten")
    validate_ports(ports)
    for port in ports.values():
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))
    mysql_base = tools / "mysql-8.4.6-macos15-arm64"
    mysql = mysql_base / "bin/mysql"
    mysqld = mysql_base / "bin/mysqld"
    redis = tools / "redis-7.2.9/src/redis-server"
    java_home = tools / "zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home"
    for executable in (mysql, mysqld, redis, java_home / "bin/java", tools / "apache-maven-3.9.16/bin/mvn"):
        if not executable.is_file():
            raise RuntimeError("Missing verified portable tool: " + str(executable))
    runtime.mkdir(mode=0o700, parents=True)
    private_file(runtime / "ports.json", json.dumps(ports, indent=2) + "\n")
    (runtime / "tools").symlink_to(tools, target_is_directory=True)
    for directory in ("config", "logs", "mysql-data", "redis-data", "uploads", "webapp", "m2"):
        (runtime / directory).mkdir(mode=0o700)
    credentials = {key: secrets.token_hex(20) for key in ("mysql_root_password", "mysql_app_password", "redis_password", "test_user_password")}
    private_file(runtime / "config/credentials.json", json.dumps(credentials, indent=2) + "\n")
    private_file(runtime / "config/mysql.cnf", f"[mysqld]\nbasedir={mysql_base}\ndatadir={runtime}/mysql-data\nport={ports['mysql']}\nbind-address=127.0.0.1\nsocket={runtime}/mysql.sock\npid-file={runtime}/mysql.pid\nlog-error={runtime}/logs/mysql-server.log\nmysqlx=OFF\nlower-case-table-names=2\nevent-scheduler=OFF\n")
    client = f"[client]\nuser=root\nhost=127.0.0.1\nport={ports['mysql']}\nprotocol=tcp\n"
    private_file(runtime / "config/mysql-initial-client.cnf", client)
    private_file(runtime / "config/mysql-admin-client.cnf", client + "password=" + credentials["mysql_root_password"] + "\n")
    private_file(runtime / "config/redis.conf", f"bind 127.0.0.1\nport {ports['redis']}\nprotected-mode yes\nrequirepass {credentials['redis_password']}\ndir {runtime}/redis-data\npidfile {runtime}/redis.pid\nlogfile {runtime}/logs/redis-server.log\ndaemonize yes\nappendonly no\nsave \"\"\n")
    template = (api / "dev/application-localtest.properties.template").read_text()
    values = {"RUNTIME": str(runtime), "MYSQL_APP_PASSWORD": credentials["mysql_app_password"], "REDIS_PASSWORD": credentials["redis_password"]}
    values.update({key.upper() + "_PORT": str(value) for key, value in ports.items()})
    for name, value in values.items():
        template = template.replace("@" + name + "@", value)
    private_file(runtime / "config/application-localtest.properties", template)
    private_file(runtime / "settings.xml", '<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"><localRepository>' + escape(str(runtime / "m2")) + '</localRepository><mirrors><mirror><id>central-https</id><mirrorOf>*,!jeecg,!jeecg-snapshots</mirrorOf><url>https://repo.maven.apache.org/maven2</url></mirror></mirrors></settings>\n')
    log = runtime / "logs/initialize.log"
    private_file(log, "")
    with log.open("a") as out:
        subprocess.run([str(mysqld), "--no-defaults", "--initialize-insecure", "--basedir=" + str(mysql_base), "--datadir=" + str(runtime / "mysql-data"), "--lower-case-table-names=2"], stdout=out, stderr=subprocess.STDOUT, check=True)
        subprocess.run([str(mysqld), "--defaults-file=" + str(runtime / "config/mysql.cnf"), "--daemonize"], stdout=out, stderr=subprocess.STDOUT, check=True)
    initial = [str(mysql), "--defaults-extra-file=" + str(runtime / "config/mysql-initial-client.cnf")]
    for attempt in range(30):
        if subprocess.run(initial + ["-e", "SELECT 1"], capture_output=True).returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Isolated MySQL did not become ready; inspect private initialization log")
    init_sql = "CREATE DATABASE teachingopen_dev CHARACTER SET utf8mb4;\nCREATE USER 'teaching_dev'@'127.0.0.1' IDENTIFIED BY '" + credentials["mysql_app_password"] + "';\nGRANT ALL PRIVILEGES ON teachingopen_dev.* TO 'teaching_dev'@'127.0.0.1';\nALTER USER 'root'@'localhost' IDENTIFIED BY '" + credentials["mysql_root_password"] + "';\n"
    private_file(runtime / "config/database-init.sql", init_sql)
    subprocess.run(initial, input=init_sql, text=True, check=True)
    subprocess.run([str(redis), str(runtime / "config/redis.conf")], check=True)
    spec = importlib.util.spec_from_file_location("extract_schema", api / "dev/extract-schema.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    schema = module.extract_schema((api / "db/teachingopen2.8.sql").read_text())
    private_file(runtime / "schema-only.sql", schema)
    with (runtime / "schema-only.sql").open() as file:
        subprocess.run([str(mysql), "--defaults-extra-file=" + str(runtime / "config/mysql-admin-client.cnf"), "teachingopen_dev"], stdin=file, check=True)
    if seed_fixtures:
        subprocess.run(["python3", str(api / "dev/seed-fixtures.py"), "--runtime", str(runtime), "--java-home", str(java_home)], check=True)
    print("Fresh isolated runtime ready:", runtime)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--tools", type=Path, required=True)
    for service, port in DEFAULT_PORTS.items():
        parser.add_argument("--" + service + "-port", type=int, default=port)
    args = parser.parse_args()
    prepare(args.runtime.resolve(), args.tools.resolve(), {name: getattr(args, name + "_port") for name in DEFAULT_PORTS})
