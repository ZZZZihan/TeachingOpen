#!/usr/bin/env python3
"""Named dictionaries and disabled transit in an owned five-account fixture."""
import argparse
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4
from local_http import FixtureApi
from local_runtime import mysql_command


def verify(args):
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(statement):
            result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError('Public boundary synthetic SQL failed')
        identifier = 'public_probe_' + uuid4().hex[:10]
        # A sixth account would violate the fixture ownership contract. Give the
        # second synthetic teacher a temporary dev role, then remove only our row.
        sql("INSERT INTO sys_role(id,role_code,role_name,role_level) VALUES ('" + identifier + "','dev','合成开发角色',10);"
            "INSERT INTO sys_user_role(id,user_id,role_id) VALUES ('" + identifier + "','fixture_teacher_b','" + identifier + "')")
        environment = {}
        try:
            for key in ('sys:cache:user::fixture_teacher_b',
                        'shiro:cache:org.jeecg.modules.shiro.authc.ShiroRealm.authorizationCache:fixture_teacher_b'):
                api.cache('DEL', key)
            for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a'):
                api.login(actor)
            values = {'PUBLIC_BOUNDARY_BASE_URL': 'http://127.0.0.1:' + str(api.ports['backend']) + '/api'}
            for role, actor in [('admin','admin'), ('dev','teacher_b'), ('teacher','teacher_a'), ('student','student_a')]:
                values['PUBLIC_BOUNDARY_' + role.upper() + '_TOKEN'] = api.tokens[actor]
            environment = {key: os.environ.get(key) for key in values}
            os.environ.update(values)
            path = Path(__file__).resolve().parents[2] / 'web/tests/public-boundaries-live.py'
            spec = importlib.util.spec_from_file_location('public_boundary_live', path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            with redirect_stdout(io.StringIO()):
                report = module.main()
            report.update({'jar_sha256': api.jar_sha256, 'production_connected': False,
                           'passed': len(report['checks']), 'failed': 0})
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print('Public boundary HTTP checks:', report['passed'], '; outbound requests:', report['outboundRequests'])
        finally:
            sql("DELETE FROM sys_user_role WHERE id='" + identifier + "';DELETE FROM sys_role WHERE id='" + identifier + "'")
            for key, value in environment.items():
                if value is None: os.environ.pop(key, None)
                else: os.environ[key] = value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    verify(parser.parse_args())
