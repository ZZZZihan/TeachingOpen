from datetime import date
import unittest
from check_richtext_dependencies import check


class RichTextDependencyGateTest(unittest.TestCase):
    def setUp(self):
        self.lock = {'packages': {'': {}, 'node_modules/editor': {'dependencies': {'parser': '1'}},
                                 'node_modules/parser': {}, 'node_modules/build-tool': {}}}
        self.policy = {'runtime_roots': ['editor'], 'exceptions': []}
        self.audit = {'vulnerabilities': {}}

    def test_audits_transitive_runtime_and_does_not_mislabel_build_tools(self):
        self.audit['vulnerabilities']['build-tool'] = {'severity': 'critical', 'nodes': ['node_modules/build-tool']}
        self.assertEqual(check(self.lock, self.policy, self.audit)['locked_packages'], 2)
        self.audit['vulnerabilities']['parser'] = {'severity': 'high', 'nodes': ['node_modules/parser']}
        with self.assertRaises(ValueError): check(self.lock, self.policy, self.audit)

    def test_removed_editor_and_incomplete_registry_result_fail_closed(self):
        self.lock['packages']['node_modules/legacy/node_modules/tinymce'] = {}
        with self.assertRaises(ValueError): check(self.lock, self.policy, self.audit)
        with self.assertRaises(ValueError): check(self.lock, self.policy, {'error': 'registry unavailable'})

    def test_exception_must_identify_advisory_owner_reason_and_unexpired_date(self):
        url = 'https://example.test/advisory'
        self.audit['vulnerabilities']['parser'] = {'severity': 'high', 'nodes': ['node_modules/parser'], 'via': [{'url': url}]}
        item = {'package': 'parser', 'advisory': url, 'owner': 'maintainer', 'reason': 'reviewed case', 'expires': '2026-10-20'}
        self.policy['exceptions'] = [item]
        self.assertEqual(check(self.lock, self.policy, self.audit, date(2026,10,10))['exceptions'], 1)
        with self.assertRaises(ValueError): check(self.lock, self.policy, self.audit, date(2026,10,20))
        del item['owner']
        with self.assertRaises(ValueError): check(self.lock, self.policy, self.audit, date(2026,10,10))

    def test_production_module_inventory_includes_other_runtime_and_excludes_build_aggregates(self):
        self.lock['packages']['node_modules/request'] = {}
        self.audit['vulnerabilities']['request'] = {'severity': 'high', 'nodes': ['node_modules/request'], 'via': [{'url': 'https://example.test/request', 'severity': 'high'}]}
        with self.assertRaises(ValueError): check(self.lock, self.policy, self.audit, bundled=['node_modules/request'])
        self.audit['vulnerabilities'] = {
            'editor': {'severity': 'high', 'nodes': ['node_modules/editor'], 'via': ['build-tool']},
            'build-tool': {'severity': 'high', 'nodes': ['node_modules/build-tool'], 'via': [{'url': 'https://example.test/build', 'severity': 'high'}]}}
        self.assertEqual(check(self.lock, self.policy, self.audit, bundled=['node_modules/request'])['locked_packages'], 3)
        with self.assertRaises(ValueError): check(self.lock, self.policy, self.audit, bundled=['node_modules/build-tool'])
        with self.assertRaises(ValueError): check(self.lock, self.policy, self.audit, bundled=[])

    def test_high_advisory_without_url_and_malformed_inventory_fail_closed(self):
        self.audit['vulnerabilities']['parser'] = {'severity': 'high', 'nodes': ['node_modules/parser'], 'via': [{'source': 1, 'severity': 'high'}]}
        with self.assertRaises(ValueError): check(self.lock, self.policy, self.audit)
        for inventory in ({}, 'node_modules/editor', [None]):
            with self.assertRaises(ValueError): check(self.lock, self.policy, {'vulnerabilities': {}}, bundled=inventory)

    def test_missing_locked_dependency_is_not_a_clean_audit(self):
        del self.lock['packages']['node_modules/parser']
        with self.assertRaises(ValueError): check(self.lock, self.policy, self.audit)
