#!/usr/bin/env python3
"""Check learning-unit access and visibility on an owned synthetic runtime."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from local_http import FixtureApi
from local_runtime import mysql_command


PREFIX = "fixture_unitprobe_"
COURSE = PREFIX + "course"
FIELDS = {"courseVideo": "course_video", "courseCase": "course_case",
          "coursePpt": "course_ppt", "coursePlan": "course_plan"}
VALUES = {field: "unit-probe-" + column + ".txt" for field, column in FIELDS.items()}
PATTERNS = {"hidden": (0, 0, 0, 0), "visible": (1, 1, 1, 1),
            "video": (1, 0, 0, 0), "case": (0, 1, 0, 0),
            "ppt": (0, 0, 1, 0), "plan": (0, 0, 0, 1), "unset": (None,) * 4}
TABLES = ("teaching_course", "teaching_course_unit", "teaching_course_dept", "teaching_work", "sys_file")
BASE = "/teaching/teachingCourseUnit/"


def verify(args):
    cases = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(query):
            return subprocess.check_output(mysql_command(api.runtime) + ["teachingopen_dev", "-e", query], text=True).strip()

        def snapshot():
            return {table: hashlib.sha256(sql("SELECT * FROM " + table + " ORDER BY id").encode()).hexdigest() for table in TABLES}

        def files():
            return {str(p.relative_to(api.runtime / "uploads")): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (api.runtime / "uploads").rglob("*") if p.is_file()}

        def check(name, passed, **details):
            cases.append({"case": name, "passed": bool(passed), **details})
            print(("PASS " if passed else "FAIL ") + name, flush=True)

        def call(kind, actor, suffix="hidden", course=COURSE):
            path = "mineUnit?courseId=" + course + "&pageSize=20" if kind == "list" else "getUnitWorkInfo?unitId=" + PREFIX + suffix
            status, body, _ = api.request("GET", BASE + path, actor)
            return status, body

        def ok(status, body):
            return status == 200 and body and body.get("success") is True

        def units(kind, body):
            if not body or not body.get("success"):
                return {}
            result = body.get("result") or {}
            records = result.get("records", []) if kind == "list" else [result]
            return {unit["id"]: unit for unit in records}

        def visibility(unit, flags, student):
            if not unit:
                return False
            for (field, value), flag in zip(VALUES.items(), flags):
                if student and flag != 1:
                    # The FileUrl aspect must not reintroduce a generated URL.
                    if unit.get(field) or unit.get(field + "_url") or value in json.dumps(unit):
                        return False
                elif value not in (unit.get(field) or ""):
                    return False
            return (unit.get("courseWork") == "unit-probe-template.sb3"
                    and "unit-probe-template.sb3" in (unit.get("courseWork_url") or "")
                    and unit.get("courseWorkType") == 2
                    and unit.get("unitIntro") == "visible introduction"
                    and unit.get("mediaContent") == "<p>visible lesson</p>")

        original, original_files = snapshot(), files()
        original_role = sql("SELECT role_id FROM sys_user_role WHERE id='role_fixture_admin'")
        original_identity = sql("SELECT user_identity FROM sys_user WHERE id='fixture_student_a'")
        if original_role != "fixture_role_admin" or original_identity != "1":
            raise RuntimeError("Unexpected synthetic account state; refusing to overwrite")
        for table in TABLES + ("sys_role",):
            if sql("SELECT COUNT(*) FROM " + table + " WHERE id LIKE '" + PREFIX + "%'") != "0":
                raise RuntimeError("Existing probe rows; refusing to overwrite")
        try:
            for actor in ("admin", "student_a", "student_b", "teacher_a", "teacher_b"):
                api.login(actor)
            sql("INSERT INTO teaching_course (id,course_name,is_shared) VALUES ('" + COURSE + "','unit access probe',0)")
            sql("INSERT INTO teaching_course_dept (id,course_id,dept_id) VALUES ('" + PREFIX + "assignment','" + COURSE + "','fixture_class_a')")
            for name, flags in PATTERNS.items():
                # Legacy baseline initially excludes nullable flags so the hidden-data
                # counterexample can be observed independently of its list failure.
                if args.expect_legacy and name == "unset":
                    continue
                columns = ["id", "course_id", "unit_name", *FIELDS.values(),
                           *("show_" + c for c in FIELDS.values()), "course_work", "course_work_type", "unit_intro", "media_content"]
                values = ["'" + PREFIX + name + "'", "'" + COURSE + "'", "'" + name + "'",
                          *("'" + v + "'" for v in VALUES.values()),
                          *(str(flag) if flag is not None else "NULL" for flag in flags),
                          "'unit-probe-template.sb3'", "2", "'visible introduction'", "'<p>visible lesson</p>'"]
                sql("INSERT INTO teaching_course_unit (" + ",".join(columns) + ") VALUES (" + ",".join(values) + ")")

            if args.expect_legacy:
                for actor in ("student_b", "teacher_b"):
                    status, body = call("detail", actor)
                    check(actor + " can read unassigned private unit before fix", ok(status, body) and body["result"].get("courseId") == COURSE)
                status, body = call("detail", "student_a")
                check("student detail leaks all four hidden resources before fix", ok(status, body) and all(body["result"].get(k) == v for k, v in VALUES.items()))
                status, body = call("list", "student_a")
                check("student list already hides disabled resources", ok(status, body) and visibility(units("list", body).get(PREFIX + "hidden"), PATTERNS["hidden"], True))
                status, body = call("list", "admin")
                check("unassigned admin list denied before fix", status == 200 and body and body.get("success") is False)
                sql("UPDATE teaching_course_unit SET show_course_video=NULL WHERE id='" + PREFIX + "hidden'")
                status, body = call("list", "student_a")
                check("nullable display flag fails student list before fix", status == 200 and body and body.get("success") is False and body.get("code") == 500, http_status=status, code=body.get("code") if body else None)
            else:
                for kind in ("list", "detail"):
                    status, body = call(kind, None)
                    check("anonymous " + kind + " denied", status == 401 and body and body.get("code") == 401)
                    for actor in ("student_b", "teacher_b"):
                        status, body = call(kind, actor)
                        check(actor + " private " + kind + " denied without unit data", status == 200 and body and body.get("success") is False and body.get("code") == 510 and not body.get("result"))

                for identity in (1, None):
                    if identity is None:
                        sql("UPDATE sys_user SET user_identity=NULL WHERE id='fixture_student_a'")
                        api.request("GET", "/sys/logout", "student_a")
                        api.login("student_a")
                    for actor in (("student_a", "teacher_a", "admin") if identity == 1 else ("student_a",)):
                        identity_label = " identity=" + str(identity) if actor == "student_a" else " identity=2"
                        for kind in ("list", "detail"):
                            status, body = call(kind, actor)
                            records = units(kind, body)
                            if kind == "list":
                                check(actor + identity_label + " list has all probe units", ok(status, body) and len(records) == len(PATTERNS))
                            for name, flags in PATTERNS.items():
                                if kind == "detail":
                                    status, body = call(kind, actor, name)
                                    records = units(kind, body)
                                check(actor + identity_label + " " + kind + " " + name + " visibility and assignment template",
                                      ok(status, body) and visibility(records.get(PREFIX + name), flags, actor == "student_a"))

                # Existing editor contract: mineWorkId belongs to the logged-in user.
                for actor, unit_id, expected_work in (("student_a", "fixture_unit_a", "fixture_work_a"),
                                                      ("student_b", "fixture_unit_b", "fixture_work_b"),
                                                      ("teacher_a", "fixture_unit_a", None)):
                    status, body, _ = api.request("GET", BASE + "getUnitWorkInfo?unitId=" + unit_id, actor)
                    check(actor + " editor work link preserved", ok(status, body) and body["result"].get("mineWorkId") == expected_work)
                sql("UPDATE teaching_course SET is_shared=1 WHERE id='" + COURSE + "'")
                for actor in ("student_b", "teacher_b"):
                    for kind in ("list", "detail"):
                        status, body = call(kind, actor)
                        check(actor + " shared " + kind + " allowed with correct visibility", ok(status, body) and visibility(units(kind, body).get(PREFIX + "hidden"), PATTERNS["hidden"], actor == "student_b"))
                sql("UPDATE teaching_course SET is_shared=0 WHERE id='" + COURSE + "'")
                sql("INSERT INTO sys_role (id,role_code,role_name) VALUES ('" + PREFIX + "dev','dev','unit probe dev'); UPDATE sys_user_role SET role_id='" + PREFIX + "dev' WHERE id='role_fixture_admin'")
                api.request("GET", "/sys/logout", "admin")
                api.login("admin")
                for kind in ("list", "detail"):
                    status, body = call(kind, "admin")
                    check("dev-only role can read unassigned " + kind, ok(status, body) and visibility(units(kind, body).get(PREFIX + "hidden"), PATTERNS["hidden"], False))
                status, body = call("detail", "student_a", "nonexistent")
                check("missing unit returns existing not-found response", status == 200 and body and body.get("success") is False and body.get("message") == "未找到对应实体" and not body.get("result"))
                check("read requests preserve stored resource paths", sql("SELECT COUNT(*) FROM teaching_course_unit WHERE course_id='" + COURSE + "' AND course_video='" + VALUES["courseVideo"] + "' AND course_case='" + VALUES["courseCase"] + "' AND course_ppt='" + VALUES["coursePpt"] + "' AND course_plan='" + VALUES["coursePlan"] + "'") == str(len(PATTERNS)))
            jar_hash = api.jar_sha256
        finally:
            sql("DELETE FROM teaching_course_dept WHERE id LIKE '" + PREFIX + "%'; DELETE FROM teaching_course_unit WHERE id LIKE '" + PREFIX + "%'; DELETE FROM teaching_course WHERE id LIKE '" + PREFIX + "%'")
            sql("UPDATE sys_user_role SET role_id='fixture_role_admin' WHERE id='role_fixture_admin'; DELETE FROM sys_role WHERE id='" + PREFIX + "dev'; UPDATE sys_user SET user_identity=1 WHERE id='fixture_student_a'")
            for actor in ("admin", "student_a"):
                if actor in api.tokens:
                    api.request("GET", "/sys/logout", actor)
        check("all original business rows restored", snapshot() == original)
        check("original identity and role restored; probe role removed", sql("SELECT user_identity FROM sys_user WHERE id='fixture_student_a'") == original_identity and sql("SELECT role_id FROM sys_user_role WHERE id='role_fixture_admin'") == original_role and sql("SELECT COUNT(*) FROM sys_role WHERE id='" + PREFIX + "dev'") == "0")
        check("all original attachment bytes unchanged", files() == original_files)
    result = {"observed_utc": datetime.now(timezone.utc).isoformat(), "jar_sha256": jar_hash,
              "expected_legacy": args.expect_legacy,
              "scope": "real HTTP login and unit list/detail responses, synthetic DB fixtures and cleanup; not browser editors or direct attachment-download authorization",
              "passed": sum(case["passed"] for case in cases), "total": len(cases), "cases": cases}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(str(result["passed"]) + "/" + str(result["total"]) + " checks passed")
    return result["passed"] == result["total"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--jar", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expect-legacy", action="store_true")
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
