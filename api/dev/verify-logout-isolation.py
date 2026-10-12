#!/usr/bin/env python3
"""Verify logout isolation through a task-owned synthetic HTTP/Redis runtime.

Requires exclusive use of fixture_student_a/b for the duration of the check.
FixtureApi verifies loopback addressing, the five-user synthetic database,
runtime-owned Redis and the exact running JAR. No production target is accepted.
Credentials and Redis values remain in memory; reports contain only outcomes.
Normal login/logout audit rows are retained. Cleanup revokes only sessions
created by this run and never flushes Redis or deletes database records.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from local_http import FixtureApi
from local_runtime import mysql_command


TOKEN_PREFIX = 'userToken:'
PERMISSION_PREFIX = 'shiro:cache:org.jeecg.modules.shiro.authc.ShiroRealm.authorizationCache:'
PROFILE_PREFIX = 'sys:cache:user::'
ACTORS = ('student_a', 'student_b')
PROTECTED_ROUTE = '/teaching/teachingCourse/mineCourse'


def accepted(reply):
    return reply[0] == 200 and isinstance(reply[1], dict) and reply[1].get('success') is True


def refused(reply):
    return reply[0] in (400, 401, 403) or (
        reply[0] == 200 and isinstance(reply[1], dict) and reply[1].get('success') is False)


def token_username(token):
    try:
        payload = token.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        return claims.get('username') if isinstance(claims, dict) else None
    except (ValueError, IndexError, UnicodeDecodeError):
        return None


def invalid_signature(token):
    """Keep a real victim's header/claims and change the first signature bit."""
    parts = token.split('.')
    if len(parts) != 3 or not parts[2]:
        raise RuntimeError('Expected an actual three-part synthetic login token')
    parts[2] = ('A' if parts[2][0] != 'A' else 'B') + parts[2][1:]
    return '.'.join(parts)


