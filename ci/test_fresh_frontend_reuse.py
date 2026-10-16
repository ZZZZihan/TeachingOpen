"""Offline regressions: historical evidence never replaces a fresh push frontend.

All GitHub receipts and dependency advisories are synthetic. No registry,
GitHub, database, browser, or production service is contacted by these tests.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import itertools
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import check_required_jobs as required
import check_richtext_dependencies as dependencies
import ci_reuse as reuse
from test_ci_reuse import valid_fixture, timestamp


ROOT = Path(__file__).resolve().parents[1]


class FreshFrontendRequiredTests(unittest.TestCase):
    def setUp(self):
        self.fixture = valid_fixture()
        self.proof = reuse.validate_evidence(*self.fixture)
        self.target_sha = self.fixture[0]['sha']

    def needs(self, frontend='success', backend='skipped', tools='skipped'):
        return {
            'changes': {'result': 'skipped', 'outputs': {}},
            'reuse': {'result': 'success', 'outputs': {
                'reuse': 'true', 'source_run_id': str(self.proof['source_run_id'])}},
            'frontend': {'result': frontend},
            'backend': {'result': backend},
            'tools': {'result': tools},
        }

    def check(self, needs, proof=None):
        return required.check('push', needs, reuse_proof=self.proof if proof is None else proof,
                              target_sha=self.target_sha)

    def test_only_fresh_frontend_and_successful_or_proven_skipped_other_jobs_pass(self):
        states = ('success', 'skipped', 'failure', 'cancelled', None)
        for frontend, backend, tools in itertools.product(states, repeat=3):
            allowed = frontend == 'success' and all(
                state in ('success', 'skipped') for state in (backend, tools))
            with self.subTest(frontend=frontend, backend=backend, tools=tools):
                needs = self.needs(frontend, backend, tools)
                if allowed:
                    self.assertIsNone(self.check(needs))
                else:
                    with self.assertRaises(ValueError):
                        self.check(needs)

    def test_missing_or_malformed_frontend_never_inherits_source_success(self):
        for frontend in (None, [], 'success', {}, {'conclusion': 'success'}):
            needs = self.needs()
            needs['frontend'] = frontend
            with self.subTest(frontend=frontend), self.assertRaises(ValueError):
                self.check(needs)
        needs = self.needs()
        del needs['frontend']
        with self.assertRaises(ValueError):
            self.check(needs)

    def test_skipped_backend_or_tools_require_valid_proof(self):
        for backend, tools in (('skipped', 'success'), ('success', 'skipped'), ('skipped', 'skipped')):
            needs = self.needs(backend=backend, tools=tools)
            with self.subTest(backend=backend, tools=tools):
                with self.assertRaises(ValueError):
                    required.check('push', needs, target_sha=self.target_sha)
                for key in self.proof:
                    incomplete = deepcopy(self.proof)
                    del incomplete[key]
                    with self.subTest(missing=key), self.assertRaises(ValueError):
                        self.check(needs, incomplete)

    def test_entrypoint_revalidates_each_mixed_skip_and_fails_closed_when_revalidation_fails(self):
        for backend, tools in (('skipped', 'success'), ('success', 'skipped'), ('skipped', 'skipped')):
            needs = self.needs(backend=backend, tools=tools)
            environment = {'CI_EVENT_NAME': 'push', 'CI_NEEDS_JSON': json.dumps(needs),
                           'GITHUB_SHA': self.target_sha}
            for failure in (False, True):
                with self.subTest(backend=backend, tools=tools, failure=failure), \
                        patch.dict(os.environ, environment, clear=True), \
                        patch('sys.argv', ['check_required_jobs.py']), \
                        patch.object(reuse, 'authorize', return_value=self.proof,
                                     side_effect=ValueError('Source evidence changed') if failure else None) as authorize, \
                        patch('sys.stdout', new_callable=io.StringIO), \
                        patch('sys.stderr', new_callable=io.StringIO):
                    self.assertEqual(required.main(), 1 if failure else 0)
                    authorize.assert_called_once_with(needs)

    def test_full_success_needs_no_reuse_and_pr_selective_skips_remain_valid(self):
        self.assertIsNone(required.check('push', self.needs('success', 'success', 'success')))
        for selection in itertools.product(('true', 'false'), repeat=3):
            needs = self.needs()
            needs['changes'] = {'result': 'success', 'outputs': {
                'selective': 'true', **dict(zip(required.JOBS, selection))}}
            for job, selected in zip(required.JOBS, selection):
                needs[job]['result'] = 'success' if selected == 'true' else 'skipped'
            with self.subTest(selection=selection):
                self.assertIsNone(required.check('pull_request', needs))

    def dependency_fixture(self):
        lock = {'packages': {'': {}, 'node_modules/editor': {}, 'node_modules/runtime': {}}}
        policy = {'runtime_roots': ['editor'], 'exceptions': []}
        audit = {'vulnerabilities': {}}
        return lock, policy, audit

    def assert_current_dependency_failure_blocks_required(self, lock, policy, audit, today):
        with self.assertRaises(ValueError):
            dependencies.check(lock, policy, audit, today=today, bundled=['node_modules/runtime'])
        # A failed live gate makes the existing frontend job fail. Historical
        # successful source receipts cannot override that current job outcome.
        with self.assertRaises(ValueError):
            self.check(self.needs(frontend='failure'))

    def test_new_npm_advisory_blocks_current_frontend_despite_valid_same_tree_proof(self):
        lock, policy, audit = self.dependency_fixture()
        today = self.fixture[-1].date()
        self.assertEqual(dependencies.check(lock, policy, audit, today=today,
                         bundled=['node_modules/runtime'])['status'], 'passed')
        audit['vulnerabilities']['runtime'] = {
            'severity': 'high', 'nodes': ['node_modules/runtime'],
            'via': [{'url': 'https://example.test/new-runtime-advisory', 'severity': 'high'}]}
        self.assertEqual(reuse.validate_evidence(*self.fixture), self.proof)
        self.assert_current_dependency_failure_blocks_required(lock, policy, audit, today)

    def test_utc_expiry_changes_within_same_shanghai_business_day_and_blocks_frontend(self):
        target, pr, run, jobs, receipts, original_now = valid_fixture()
        before = datetime(2026, 10, 15, 23, 59, tzinfo=timezone.utc)
        after = before + timedelta(minutes=2)
        shift = before - original_now
        for obj, fields in [(run, ('created_at', 'updated_at'))] + [
                (job, ('started_at', 'completed_at')) for job in jobs] + [
                (receipt, ('recorded_at',)) for receipt in receipts.values()]:
            for field in fields:
                obj[field] = timestamp(reuse.timestamp(obj[field]) + shift)
        self.assertNotEqual(before.date(), after.date())
        self.assertEqual(before.astimezone(ZoneInfo('Asia/Shanghai')).date(),
                         after.astimezone(ZoneInfo('Asia/Shanghai')).date())
        self.proof = reuse.validate_evidence(target, pr, run, jobs, receipts, after)
        lock, policy, audit = self.dependency_fixture()
        advisory = 'https://example.test/expiring-runtime-advisory'
        audit['vulnerabilities']['runtime'] = {
            'severity': 'high', 'nodes': ['node_modules/runtime'],
            'via': [{'url': advisory, 'severity': 'high'}]}
        policy['exceptions'] = [{'package': 'runtime', 'advisory': advisory,
            'owner': 'synthetic-maintainer', 'reason': 'synthetic exception',
            'expires': after.date().isoformat()}]
        self.assertEqual(dependencies.check(lock, policy, audit, today=before.date(),
                         bundled=['node_modules/runtime'])['exceptions'], 1)
        self.assert_current_dependency_failure_blocks_required(lock, policy, audit, after.date())


class FreshFrontendWorkflowTests(unittest.TestCase):
    def test_token_permissions_remain_existing_read_only_scopes(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        declarations = re.findall(r'(?m)^( *)permissions:([^\n]*)\n((?: +[^\n]*\n)*)', workflow)
        self.assertEqual(len(declarations), 3)
        scopes = []
        for indentation, inline, following in declarations:
            self.assertEqual(inline.strip(), '')
            entries = {}
            for line in following.splitlines():
                depth = len(line) - len(line.lstrip())
                if depth <= len(indentation):
                    break
                key, value = line.strip().split(':', 1)
                entries[key] = value.strip()
            scopes.append(entries)
        self.assertEqual(scopes, [
            {'contents': 'read'},
            {'contents': 'read', 'actions': 'read'},
            {'contents': 'read', 'actions': 'read'},
        ])

    def test_frontend_keeps_pr_selection_but_has_no_reuse_skip_or_step_bypass(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        frontend = workflow.split('\n  frontend:\n', 1)[1].split('\n  tools:\n', 1)[0]
        guard = frontend.split('    if: >-\n', 1)[1].split('    runs-on:', 1)[0]
        self.assertNotIn('needs.reuse', guard)
        self.assertEqual(' '.join(guard.split()),
            "${{ !cancelled() && (github.event_name != 'pull_request' || "
            "needs.changes.result != 'success' || needs.changes.outputs.selective != 'true' || "
            "needs.changes.outputs.frontend != 'false') }}")
        live_steps = frontend.split('      - name: Store synthetic menu browser evidence', 1)[0]
        self.assertNotIn('continue-on-error', live_steps)
        self.assertNotIn('\n        if:', live_steps)
        commands = ('npm ci --ignore-scripts --no-audit --no-fund', 'run: npm test',
            'node tests/announcement-rendering.browser.cjs', 'node tests/upload-credentials.browser.cjs',
            'node tests/teaching-menu-browser.cjs', 'python3 ../ci/check_menu_browser_results.py',
            "TEACHING_DEPENDENCY_REPORT: '1'", 'run: npm run build',
            'run: python3 ci/check_richtext_dependencies.py', 'run: npm run check:initial-assets')
        positions = []
        for command in commands:
            self.assertIn(command, live_steps)
            positions.append(live_steps.index(command))
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('--audit-report', live_steps)
        gate = Path(dependencies.__file__).read_text()
        self.assertIn("['npm', 'audit', '--json']", gate)
        self.assertIn("web/dist/runtime-dependencies.json", gate)
        self.assertIn("bundled=runtime.get('packages')", gate)
        self.assertIn('hashlib.sha256(lock_bytes).hexdigest()', gate)


if __name__ == '__main__':
    unittest.main()
