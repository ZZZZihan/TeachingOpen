#!/usr/bin/env python3
"""Verify course-management role boundaries with a task-owned synthetic runtime."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from local_http import FixtureApi
from local_runtime import mysql_command


PREFIX = "fixture_roleprobe_"
TABLES = ("teaching_course", "teaching_course_unit", "teaching_course_dept", "sys_file")
RESOURCES = (
    ("course", "teachingCourse", "teaching_course", "courseName"),
    ("unit", "teachingCourseUnit", "teaching_course_unit", "unitName"),
    ("assignment", "teachingCourseDept", "teaching_course_dept", "deptId"),
)


def verify(args):
    results = []
    runtime = args.runtime.resolve()
    with FixtureApi(runtime, args.jar) as api:
        def sql(query):
            return subprocess.check_output(mysql_command(runtime) + ["teachingopen_dev", "-e", query], text=True).strip()

        def snapshot():
            return {table: hashlib.sha256(sql("SELECT * FROM " + table + " ORDER BY id").encode()).hexdigest() for table in TABLES}

        def check(name, passed, **details):
            results.append({"case": name, "passed": bool(passed), **details})
            print(("PASS " if passed else "FAIL ") + name, flush=True)

        def empty_import(path, actor):
            boundary = "teaching-role-check-boundary"
            headers = {"Content-Type": "multipart/form-data; boundary=" + boundary}
            if actor:
                headers["X-Access-Token"] = api.tokens[actor]
            request = Request("http://127.0.0.1:" + str(api.ports["backend"]) + "/api" + path,
                              data=("--" + boundary + "--\r\n").encode(), headers=headers, method="POST")
            try:
                response = urlopen(request, timeout=15)
            except HTTPError as error:
                response = error
            with response:
                raw = response.read()
                try:
                    payload = json.loads(raw)
                except ValueError:
                    payload = None
                return response.status, payload, response.headers.get("Content-Type", "")

        def call(method, path, actor=None, data=None):
            if path.endswith("/importExcel"):
                return empty_import(path, actor)
            if path.endswith("/exportXls"):
                headers = {"X-Access-Token": api.tokens[actor]} if actor else {}
                request = Request("http://127.0.0.1:" + str(api.ports["backend"]) + "/api" + path, headers=headers)
                try:
                    response = urlopen(request, timeout=15)
                except HTTPError as error:
                    response = error
                with response:
                    raw = response.read()
                    try:
                        payload = json.loads(raw)
                    except ValueError:
                        payload = {"xls_ole2": raw[:8] == bytes.fromhex("D0CF11E0A1B11AE1") and len(raw) > 512}
                    return response.status, payload, response.headers.get("Content-Type", "")
            return api.request(method, path, actor, data)

        def allowed(name, method, path, data=None, actor="admin"):
            status, payload, content_type = call(method, path, actor, data)
            if path.endswith("/exportXls"):
                passed = status == 200 and payload and payload.get("xls_ole2") is True
            elif path.endswith("/importExcel"):
                # Empty multipart deliberately checks the role gate and existing validation,
                # not workbook parsing or a successful import.
                passed = status == 200 and payload and payload.get("success") is False and payload.get("message") == "文件导入失败！"
            else:
                passed = status == 200 and payload and payload.get("success") is True
            check(name, passed, http_status=status, code=payload.get("code") if payload else None)
            return payload

        def refresh_fixture_role():
            # Direct SQL role changes bypass the application role editor. Evict only
            # this synthetic principal in the owned Redis instance. Existing Shiro
            # defaults to DB 0 while this runtime's Spring Redis uses DB 1; logout
            # alone does not currently clear that mismatch (tracked separately).
            if "admin" in api.tokens:
                api.request("GET", "/sys/logout", "admin")
                key = "shiro:cache:org.jeecg.modules.shiro.authc.ShiroRealm.authorizationCache:fixture_admin"
                for database in ("0", "1"):
                    subprocess.check_output(api.redis + ["-n", database, "DEL", key], env=api.redis_env, text=True)
                api.login("admin")

        original = snapshot()
        role_original = sql("SELECT role_id FROM sys_user_role WHERE id='role_fixture_admin'")
        if role_original != "fixture_role_admin" or sql("SELECT COUNT(*) FROM sys_role WHERE id='fixture_roleprobe_dev'") != "0":
            raise RuntimeError("Unexpected synthetic admin role state")
        for table in TABLES:
            if sql("SELECT COUNT(*) FROM " + table + " WHERE id LIKE '" + PREFIX + "%'") != "0":
                raise RuntimeError("Existing probe data; refusing to overwrite")
        file = runtime / "uploads/fixture-role-probe.txt"
        if file.exists():
            raise RuntimeError("Existing probe attachment; refusing to overwrite")
        preserved_files = {str(p.relative_to(runtime / "uploads")): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in (runtime / "uploads").rglob("*") if p.is_file()}
        try:
            for actor in ("admin", "student_a", "teacher_a"):
                api.login(actor)
            # Only fresh probe resources are ever targeted by mutating requests.
            file.write_bytes(b"synthetic permission probe\n")
            sql("INSERT INTO sys_file (id,file_name,file_path,file_location) VALUES ('" + PREFIX + "file','fixture-role-probe.txt','fixture-role-probe.txt',1)")
            sql("INSERT INTO teaching_course (id,course_name,course_cover) VALUES ('" + PREFIX + "course','permission probe','fixture-role-probe.txt')")
            sql("INSERT INTO teaching_course_unit (id,course_id,unit_name,course_plan) VALUES ('" + PREFIX + "unit','" + PREFIX + "course','permission probe','fixture-role-probe.txt')")
            sql("INSERT INTO teaching_course_dept (id,course_id,dept_id) VALUES ('" + PREFIX + "assignment','" + PREFIX + "course','fixture_class_b')")
            if args.expect_legacy:
                allowed("legacy student can create a course", "POST", "/teaching/teachingCourse/add", {"id": PREFIX + "newcourse", "courseName": "student mutation"}, "student_a")
                check("legacy student course write persisted", sql("SELECT course_name FROM teaching_course WHERE id='" + PREFIX + "newcourse'") == "student mutation")
                allowed("legacy teacher can edit unit batch", "PUT", "/teaching/teachingCourseUnit/editBatch", [{"id": PREFIX + "unit", "unitName": "teacher mutation"}], "teacher_a")
                check("legacy teacher unit write persisted", sql("SELECT unit_name FROM teaching_course_unit WHERE id='" + PREFIX + "unit'") == "teacher mutation")
                allowed("legacy student can change assignment", "PUT", "/teaching/teachingCourseDept/edit", {"id": PREFIX + "assignment", "deptId": "fixture_class_a"}, "student_a")
                check("legacy student assignment write persisted", sql("SELECT dept_id FROM teaching_course_dept WHERE id='" + PREFIX + "assignment'") == "fixture_class_a")
            else:
                protected = []
                for kind, controller, table, name in RESOURCES:
                    base = "/teaching/" + controller
                    resource_id = PREFIX + kind
                    body = {"id": resource_id, name: "blocked mutation", "courseId": PREFIX + "course"}
                    protected.extend([
                        ("GET", base + "/list", None),
                        ("GET", base + "/queryById?id=" + resource_id, None),
                        ("POST", base + "/add", {**body, "id": PREFIX + "denied_" + kind}),
                        ("PUT", base + "/edit", body),
                        ("DELETE", base + "/delete?id=" + resource_id, None),
                        ("DELETE", base + "/deleteBatch?ids=" + resource_id, None),
                        ("GET", base + "/exportXls", None),
                        ("POST", base + "/importExcel", None),
                    ])
                    if kind == "unit":
                        protected.append(("PUT", base + "/editBatch", [body]))
                    if kind == "assignment":
                        protected.append(("POST", base + "/addOrUpdate", {"deptId": "fixture_class_a", "courseIdList": [PREFIX + "course"]}))
                denial_before = snapshot()
                for actor in (None, "student_a", "teacher_a"):
                    for method, path, data in protected:
                        status, payload, _ = call(method, path, actor, data)
                        passed = status == 401 and payload and payload.get("code") == 401 if actor is None else status == 200 and payload and payload.get("success") is False and payload.get("code") == 510
                        check((actor or "anonymous") + " denied " + method + " " + path.split("?")[0], passed, http_status=status, code=payload.get("code") if payload else None)
                    check((actor or "anonymous") + " denied requests preserve every course/unit/assignment/file row", snapshot() == denial_before)
                    check((actor or "anonymous") + " denied deletes preserve attachment bytes", file.exists() and file.read_bytes() == b"synthetic permission probe\n")
                for actor in (None, "student_a", "teacher_a"):
                    allowed((actor or "anonymous") + " public courses still readable", "GET", "/teaching/teachingCourse/getHomeCourse", actor=actor)
                for actor in ("student_a", "teacher_a"):
                    allowed(actor + " assigned course entry remains available", "GET", "/teaching/teachingCourse/mineCourse", actor=actor)
                    allowed(actor + " assigned learning units remain available", "GET", "/teaching/teachingCourseUnit/mineUnit?courseId=fixture_course_a", actor=actor)
                    allowed(actor + " assigned course detail remains available", "GET", "/teaching/teachingCourse/queryById?id=fixture_course_a", actor=actor)
                    status, payload, _ = api.request("GET", "/teaching/teachingCourse/queryById?id=fixture_course_b", actor)
                    check(actor + " other class course detail denied", status == 200 and payload and payload.get("code") == 510 and payload.get("success") is False)
                sql("UPDATE teaching_course SET is_shared=1 WHERE id='" + PREFIX + "course'")
                for actor in ("student_a", "teacher_a"):
                    allowed(actor + " shared course detail remains available", "GET", "/teaching/teachingCourse/queryById?id=" + PREFIX + "course", actor=actor)
                sql("UPDATE teaching_course SET is_shared=0 WHERE id='" + PREFIX + "course'")
                for role in ("admin", "dev"):
                    if role == "dev":
                        sql("UPDATE sys_user_role SET role_id='fixture_role_teacher' WHERE id='role_fixture_admin'")
                        refresh_fixture_role()
                        status, payload, _ = api.request("GET", "/teaching/teachingCourse/list", "admin")
                        check("former admin with only teacher role denied after fixture cache eviction and fresh login", status == 200 and payload and payload.get("success") is False and payload.get("code") == 510)
                        sql("INSERT INTO sys_role (id,role_code,role_name) VALUES ('fixture_roleprobe_dev','dev','synthetic dev'); UPDATE sys_user_role SET role_id='fixture_roleprobe_dev' WHERE id='role_fixture_admin'")
                        refresh_fixture_role()
                        check("dev exercise uses only dev role", sql("SELECT r.role_code FROM sys_user_role ur JOIN sys_role r ON r.id=ur.role_id WHERE ur.user_id='fixture_admin'") == "dev")
                    for kind, controller, table, name in RESOURCES:
                        base = "/teaching/" + controller
                        resource_id = PREFIX + role + "_" + kind
                        body = {"id": resource_id, name: "fixture_class_a" if kind == "assignment" else "admin probe", "courseId": PREFIX + "course"}
                        allowed(role + " creates " + kind, "POST", base + "/add", body)
                        check(role + " " + kind + " creation persisted", sql("SELECT COUNT(*) FROM " + table + " WHERE id='" + resource_id + "'") == "1")
                        allowed(role + " lists " + kind, "GET", base + "/list")
                        allowed(role + " reads " + kind, "GET", base + "/queryById?id=" + resource_id)
                        value = "fixture_class_b" if kind == "assignment" else "updated probe"
                        allowed(role + " edits " + kind, "PUT", base + "/edit", {"id": resource_id, name: value})
                        column = {"courseName": "course_name", "unitName": "unit_name", "deptId": "dept_id"}[name]
                        check(role + " " + kind + " edit persisted", sql("SELECT " + column + " FROM " + table + " WHERE id='" + resource_id + "'") == value)
                        allowed(role + " exports " + kind, "GET", base + "/exportXls")
                        allowed(role + " empty import reaches existing validation " + kind, "POST", base + "/importExcel")
                        if kind == "unit":
                            allowed(role + " edits unit batch", "PUT", base + "/editBatch", [{"id": resource_id, "unitName": "batch update"}])
                            check(role + " unit batch persisted", sql("SELECT unit_name FROM teaching_course_unit WHERE id='" + resource_id + "'") == "batch update")
                        if kind == "assignment":
                            allowed(role + " assigns course to class", "POST", base + "/addOrUpdate", {"deptId": "fixture_class_a", "courseIdList": [PREFIX + "course"]})
                            check(role + " course assignment persisted", sql("SELECT COUNT(*) FROM teaching_course_dept WHERE course_id='" + PREFIX + "course' AND dept_id='fixture_class_a'") == "1")
                        allowed(role + " deletes " + kind, "DELETE", base + "/delete?id=" + resource_id)
                        check(role + " " + kind + " deletion persisted", sql("SELECT COUNT(*) FROM " + table + " WHERE id='" + resource_id + "'") == "0")
                        allowed(role + " recreates " + kind + " for batch delete", "POST", base + "/add", body)
                        allowed(role + " batch deletes " + kind, "DELETE", base + "/deleteBatch?ids=" + resource_id)
                        check(role + " " + kind + " batch deletion persisted", sql("SELECT COUNT(*) FROM " + table + " WHERE id='" + resource_id + "'") == "0")
            jar_hash = api.jar_sha256
        finally:
            sql("DELETE FROM teaching_course_dept WHERE course_id LIKE '" + PREFIX + "%'")
            for table in TABLES:
                sql("DELETE FROM " + table + " WHERE id LIKE '" + PREFIX + "%'")
            sql("UPDATE sys_user_role SET role_id='fixture_role_admin' WHERE id='role_fixture_admin'; DELETE FROM sys_role WHERE id='fixture_roleprobe_dev'")
            refresh_fixture_role()
            file.unlink(missing_ok=True)
        check("all original course/unit/assignment/file rows restored", snapshot() == original)
        check("synthetic admin role restored and temporary dev role removed", sql("SELECT role_id FROM sys_user_role WHERE id='role_fixture_admin'") == role_original and sql("SELECT COUNT(*) FROM sys_role WHERE id='fixture_roleprobe_dev'") == "0")
        after_files = {str(p.relative_to(runtime / "uploads")): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (runtime / "uploads").rglob("*") if p.is_file()}
        check("all original attachment bytes preserved and probe removed", after_files == preserved_files)
    report = {"observed_utc": datetime.now(timezone.utc).isoformat(), "jar_sha256": jar_hash,
              "base_url": "http://127.0.0.1:" + str(api.ports["backend"]) + "/api", "expected_legacy": args.expect_legacy,
              "scope": "real HTTP login, role gates, database and attachments; import role gate only, not workbook import; no full role UI acceptance",
              "captcha_method": "real HTTP generation; read only task-owned synthetic Redis", "protected_routes": 26, "administrator_only_routes": 25,
              "passed": sum(case["passed"] for case in results), "total": len(results), "cases": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(str(report["passed"]) + "/" + str(report["total"]) + " checks passed; sanitized evidence: " + str(args.output))
    return report["passed"] == report["total"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--jar", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expect-legacy", action="store_true")
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
