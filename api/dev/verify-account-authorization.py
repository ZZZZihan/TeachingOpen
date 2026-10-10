#!/usr/bin/env python3
"""Exercise administrative and profile boundaries on an owned synthetic runtime."""
import argparse
import base64
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import urlencode
from uuid import uuid4
from zipfile import ZipFile

from local_http import FixtureApi
from local_runtime import mysql_command


def legacy_authorization_payload(runtime, jar):
    """Create the legacy Redis value using the candidate's real Shiro serializer."""
    with TemporaryDirectory(prefix='teaching-legacy-auth-') as temporary:
        directory = Path(temporary)
        libraries = []
        with ZipFile(jar) as archive:
            for artifact in ('shiro-core', 'shiro-redis', 'slf4j-api'):
                matches = [name for name in archive.namelist()
                           if name.startswith('BOOT-INF/lib/' + artifact + '-') and name.endswith('.jar')]
                if len(matches) != 1:
                    raise RuntimeError('Candidate must contain one legacy Shiro dependency')
                library = directory / (artifact + '.jar')
                library.write_bytes(archive.read(matches[0]))
                libraries.append(str(library))
        javac_candidates = sorted((runtime / 'tools').glob('*jdk*/Contents/Home/bin/javac'))
        javac = str(javac_candidates[0]) if javac_candidates else shutil.which('javac')
        if not javac:
            raise RuntimeError('Java compiler required for canonical legacy authorization cache')
        java = str(Path(javac).parent / 'java')
        source = directory / 'LegacyAuthorization.java'
        source.write_text('''import java.util.*;
import org.apache.shiro.authz.SimpleAuthorizationInfo;
import org.crazycake.shiro.serializer.ObjectSerializer;
public class LegacyAuthorization {
    public static void main(String[] args) throws Exception {
        SimpleAuthorizationInfo info = new SimpleAuthorizationInfo(new HashSet<>(Arrays.asList("student", "admin", "dev")));
        info.addStringPermission("user:status");
        ObjectSerializer serializer = new ObjectSerializer();
        byte[] value = serializer.serialize(info);
        SimpleAuthorizationInfo restored = (SimpleAuthorizationInfo) serializer.deserialize(value);
        if (!restored.getRoles().contains("dev") || !restored.getStringPermissions().contains("user:status"))
            throw new IllegalStateException("Legacy authorization round trip failed");
        System.out.print(Base64.getEncoder().encodeToString(value));
    }
}
''')
        classpath = ':'.join(libraries)
        compiled = subprocess.run([javac, '-cp', classpath, str(source)], capture_output=True, timeout=30)
        if compiled.returncode:
            raise RuntimeError('Canonical legacy authorization helper compilation failed')
        serialized = subprocess.run([java, '-cp', str(directory) + ':' + classpath, 'LegacyAuthorization'],
                                    capture_output=True, timeout=20)
        if serialized.returncode:
            raise RuntimeError('Canonical legacy authorization serialization failed')
        value = base64.b64decode(serialized.stdout, validate=True)
        if not value.startswith(b'\xac\xed\x00\x05'):
            raise RuntimeError('Legacy authorization must use Java object serialization')
        return value