def run(args):
    runtime = args.runtime.resolve()
    output = args.output.absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir() or output.parent.is_symlink():
        raise ValueError('Use a fresh output file in an existing evidence directory')
    api = FixtureApi(runtime, args.jar)
    cases = []
    sessions = {actor: set() for actor in ACTORS}
    login_seconds = {}
    owned_actors = set()
    cleanup_errors = []
    execution_error = None
    started = datetime.now(timezone.utc).isoformat()

    def check(name, value, **detail):
        cases.append({'case': name, 'passed': bool(value), **detail})
        print(('PASS ' if value else 'FAIL ') + name, flush=True)
        return bool(value)

    def sql(statement):
        reply = subprocess.run(mysql_command(runtime) + ['teachingopen_dev'], input=statement,
                               capture_output=True, text=True, timeout=20)
        if reply.returncode:
            raise RuntimeError('Synthetic SQL observation failed; private details withheld')
        return reply.stdout.strip()

    def audit_count():
        # Logout is anonymous, so userid may be NULL. Count the explicit success
        # message instead of incorrectly filtering by authenticated principal.
        return int(sql("SELECT COUNT(*) FROM sys_log WHERE log_type=1 AND log_content LIKE '%退出成功%';"))

    def keys(actor, token=None):
        username = 'fixture_' + actor
        result = {'username': TOKEN_PREFIX + username,
                  'permission': PERMISSION_PREFIX + username,
                  'profile': PROFILE_PREFIX + username}
        if token is not None:
            result['token'] = TOKEN_PREFIX + token
        return result

    def cache_bytes(key):
        reply = subprocess.run(api.redis + ['-n', '1', 'DUMP', key], env=api.redis_env,
                               capture_output=True, timeout=5)
        if reply.returncode:
            raise RuntimeError('Synthetic Redis observation failed; private details withheld')
        return reply.stdout

    def snapshot(actor, token):
        return {name: cache_bytes(key) for name, key in keys(actor, token).items()}

    def mapping(actor):
        raw = api.cache('GET', keys(actor)['username'])
        if not raw:
            return None
        value = json.loads(raw)
        if not isinstance(value, str):
            raise RuntimeError('Unexpected synthetic session mapping format')
        return value

    def active_tokens(actor):
        username = 'fixture_' + actor
        return {key[len(TOKEN_PREFIX):] for key in api.cache('KEYS', TOKEN_PREFIX + '*').splitlines()
                if token_username(key[len(TOKEN_PREFIX):]) == username}

    def authorized(token):
        return accepted(api.request('GET', PROTECTED_ROUTE, token=token))

    def rejected(token):
        reply = api.request('GET', PROTECTED_ROUTE, token=token)
        return reply[0] == 401 and isinstance(reply[1], dict) and reply[1].get('code') == 401

    def login(actor):
        # JwtUtil signs on a one-second clock. Waiting before another real login
        # prevents a same-token collision from hiding predecessor revocation.
        if actor in login_seconds:
            time.sleep(max(0, login_seconds[actor] + 1.05 - time.time()))
        prior = set(sessions[actor])
        api.login(actor)
        token = api.tokens[actor]
        sessions[actor].add(token)
        login_seconds[actor] = int(time.time())
        if token in prior:
            raise RuntimeError('Actual synthetic logins did not yield distinct tokens')
        if token_username(token) != 'fixture_' + actor:
            raise RuntimeError('Actual login returned another synthetic identity')
        return token

    def logout(token):
        return api.request('POST', '/sys/logout', token=token)

    try:
        # These guards run before every login. Other fixture identities may have
        # live sessions; they are never logged out or directly cleaned by us.
        for actor in ACTORS:
            if active_tokens(actor) or any(api.cache('EXISTS', key) != '0' for key in keys(actor).values()):
                raise RuntimeError('Selected synthetic account already has session/cache state')
        owned_actors.update(ACTORS)
        check('runtime, exact JAR and selected clean synthetic identities verified', True)
        a = login('student_a')
        check('control account A has protected access', authorized(a))
        # A denied management read also exercises its ordinary authorization
        # cache. Presence is observed rather than assumed for empty permissions.
        api.request('GET', '/teaching/teachingCourse/list', token=a)
        control = snapshot('student_a', a)

        initial = login('student_b')
        first = login('student_b')
        if not check('normal distinct single-session login revokes its predecessor',
                     initial != first and rejected(initial) and authorized(first)
                     and api.cache('EXISTS', TOKEN_PREFIX + initial) == '0'
                     and mapping('student_b') == first):
            raise RuntimeError('Effective single-session login is required for this regression')
        before = snapshot('student_b', first)
        before_audit = audit_count()
        forged = invalid_signature(first)
        reply = logout(forged)
        after_audit = audit_count()
        mapping_deleted = mapping('student_b') is None
        cache_unchanged = snapshot('student_b', first) == before
        check('invalid-signature logout response matches candidate',
              accepted(reply) if args.expect_legacy else refused(reply),
              http_status=reply[0], returned_success=accepted(reply))
        check('invalid-signature logout cache effects match candidate',
              mapping_deleted if args.expect_legacy else cache_unchanged,
              victim_username_mapping_deleted=mapping_deleted,
              victim_cache_unchanged=cache_unchanged)
        check('invalid-signature logout success audit matches candidate',
              after_audit == before_audit + 1 if args.expect_legacy else after_audit == before_audit,
              success_audit_delta=after_audit - before_audit)
        check('forgery preserves the victim token and account A caches/access',
              api.cache('EXISTS', TOKEN_PREFIX + first) == '1' and authorized(first)
              and snapshot('student_a', a) == control and authorized(a))

        second = login('student_b')
        check('login after forged logout uses a distinct authorized token and current index',
              second != first and authorized(second) and mapping('student_b') == second)
        old_authorized = authorized(first)
        check('old victim session after the next login matches candidate',
              old_authorized if args.expect_legacy else rejected(first),
              old_token_still_authorized=old_authorized)
        check('old victim Redis token after the next login matches candidate',
              api.cache('EXISTS', TOKEN_PREFIX + first) == ('1' if args.expect_legacy else '0'))

        check('normal current-session logout succeeds and removes its own cache state',
              accepted(logout(second)) and all(api.cache('EXISTS', key) == '0'
                                               for key in keys('student_b', second).values()))
        check('normally logged-out token loses protected access', rejected(second))
        repeat = logout(second)
        check('repeated signed logout succeeds without recreating session state',
              accepted(repeat) and all(api.cache('EXISTS', key) == '0'
                                      for key in keys('student_b', second).values()) and rejected(second))
        check('normal and repeated B logout preserve A caches/access',
              snapshot('student_a', a) == control and authorized(a))

        # Start an independent late-delivery sequence. Any legacy first token is
        # still owned by this run and is revoked in finally; it cannot be used as
        # the predecessor index for this sequence.
        late_first = login('student_b')
        current = login('student_b')
        check('late-logout sequence starts with distinct T1/T2 and revoked T1',
              late_first != current and rejected(late_first) and authorized(current)
              and api.cache('EXISTS', TOKEN_PREFIX + late_first) == '0'
              and mapping('student_b') == current)
        late_reply = logout(late_first)
        late_mapping_deleted = mapping('student_b') is None
        check('late valid T1 logout succeeds and removes only its token',
              accepted(late_reply) and api.cache('EXISTS', TOKEN_PREFIX + late_first) == '0'
              and rejected(late_first) and api.cache('EXISTS', TOKEN_PREFIX + current) == '1'
              and authorized(current))
        check('late T1 logout username index matches candidate',
              late_mapping_deleted if args.expect_legacy else mapping('student_b') == current,
              newer_username_mapping_deleted=late_mapping_deleted)
        third = login('student_b')
        check('T3 login has a distinct authorized token and owns the username index',
              third not in (late_first, current) and authorized(third) and mapping('student_b') == third)
        current_authorized = authorized(current)
        check('T3 login revocation of T2 after late T1 logout matches candidate',
              current_authorized if args.expect_legacy else rejected(current),
              t2_still_authorized=current_authorized)
        check('T2 Redis token after T3 login matches candidate',
              api.cache('EXISTS', TOKEN_PREFIX + current) == ('1' if args.expect_legacy else '0'))
        check('all B transitions preserve account A caches/access',
              snapshot('student_a', a) == control and authorized(a))
        check('every actual login token for each account is distinct',
              len(sessions['student_a']) == 1 and len(sessions['student_b']) == 6,
              actual_a_sessions=len(sessions['student_a']), actual_b_sessions=len(sessions['student_b']))
    except Exception as exc:
        execution_error = type(exc).__name__
        check('regression execution completed', False, error_type=execution_error)
    finally:
        # Do not use FixtureApi.close(): it remembers only each actor's newest
        # token, whereas this check deliberately creates several real sessions.
        # Never send a logout if a different run has acquired this username;
        # legacy logout would otherwise delete that unrelated session's index.
        for actor in owned_actors:
            try:
                foreign = active_tokens(actor) - sessions[actor]
                current_mapping = mapping(actor)
                safe = not foreign and (current_mapping is None or current_mapping in sessions[actor])
                if safe:
                    for token in sessions[actor]:
                        logout(token)
                for token in sessions[actor]:
                    api.cache('DEL', TOKEN_PREFIX + token)
                raw_mapping = api.cache('GET', keys(actor)['username'])
                if raw_mapping and json.loads(raw_mapping) in sessions[actor]:
                    api.cache('EVAL', "if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0",
                              '1', keys(actor)['username'], raw_mapping)
                if safe and mapping(actor) is None and not active_tokens(actor):
                    api.cache('DEL', keys(actor)['permission'], keys(actor)['profile'])
            except Exception as exc:
                cleanup_errors.append({'actor': actor, 'error_type': type(exc).__name__})
        api.tokens.clear()
        try:
            own_tokens_removed = all(api.cache('EXISTS', TOKEN_PREFIX + token) == '0'
                                     for actor in ACTORS for token in sessions[actor])
        except Exception as exc:
            cleanup_errors.append({'operation': 'final token readback', 'error_type': type(exc).__name__})
            own_tokens_removed = False
        check('cleanup revoked only the sessions created by this run',
              not cleanup_errors and own_tokens_removed,
              cleanup_errors=cleanup_errors)

    report = {'started_utc': started, 'ended_utc': datetime.now(timezone.utc).isoformat(),
              'runtime': str(runtime), 'ports': api.ports, 'jar_sha256': api.jar_sha256,
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'expected_legacy': args.expect_legacy, 'synthetic_only': True, 'credentials_exported': False,
              'scope': 'Real synthetic CAPTCHA/login, HTTP logout/protected access, Redis session/index/cache observations and success audit counts. Normal audit rows retained; no production or browser acceptance.',
              'passed': sum(case['passed'] for case in cases), 'total': len(cases), 'cases': cases,
              'exception_type': execution_error}
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(str(report['passed']) + '/' + str(report['total']) + ' checks passed', flush=True)
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    try:
        ok = run(parser.parse_args())
    except Exception as exc:
        # subprocess exception text can contain a Redis key with a JWT. Never
        # print a traceback or exception message from this credentialed probe.
        print('ERROR logout isolation probe: ' + type(exc).__name__, flush=True)
        raise SystemExit(1)
    raise SystemExit(0 if ok else 1)
