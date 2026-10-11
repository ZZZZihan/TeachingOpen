"""Synthetic profile-cache fixtures and live HTTP class-revocation checks."""
import hashlib
import json


def cache_fixture_user(api, sql, actor):
    if actor not in ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b'):
        raise ValueError('Only the owned five-account fixture can populate this cache')
    # This is the @Cacheable GenericJackson2JsonRedisSerializer contract. Keep
    # the real synthetic password hash in private Redis only; never print it.
    username = 'fixture_' + actor
    value = sql("SELECT JSON_OBJECT('@class','org.jeecg.common.system.vo.LoginUser',"
                "'id',id,'username',username,'password',password,'status',status,"
                "'delFlag',del_flag,'departIds',depart_ids,'orgCode',org_code) "
                "FROM sys_user WHERE username='" + username + "'")
    parsed = json.loads(value)
    if parsed.get('username') != username or parsed.get('id') != username:
        raise RuntimeError('Unexpected cache fixture identity')
    key = 'sys:cache:user::' + username
    if api.cache('SET', key, value, 'EX', '21600') != 'OK':
        raise RuntimeError('Unable to seed the owned profile cache')
    return key, value


def verify_teacher_revocation(api, sql, check):
    tables = ('teaching_work', 'teaching_work_correct', 'teaching_work_comment', 'sys_file')
    def snapshot():
        return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest()
                for table in tables}
    actor = 'teacher_a'
    # Caller owns the fixture and has already logged in; save the actual row
    # before changing its managed scope, then restore it even on assertion failure.
    saved = sql("SELECT IFNULL(HEX(depart_ids),'NULL') FROM sys_user WHERE id='fixture_teacher_a'")
    key, stale = cache_fixture_user(api, sql, actor)
    initial = snapshot()
    try:
        for route in ('/teaching/teachingWork/queryById?id=fixture_work_a',
                      '/system/sysFile/queryById?id=fixture_file_a'):
            status, result, _ = api.request('GET', route, actor)
            check('current teacher scope permits ' + route,
                  status == 200 and result and result.get('success') is True)
        sql("UPDATE sys_user SET depart_ids='' WHERE id='fixture_teacher_a'")
        # Reproduce both successful eviction followed by late cache fill, and
        # a retained value after eviction failure. No production cache is used.
        for mode in ('late fill after eviction', 'retained after eviction failure'):
            if mode.startswith('late'):
                api.cache('DEL', key)
            api.cache('SET', key, stale, 'EX', '21600')
            before = snapshot()
            for method, route, body in (
                ('GET', '/teaching/teachingWork/queryById?id=fixture_work_a', None),
                ('PUT', '/teaching/teachingWork/edit', {'id': 'fixture_work_a', 'workName': 'must stay unchanged'}),
                ('GET', '/system/sysFile/queryById?id=fixture_file_a', None),
                ('GET', '/sys/common/static/fixture-work-a.txt', None),
                ('HEAD', '/sys/common/static/fixture-work-a.txt', None)):
                status, result, _ = api.request(method, route, actor, body)
                check(mode + ': same token rejects ' + method + ' ' + route,
                      status in (401, 403) or result and result.get('success') is False
                      and result.get('code') in (401, 403, 510))
                check(mode + ': denial leaves work, feedback and files unchanged', snapshot() == before)
                check(mode + ': old cached scope remains but grants no access', api.cache('GET', key) == stale)
        check('scope probe never mutates work or file state', snapshot() == initial)
    finally:
        sql("UPDATE sys_user SET depart_ids=" + ('NULL' if saved == 'NULL' else "CONVERT(X'" + saved + "' USING utf8mb4)")
            + " WHERE id='fixture_teacher_a'")
        api.cache('DEL', key)