def verify(args):
    checks = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(statement):
            result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError('Synthetic account SQL failed')
            return result.stdout.strip()

        def literal(value):
            return '0x' + str(value).encode().hex()

        def check(name, passed):
            checks.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed:
                raise AssertionError(name)

        tables = ('sys_user', 'sys_user_role', 'sys_user_depart', 'sys_depart_role_user',
                  'sys_permission', 'sys_role_permission', 'sys_depart_role', 'sys_depart_role_permission',
                  'sys_role', 'sys_depart_permission', 'sys_depart', 'sys_permission_data_rule')

        def snapshot():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest()
                    for table in tables}

        def request(method, route, actor, body=None):
            return api.request(method, route, actor, body)

        def denied(name, method, route, actor, body=None):
            before = snapshot()
            status, result, _ = request(method, route, actor, body)
            check(name, status != 404 and (status >= 400 or result is not None and result.get('success') is False))
            check(name + ' changes no account or permission records', snapshot() == before)

        def allowed(name, method, route, actor, body=None):
            status, result, _ = request(method, route, actor, body)
            check(name, status == 200 and result is not None and result.get('success') is True)

        def authorization_denied(name, method, route, actor, body=None, stale_key=None, stale_hash=None):
            before = snapshot()
            status, result, _ = request(method, route, actor, body)
            check(name, status == 403 or result is not None and result.get('success') is False and result.get('code') == 510)
            check(name + ' changes no account, department, or permission records', snapshot() == before)
            if stale_key:
                observed = api.cache('EVAL', "return redis.sha1hex(redis.call('GET',KEYS[1]) or '')", '1', stale_key)
                check(name + ' leaves the old authorization cache intact', observed == stale_hash)

        def clear(actor):
            for key in ('sys:cache:user::fixture_' + actor, 'shiro:cache:org.jeecg.modules.shiro.authc.ShiroRealm.authorizationCache:fixture_' + actor):
                api.cache('DEL', key)

        # Exact state restoration is limited to the five synthetic accounts and roles.
        saved = {}
        for table in ('sys_user', 'sys_role'):
            columns = [line.split('\t')[0] for line in sql('SHOW COLUMNS FROM ' + table).splitlines()]
            rows = sql('SELECT ' + ','.join("IFNULL(HEX(CAST(`" + c + "` AS BINARY)),'NULL')" for c in columns)
                       + ' FROM ' + table + " WHERE id LIKE 'fixture_%' ORDER BY id").splitlines()
            saved[table] = (columns, rows)
        prefix = 'account_auth_' + uuid4().hex[:10]
        probe_a, probe_b = prefix + '_a', prefix + '_b'
        permission_id, permission_link = prefix + '_p', prefix + '_rp'
        old_admin_grant, old_dev_grant = prefix + '_oa', prefix + '_od'
        trigger = prefix + '_reject'
        original = snapshot()
        sql("UPDATE sys_role SET role_level=CASE role_code WHEN 'admin' THEN 9 WHEN 'teacher' THEN 5 ELSE 1 END WHERE id LIKE 'fixture_role_%'")
        try:
            for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b'):
                api.login(actor)
            role_body = {'roleId': 'fixture_role_admin', 'userIdList': ['fixture_student_a']}
            for actor in ('student_a', 'teacher_a'):
                denied(actor + ' cannot self-grant admin', 'POST', '/sys/user/addSysUserRole', actor, role_body)
                denied(actor + ' cannot reset another password', 'PUT', '/sys/user/changePassword', actor,
                       {'id': 'fixture_student_b', 'username': 'fixture_student_b', 'password': 'SecurePassword9!'})
                denied(actor + ' cannot add account', 'POST', '/sys/user/add', actor,
                       {'username': prefix, 'realname': 'probe', 'password': 'SecurePassword9!', 'selectedroles': 'fixture_role_admin'})
                denied(actor + ' cannot edit account roles', 'PUT', '/sys/user/edit', actor,
                       {'id': 'fixture_student_a', 'selectedroles': 'fixture_role_admin'})
                for route in ('/sys/user/importExcel', '/sys/user/importStudent'):
                    denied(actor + ' cannot import accounts ' + route, 'POST', route, actor, {})
                for route in ('/sys/permission/add', '/sys/permission/saveRolePermission', '/sys/sysDepartRole/add'):
                    denied(actor + ' permission graph blocked ' + route, 'POST', route, actor, {})
                for method, route, body in (
                    ('POST', '/sys/sysDepart/add', {'id': prefix + '_d', 'departName': '合成班级'}),
                    ('PUT', '/sys/sysDepart/edit', {'id': 'fixture_class_a', 'departName': 'forged'}),
                    ('DELETE', '/sys/sysDepart/delete?id=fixture_class_a', None),
                    ('DELETE', '/sys/sysDepart/deleteBatch?ids=fixture_class_a', None),
                    ('POST', '/sys/sysDepart/importExcel', {}),
                    ('GET', '/sys/sysDepart/removeAll?id=fixture_class_a', None)):
                    authorization_denied(actor + ' department management blocked ' + route, method, route, actor, body)
                for method, route, body in (
                    ('POST', '/sys/sysDepartPermission/add', {}),
                    ('PUT', '/sys/sysDepartPermission/edit', {}),
                    ('DELETE', '/sys/sysDepartPermission/delete?id=missing', None),
                    ('DELETE', '/sys/sysDepartPermission/deleteBatch?ids=missing', None),
                    ('POST', '/sys/sysDepartPermission/importExcel', {}),
                    ('POST', '/sys/sysDepartPermission/datarule', {}),
                    ('POST', '/sys/sysDepartPermission/saveDeptRolePermission', {})):
                    denied(actor + ' department authorization blocked ' + route, method, route, actor, body)
                denied(actor + ' cannot restore recycle bin', 'PUT', '/sys/user/putRecycleBin', actor,
                       {'userIds': 'fixture_student_b'})
                denied(actor + ' cannot purge accounts', 'DELETE', '/sys/user/deleteRecycleBin?userIds=fixture_student_b', actor)
            for actor in ('student_a', 'teacher_a', 'admin'):
                for method, route, body in (
                    ('POST', '/sys/role/add', {'roleCode': 'dev', 'roleLevel': 999}),
                    ('PUT', '/sys/role/edit', {'id': 'fixture_role_admin', 'roleLevel': 999}),
                    ('PUT', '/sys/role/edit', {'id': 'fixture_role_student', 'roleCode': 'dev'}),
                    ('DELETE', '/sys/role/delete?id=fixture_role_admin', None),
                    ('DELETE', '/sys/role/deleteBatch?ids=fixture_role_student', None),
                    ('POST', '/sys/role/importExcel', {})):
                    denied(actor + ' cannot redefine role identity ' + route, method, route, actor, body)
            for route in ('/sys/user/appEdit', '/teaching/user/edit'):
                denied('profile alias rejects other ID ' + route, 'PUT', route, 'student_a',
                       {'id': 'fixture_student_b', 'realname': 'forged'})
                for key, value in (('password', 'forged'), ('salt', 'salt'), ('status', 0), ('delFlag', 1),
                                   ('departIds', 'fixture_school'), ('phone', '13912345678'), ('userIdentity', 2)):
                    denied('profile rejects ' + key + ' ' + route, 'PUT', route, 'student_a',
                           {'id': 'fixture_student_a', 'realname': 'probe', key: value})
            denied('self-password API cannot target a different username', 'PUT', '/sys/user/updatePassword', 'student_a',
                   {'username': 'fixture_student_b', 'oldpassword': api.credentials['test_user_password'],
                    'password': 'SecurePassword9!', 'confirmpassword': 'SecurePassword9!'})
            denied('role batch validates all target IDs', 'POST', '/sys/user/addSysUserRole', 'admin',
                   {'roleId': 'fixture_role_teacher', 'userIdList': ['fixture_student_a', prefix + '_missing']})
            denied('case aliases are not accepted as exact target IDs', 'POST', '/sys/user/addSysUserRole', 'admin',
                   {'roleId': 'fixture_role_teacher', 'userIdList': ['FIXTURE_STUDENT_A']})
            sql("INSERT INTO sys_role(id,role_code,role_name,role_level) VALUES ('" + prefix + "','dev','probe',10)")
            denied('administrator cannot grant developer', 'POST', '/sys/user/addSysUserRole', 'admin',
                   {'roleId': prefix, 'userIdList': ['fixture_student_a']})
            allowed('administrator creates account with validated roles and class', 'POST', '/sys/user/add', 'admin',
                    {'username': prefix + '_new', 'password': 'SecurePassword9!', 'realname': '合成管理账号',
                     'selectedroles': 'fixture_role_student', 'selecteddeparts': 'fixture_class_a',
                     'id': 'forged', 'status': 0, 'delFlag': 1})
            new_id = sql('SELECT id FROM sys_user WHERE username=' + literal(prefix + '_new'))
            check('new identity is server generated and active', new_id.isdigit() and
                  sql('SELECT CONCAT(status,del_flag) FROM sys_user WHERE id=' + literal(new_id)) == '10')
            credentials = sql('SELECT password,salt,username FROM sys_user WHERE id=' + literal(new_id))
            allowed('administrator edits allowed account fields', 'PUT', '/sys/user/edit', 'admin',
                    {'id': new_id, 'username': 'forged', 'password': 'forged', 'salt': 'forged',
                     'status': 0, 'realname': '合成已修改', 'selectedroles': 'fixture_role_teacher',
                     'selecteddeparts': 'fixture_class_b'})
            check('administrative edit preserves credentials and account identity',
                  sql('SELECT password,salt,username FROM sys_user WHERE id=' + literal(new_id)) == credentials)
            check('administrative edit commits selected memberships',
                  sql('SELECT role_id FROM sys_user_role WHERE user_id=' + literal(new_id)) == 'fixture_role_teacher' and
                  sql('SELECT dep_id FROM sys_user_depart WHERE user_id=' + literal(new_id)) == 'fixture_class_b')
            allowed('administrator logically deletes newly created account', 'DELETE', '/sys/user/delete?id=' + new_id, 'admin')
            allowed('administrator purges newly deleted account', 'DELETE', '/sys/user/deleteRecycleBin?userIds=' + new_id, 'admin')
            # The same token observes live role changes before and after each grant.
            denied('student has no recycle access before grant', 'GET', '/sys/user/recycleBin', 'student_a')
            allowed('administrator grants an allowed role', 'POST', '/sys/user/addSysUserRole', 'admin', role_body)
            allowed('same token observes newly granted role', 'GET', '/sys/user/recycleBin', 'student_a')
            allowed('administrator revokes role', 'DELETE', '/sys/user/deleteUserRole?' + urlencode(
                {'roleId': 'fixture_role_admin', 'userId': 'fixture_student_a'}), 'admin')
            denied('same token loses revoked role', 'GET', '/sys/user/recycleBin', 'student_a')
            # Preserve an authentic old Redis value across DB revocation. This models the
            # result of a failed eviction without changing Redis availability or configuration.
            sql('INSERT INTO sys_permission(id,name,perms,menu_type,del_flag,status) VALUES ('
                + literal(permission_id) + ",'probe','user:status',2,0,'1')")
            sql('INSERT INTO sys_role_permission(id,role_id,permission_id) VALUES ('
                + literal(permission_link) + ',' + literal(prefix) + ',' + literal(permission_id) + ')')
            for assignment, role in ((old_admin_grant, 'fixture_role_admin'), (old_dev_grant, prefix)):
                sql('INSERT INTO sys_user_role(id,user_id,role_id) VALUES (' + literal(assignment)
                    + ",'fixture_student_a'," + literal(role) + ')')
            allowed('live developer can edit its synthetic role', 'PUT', '/sys/role/edit', 'student_a',
                    {'id': prefix, 'roleName': '合成开发角色'})
            allowed('live administrator has recycle access', 'GET', '/sys/user/recycleBin', 'student_a')
            allowed('live permission authorizes status API', 'PUT', '/sys/user/frozenBatch', 'student_a',
                    {'ids': 'fixture_student_b', 'status': '1'})
            jar = (args.jar or Path(__file__).resolve().parents[1] / 'jeecg-boot-module-system/target/teaching-open-2.8.0.jar').resolve()
            stale_value = legacy_authorization_payload(api.runtime, jar)
            stale_hash = hashlib.sha1(stale_value).hexdigest()
            stale_key = 'shiro:cache:org.jeecg.modules.shiro.authc.ShiroRealm.authorizationCache:fixture_student_a'
            replay = "local value=ARGV[1]:gsub('..',function(h) return string.char(tonumber(h,16)) end); redis.call('SET',KEYS[1],value,'EX',200000); return redis.sha1hex(value)"
            check('canonical legacy administrator/developer cache is retained in owned Redis',
                  api.cache('EVAL', replay, '1', stale_key, stale_value.hex()) == stale_hash)
            sql('DELETE FROM sys_user_role WHERE id IN (' + literal(old_admin_grant) + ',' + literal(old_dev_grant) + ')')
            check('database revocation removes both old management roles',
                  sql("SELECT COUNT(*) FROM sys_user_role WHERE user_id='fixture_student_a' AND role_id IN ('fixture_role_admin',"
                      + literal(prefix) + ')') == '0')
            missing = prefix + '_missing'
            for method, route, body in (
                ('PUT', '/sys/role/edit', {'id': prefix, 'roleName': 'forged stale cache'}),
                ('POST', '/sys/role/add', {'id': prefix + '_r', 'roleCode': prefix + '_new', 'roleName': 'forged', 'roleLevel': 1}),
                ('DELETE', '/sys/role/delete?id=' + prefix, None),
                ('DELETE', '/sys/role/deleteBatch?ids=' + prefix, None),
                ('POST', '/sys/role/importExcel', {}),
                ('POST', '/sys/role/datarule', {'roleId': prefix, 'permissionId': permission_id, 'dataRuleIds': ''}),
                ('POST', '/sys/permission/add', {'id': prefix + '_p2', 'name': 'forged', 'menuType': 2, 'perms': '*'}),
                ('PUT', '/sys/permission/edit', {'id': permission_id, 'name': 'forged'}),
                ('POST', '/sys/permission/edit', {'id': permission_id, 'name': 'forged'}),
                ('DELETE', '/sys/permission/delete?id=' + permission_id, None),
                ('DELETE', '/sys/permission/deleteBatch?ids=' + permission_id, None),
                ('POST', '/sys/permission/saveRolePermission', {'roleId': prefix, 'permissionIds': '', 'lastpermissionIds': permission_id}),
                ('POST', '/sys/permission/saveDepartPermission', {'departId': 'fixture_class_a', 'permissionIds': permission_id, 'lastpermissionIds': ''}),
                ('POST', '/sys/permission/addPermissionRule', {'id': prefix + '_rule', 'permissionId': permission_id, 'ruleName': 'forged'}),
                ('PUT', '/sys/permission/editPermissionRule', {'id': prefix + '_rule', 'ruleName': 'forged'}),
                ('POST', '/sys/permission/editPermissionRule', {'id': prefix + '_rule', 'ruleName': 'forged'}),
                ('DELETE', '/sys/permission/deletePermissionRule?id=' + prefix + '_rule', None),
                ('POST', '/sys/sysDepartRole/add', {'id': prefix + '_dr', 'departId': 'fixture_class_a', 'roleName': 'forged'}),
                ('PUT', '/sys/sysDepartRole/edit', {'id': prefix + '_dr', 'roleName': 'forged'}),
                ('DELETE', '/sys/sysDepartRole/delete?id=' + prefix + '_dr', None),
                ('DELETE', '/sys/sysDepartRole/deleteBatch?ids=' + prefix + '_dr', None),
                ('POST', '/sys/sysDepartRole/deptRoleUserAdd', {'depId': 'fixture_class_a', 'userId': 'fixture_student_a', 'newRoleId': prefix + '_dr'}),
                ('POST', '/sys/sysDepartRole/datarule', {'roleId': prefix + '_dr', 'permissionId': permission_id, 'dataRuleIds': ''}),
                ('POST', '/sys/sysDepartRole/importExcel', {}),
                ('POST', '/sys/sysDepartPermission/add', {'id': prefix + '_dp', 'departId': 'fixture_class_a', 'permissionId': permission_id}),
                ('PUT', '/sys/sysDepartPermission/edit', {'id': prefix + '_dp', 'permissionId': permission_id}),
                ('DELETE', '/sys/sysDepartPermission/delete?id=' + prefix + '_dp', None),
                ('DELETE', '/sys/sysDepartPermission/deleteBatch?ids=' + prefix + '_dp', None),
                ('POST', '/sys/sysDepartPermission/importExcel', {}),
                ('POST', '/sys/sysDepartPermission/datarule', {'departId': 'fixture_class_a', 'permissionId': permission_id, 'dataRuleIds': ''}),
                ('POST', '/sys/sysDepartPermission/saveDeptRolePermission', {'roleId': prefix + '_dr', 'permissionIds': permission_id, 'lastpermissionIds': ''}),
                ('POST', '/sys/sysDepart/add', {'id': prefix + '_d', 'departName': 'forged'}),
                ('PUT', '/sys/sysDepart/edit', {'id': 'fixture_class_a', 'departName': 'forged'}),
                ('DELETE', '/sys/sysDepart/delete?id=' + missing, None),
                ('DELETE', '/sys/sysDepart/deleteBatch?ids=' + missing, None),
                ('POST', '/sys/sysDepart/importExcel', {}),
                ('GET', '/sys/sysDepart/removeAll?id=' + missing, None),
                ('POST', '/sys/user/add', {'username': prefix + '_denied', 'password': 'SecurePassword9!', 'realname': 'forged'}),
                ('PUT', '/sys/user/edit', {'id': 'fixture_student_a', 'realname': 'forged'}),
                ('DELETE', '/sys/user/delete?id=' + missing, None),
                ('DELETE', '/sys/user/deleteBatch?ids=' + missing, None),
                ('PUT', '/sys/user/changePassword', {'id': 'fixture_student_b', 'password': 'SecurePassword9!'}),
                ('POST', '/sys/user/importExcel', {}),
                ('POST', '/sys/user/importStudent', {}),
                ('POST', '/sys/user/addSysUserRole', role_body),
                ('DELETE', '/sys/user/deleteUserRole?roleId=fixture_role_student&userId=fixture_student_a', None),
                ('DELETE', '/sys/user/deleteUserRoleBatch?roleId=fixture_role_student&userIds=fixture_student_a', None),
                ('POST', '/sys/user/editSysDepartWithUser', {'depId': 'fixture_class_a', 'userIdList': ['fixture_student_a']}),
                ('DELETE', '/sys/user/deleteUserInDepart?depId=fixture_class_a&userId=fixture_student_a', None),
                ('DELETE', '/sys/user/deleteUserInDepartBatch?depId=fixture_class_a&userIds=fixture_student_a', None),
                ('GET', '/sys/user/recycleBin', None),
                ('PUT', '/sys/user/putRecycleBin', {'userIds': missing}),
                ('DELETE', '/sys/user/deleteRecycleBin?userIds=' + missing, None),
                ('PUT', '/sys/user/frozenBatch', {'ids': 'fixture_student_b', 'status': '2'})):
                authorization_denied('revoked roles ignore retained old cache ' + method + ' ' + route,
                                     method, route, 'student_a', body, stale_key, stale_hash)
            for probe in (probe_a, probe_b):
                sql('INSERT INTO sys_user(id,username,realname,status,del_flag) VALUES (' + literal(probe) + ','
                    + literal(probe) + ",'probe',1,1)")
                sql('INSERT INTO sys_user_role(id,user_id,role_id) VALUES (' + literal(probe) + ',' + literal(probe)
                    + ",'fixture_role_student')")
                sql('INSERT INTO sys_user_depart(id,user_id,dep_id) VALUES (' + literal(probe) + ',' + literal(probe)
                    + ",'fixture_class_a')")
            denied('normal account cannot be permanently deleted', 'DELETE', '/sys/user/deleteRecycleBin?userIds=fixture_student_a', 'admin')
            denied('mixed normal and deleted targets preserve all rows', 'DELETE', '/sys/user/deleteRecycleBin?' + urlencode(
                {'userIds': probe_a + ',fixture_student_a'}), 'admin')
            for route, method in (('/sys/user/deleteRecycleBin', 'DELETE'), ('/sys/user/putRecycleBin', 'PUT')):
                value = probe_a + "') OR 1=1 -- "
                denied('SQL-shaped ID is only a bound value ' + route, method,
                       route + ('?' + urlencode({'userIds': value}) if method == 'DELETE' else ''),
                       'admin', {'userIds': value} if method == 'PUT' else None)
            sql('CREATE TRIGGER ' + trigger + " BEFORE DELETE ON sys_user_role FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic relationship failure'")
            try:
                denied('relationship failure rolls back physical account deletion', 'DELETE',
                       '/sys/user/deleteRecycleBin?userIds=' + probe_a + ',' + probe_b, 'admin')
            finally:
                sql('DROP TRIGGER ' + trigger)
            allowed('restore accepts valid recycle account', 'PUT', '/sys/user/putRecycleBin', 'admin', {'userIds': probe_a})
            check('restore changes deletion state only', sql('SELECT del_flag FROM sys_user WHERE id=' + literal(probe_a)) == '0')
            allowed('purge removes deleted account', 'DELETE', '/sys/user/deleteRecycleBin?userIds=' + probe_b, 'admin')
            check('purge removes all related memberships', all(sql('SELECT COUNT(*) FROM ' + t + ' WHERE '
                  + ('id' if t == 'sys_user' else 'user_id') + '=' + literal(probe_b)) == '0'
                  for t in ('sys_user', 'sys_user_role', 'sys_user_depart', 'sys_depart_role_user')))
            sensitive = 'username,password,salt,phone,status,del_flag,depart_ids,user_identity'
            before = sql('SELECT ' + sensitive + " FROM sys_user WHERE id='fixture_student_a'")
            allowed('own profile updates permitted fields', 'PUT', '/teaching/user/edit', 'student_a',
                    {'id': 'fixture_student_a', 'realname': '合成个人资料', 'avatar': '', 'email': None, 'sex': 1, 'birthday': None})
            check('own profile preserves all sensitive columns', sql('SELECT ' + sensitive + " FROM sys_user WHERE id='fixture_student_a'") == before)
            before = sql("SELECT username,realname,status,del_flag,depart_ids,user_identity FROM sys_user WHERE id='fixture_student_b'")
            allowed('reset uses canonical username and only credentials', 'PUT', '/sys/user/changePassword', 'admin',
                    {'id': 'fixture_student_b', 'username': 'forged', 'realname': 'forged', 'status': 0, 'password': 'SecurePassword9!'})
            check('reset preserves identity and status', sql("SELECT username,realname,status,del_flag,depart_ids,user_identity FROM sys_user WHERE id='fixture_student_b'") == before)
            denied('old token is rejected after password reset', 'GET', '/sys/user/queryById?id=fixture_student_b', 'student_b')
        finally:
            sql('DROP TRIGGER IF EXISTS ' + trigger)
            for table in ('sys_user_role', 'sys_user_depart', 'sys_depart_role_user'):
                sql('DELETE FROM ' + table + ' WHERE user_id IN (SELECT id FROM sys_user WHERE username=' + literal(prefix + '_new') + ')')
            sql('DELETE FROM sys_user WHERE username=' + literal(prefix + '_new'))
            for table in ('sys_user_role', 'sys_user_depart', 'sys_depart_role_user'):
                sql('DELETE FROM ' + table + ' WHERE user_id IN (' + literal(probe_a) + ',' + literal(probe_b) + ')')
            sql("DELETE FROM sys_user_role WHERE user_id='fixture_student_a' AND role_id IN ('fixture_role_admin','fixture_role_teacher')")
            sql('DELETE FROM sys_user_role WHERE id IN (' + literal(old_admin_grant) + ',' + literal(old_dev_grant) + ')')
            sql('DELETE FROM sys_role_permission WHERE id=' + literal(permission_link))
            sql('DELETE FROM sys_permission WHERE id=' + literal(permission_id))
            sql('DELETE FROM sys_user WHERE id IN (' + literal(probe_a) + ',' + literal(probe_b) + ')')
            sql('DELETE FROM sys_role WHERE id=' + literal(prefix))
            for table, (columns, rows) in saved.items():
                for row in rows:
                    values = row.split('\t'); record = dict(zip(columns, ['NULL' if v == 'NULL' else "CONVERT(X'" + v + "' USING utf8mb4)" for v in values]))
                    sql('UPDATE ' + table + ' SET ' + ','.join('`' + c + '`=' + record[c] for c in columns if c != 'id') + ' WHERE id=' + record['id'])
            for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b'):
                clear(actor)
        check('original account and permission records restored', snapshot() == original)
        report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'owned synthetic HTTP/MySQL',
                  'jar_sha256': api.jar_sha256, 'production_connected': False, 'passed': len(checks), 'failed': 0, 'checks': checks}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    verify(parser.parse_args())
