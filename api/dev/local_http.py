"""Actual HTTP/login client, restricted to a running synthetic local candidate."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from local_runtime import assert_app_config, assert_database, load_ports


class FixtureApi:
    def __init__(self, runtime, jar=None):
        self.runtime = runtime.resolve()
        assert_app_config(self.runtime)
        assert_database(self.runtime)
        self.ports = load_ports(self.runtime)
        jar = (jar or Path(__file__).resolve().parents[1] / "jeecg-boot-module-system/target/teaching-open-2.8.0.jar").resolve()
        process = json.loads((self.runtime / "backend-process.json").read_text())
        command = subprocess.check_output(["ps", "-p", str(process["pid"]), "-o", "command="], text=True)
        self.jar_sha256 = hashlib.sha256(jar.read_bytes()).hexdigest()
        if process["jar_path"] != str(jar) or process["jar_sha256"] != self.jar_sha256 or str(jar) not in command or "--spring.profiles.active=dev,localtest" not in command:
            raise RuntimeError("Running app is not the specified local candidate")
        self.credentials = json.loads((self.runtime / "config/credentials.json").read_text())
        self.redis = [str(self.runtime / "tools/redis-7.2.9/src/redis-cli"), "-h", "127.0.0.1", "-p", str(self.ports["redis"]), "--raw"]
        self.redis_env = dict(os.environ, REDISCLI_AUTH=self.credentials["redis_password"])
        if self.cache("CONFIG", "GET", "dir").splitlines() != ["dir", str(self.runtime / "redis-data")]:
            raise RuntimeError("Redis does not belong to this local runtime")
        self.tokens = {}

    def cache(self, *args):
        return subprocess.check_output(self.redis + ["-n", "1"] + list(args), env=self.redis_env, text=True).strip()

    def request(self, method, path, actor=None, data=None, token=None):
        headers = {"Content-Type": "application/json"}
        credential = self.tokens[actor] if actor else token
        if credential is not None:
            headers["X-Access-Token"] = credential
        req = Request("http://127.0.0.1:" + str(self.ports["backend"]) + "/api" + path,
                      data=json.dumps(data).encode() if data is not None else None,
                      headers=headers, method=method)
        try:
            response = urlopen(req, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            content_type = response.headers.get("Content-Type", "")
            raw = response.read()
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = None
            return response.status, payload, content_type

    def login(self, actor):
        if actor not in {"admin", "teacher_a", "teacher_b", "student_a", "student_b"}:
            raise ValueError("Only synthetic fixture accounts are supported")
        nonce = "localtest-" + secrets.token_hex(8)
        status, image, _ = self.request("GET", "/sys/randomImage/" + nonce)
        if status != 200 or not image or not image.get("success"):
            raise RuntimeError("Actual CAPTCHA generation failed")
        code = None
        for key in self.cache("KEYS", "*").splitlines():
            if re.fullmatch("[a-fA-F0-9]{32}", key):
                try:
                    value = json.loads(self.cache("GET", key))
                except ValueError:
                    continue
                if isinstance(value, str) and hashlib.md5((value + nonce).encode()).hexdigest().lower() == key.lower():
                    code = value
                    break
        if code is None:
            raise RuntimeError("CAPTCHA missing from task-owned Redis")
        status, result, _ = self.request("POST", "/sys/login", data={"username": "fixture_" + actor, "password": self.credentials["test_user_password"], "captcha": code, "checkKey": nonce})
        if status != 200 or not result or not result.get("success"):
            raise RuntimeError("Synthetic account login failed")
        self.tokens[actor] = result["result"]["token"]

    def close(self):
        for actor in list(self.tokens):
            self.request("GET", "/sys/logout", actor)
        self.tokens.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, value, traceback):
        self.close()
