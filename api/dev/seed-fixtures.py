#!/usr/bin/env python3
"""Seed synthetic accounts/classes in the task-owned, empty local test database."""
import argparse
import json
from pathlib import Path
import secrets
import subprocess
from local_runtime import assert_database


def quote(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def seed(runtime, java_home):
    api = Path(__file__).resolve().parents[1]
    mysql = runtime / "tools/mysql-8.4.6-macos15-arm64/bin/mysql"
    command = [str(mysql), "--defaults-extra-file=" + str(runtime / "config/mysql-admin-client.cnf"), "--batch", "--skip-column-names"]
    def query(sql):
        return subprocess.check_output(command + ["-e", sql], text=True).strip()
    # Refuse a different server or existing account data before any inserts.
    assert_database(runtime, empty=True)
    credentials = json.loads((runtime / "config/credentials.json").read_text())
    classes = runtime / "fixture-classes"
    classes.mkdir(exist_ok=True)
    classpath = api / "jeecg-boot-base-common/target/classes"
    subprocess.run([str(java_home / "bin/javac"), "-cp", str(classpath), "-d", str(classes), str(api / "dev/FixturePassword.java")], check=True)
    statements = [(api / "db/phone-profile-registration.sql").read_text(), "START TRANSACTION;"]
    def insert(table, **fields):
        statements.append("INSERT INTO `" + table + "` (" + ",".join("`" + k + "`" for k in fields) + ") VALUES (" + ",".join(quote(v) for v in fields.values()) + ");")
    insert("sys_config", id="fixture_allow_registration", config_key="allowReg", config_value="1", config_enabled=1, comment="仅本地合成验收开放注册")
    for role in ("admin", "teacher", "student"):
        insert("sys_role", id="fixture_role_" + role, role_code=role, role_name="测试" + role)
    insert("sys_depart", id="fixture_school", parent_id="", depart_name="合成测试学校", org_code="A99", org_category="1", org_type="1", status="1", del_flag="0")
    for suffix in ("a", "b"):
        insert("sys_depart", id="fixture_class_" + suffix, parent_id="fixture_school", depart_name="合成测试班" + suffix, org_code="A99A0" + ("1" if suffix == "a" else "2"), org_category="2", org_type="2", status="1", del_flag="0")
    accounts = {}
    for role, suffix in (("admin", ""), ("teacher", "a"), ("teacher", "b"), ("student", "a"), ("student", "b")):
        name = "fixture_" + role + ("_" + suffix if suffix else "")
        salt = secrets.token_hex(4)
        hashed = subprocess.check_output([str(java_home / "bin/java"), "-cp", str(classes) + ":" + str(classpath), "FixturePassword"], input=name + "\n" + credentials["test_user_password"] + "\n" + salt + "\n", text=True)
        depart = "fixture_class_" + suffix if suffix else "fixture_school"
        insert("sys_user", id=name, username=name, realname="合成测试" + role + suffix, password=hashed, salt=salt, status=1, del_flag=0, user_identity=2 if role != "student" else 1, depart_ids=depart if role != "student" else "")
        insert("sys_user_role", id="role_" + name, user_id=name, role_id="fixture_role_" + role)
        insert("sys_user_depart", ID="dept_" + name, user_id=name, dep_id=depart)
        accounts[name] = {"id": name, "role": role, "class_id": depart}
    for suffix in ("a", "b"):
        insert("teaching_course", id="fixture_course_" + suffix, course_name="合成测试课程" + suffix, course_desc="仅用于本地验收", show_home=1, is_shared=0, depart_ids="fixture_school", course_type="1", course_category="1")
        insert("teaching_course_dept", id="fixture_assignment_" + suffix, dept_id="fixture_class_" + suffix, course_id="fixture_course_" + suffix, open_time="2026-01-01 00:00:00")
        insert("teaching_course_unit", id="fixture_unit_" + suffix, course_id="fixture_course_" + suffix, unit_name="合成单元" + suffix, unit_intro="仅用于本地验收", course_video="[]", course_work_type=1, course_work="合成作业题目" + suffix, course_plan="仅教师可见的教案" + suffix, show_course_plan=0)
        filename = "fixture-work-" + suffix + ".txt"
        (runtime / "uploads" / filename).write_text("synthetic work " + suffix + "\n")
        insert("sys_file", id="fixture_file_" + suffix, file_name=filename, file_path=filename, file_location=1, file_type=0, create_by="fixture_student_" + suffix)
        insert("teaching_additional_work", id="fixture_additional_" + suffix, work_name="合成附加作业" + suffix, work_dept="fixture_class_" + suffix, status=1, code_type=0)
        insert("teaching_work", id="fixture_work_" + suffix, user_id="fixture_student_" + suffix, depart_id="fixture_class_" + suffix, course_id="fixture_unit_" + suffix, work_name="合成作业" + suffix, work_type="1", work_file="fixture_file_" + suffix, create_by="fixture_student_" + suffix, create_time="2026-10-02 20:00:00", work_scene="course")
    statements.append("COMMIT;")
    sql = runtime / "config/fixture-seed.sql"
    sql.write_text("\n".join(statements) + "\n"); sql.chmod(0o600)
    with sql.open() as f:
        subprocess.run(command + ["teachingopen_dev"], stdin=f, check=True)
    (runtime / "fixture-accounts.json").write_text(json.dumps(accounts, ensure_ascii=False, indent=2) + "\n")
    print("Seeded 5 synthetic accounts, 2 classes, 2 courses and 2 works; no upstream INSERT data imported")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--java-home", type=Path, required=True)
    args = parser.parse_args()
    seed(args.runtime.resolve(), args.java_home.resolve())
