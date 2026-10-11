"""Evidence-contract tests; synthetic reports are not browser execution evidence."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check_menu_browser_results as menu


class MenuBrowserEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name)
        self.sha = 'a' * 40
        self.blobs = {name: ('synthetic source ' + name).encode() for name in menu.SOURCES}
        self.source = {'ref': self.sha, 'resolved_ref': self.sha, 'files': [
            {'file': name, 'sha256': hashlib.sha256(data).hexdigest()} for name, data in self.blobs.items()]}
        self.report = {'completed': True, 'expected_legacy': False, 'source': self.source,
                       'browser': {'product': 'HeadlessChrome/151.0.0.0'},
                       'viewports': menu.VIEWPORTS, 'checks': [
                           {'case': name, 'passed': True} for name in sorted(menu.REQUIRED_CHECKS)],
                       'passed': len(menu.REQUIRED_CHECKS), 'total': len(menu.REQUIRED_CHECKS), 'failed': 0,
                       'clicks': [{'case': name, 'input': 'Chromium Input.dispatchMouseEvent'}
                                  for name in sorted(menu.REQUIRED_CLICKS)],
                       'external': [{'url': menu.HTTPS_FIXTURE, 'resourceType': 'Document',
                                     'intercepted_before_network': True} for _ in range(4)],
                       'blocked': [], 'errors': []}
        for name in menu.SCREENSHOTS:
            (self.output / name).write_bytes(menu.PNG_SIGNATURE + b'synthetic-test-image')
        self.git = patch.object(menu, 'git', side_effect=self.git_result).start()
        self.addCleanup(patch.stopall)

    def git_result(self, root, *args):
        if args == ('rev-parse', 'HEAD'):
            return (self.sha + '\n').encode()
        if args[0] == 'show' and args[1].startswith(self.sha + ':'):
            return self.blobs[args[1].split(':', 1)[1]]
        raise AssertionError(args)

    def check(self, report=None):
        (self.output / 'report.json').write_text(json.dumps(self.report if report is None else report))
        (self.output / 'sources.json').write_text(json.dumps(self.source))
        return menu.check(self.output / 'report.json', self.sha)

    def test_complete_fixed_candidate_browser_evidence_is_required(self):
        self.assertEqual(self.check()['checks'], 28)
        for change in ({'completed': False}, {'completed': 1}, {'expected_legacy': True},
                       {'checks': []}, {'passed': 27}, {'passed': True}, {'total': 27}, {'total': 28.0},
                       {'failed': 1}, {'errors': ['protocol failure']}, {'blocked': ['unexpected URL']},
                       {'browser': {}}, {'browser': {'product': 'JSDOM'}}, {'viewports': []}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self.check({**self.report, **change})

    def test_missing_or_failed_behavior_and_dom_only_clicks_cannot_pass(self):
        for name in menu.REQUIRED_CHECKS:
            report = deepcopy(self.report)
            report['checks'] = [check for check in report['checks'] if check['case'] != name]
            report['passed'] = report['total'] = len(report['checks'])
            with self.subTest(missing=name), self.assertRaises(RuntimeError):
                self.check(report)
        for key in ('checks', 'clicks'):
            report = deepcopy(self.report)
            report[key].append(report[key][0])
            with self.subTest(duplicate=key), self.assertRaises(RuntimeError):
                self.check(report)
        for name in menu.REQUIRED_CLICKS:
            report = deepcopy(self.report)
            report['clicks'] = [click for click in report['clicks'] if click['case'] != name]
            with self.subTest(missing_click=name), self.assertRaises(RuntimeError):
                self.check(report)
        report = deepcopy(self.report)
        report['checks'][0]['passed'] = False
        with self.assertRaises(RuntimeError): self.check(report)
        report = deepcopy(self.report)
        report['clicks'][0]['input'] = 'element.click()'
        with self.assertRaises(RuntimeError): self.check(report)

    def test_other_commit_source_hash_or_missing_screenshot_cannot_pass(self):
        for key in ('ref', 'resolved_ref'):
            report = deepcopy(self.report)
            report['source'][key] = 'b' * 40
            with self.subTest(key=key), self.assertRaises(RuntimeError): self.check(report)
        for key, value in (('sha256', '0' * 64), ('file', 'unexpected.vue')):
            report = deepcopy(self.report)
            report['source']['files'][0][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError): self.check(report)
        for name in menu.SCREENSHOTS:
            image = self.output / name
            image.unlink()
            with self.subTest(screenshot=name), self.assertRaises(RuntimeError): self.check()
            image.write_bytes(menu.PNG_SIGNATURE)
        self.check()
        (self.output / 'sources.json').write_text('{}')
        with self.assertRaises(RuntimeError): menu.check(self.output / 'report.json', self.sha)
        with self.assertRaises(RuntimeError): menu.check(self.output / 'report.json', 'HEAD')
        with patch.object(menu, 'git', return_value=('b' * 40).encode()), self.assertRaises(RuntimeError):
            self.check()

    def test_all_synthetic_https_requests_must_be_intercepted_before_network(self):
        for external in ([], self.report['external'][:3], self.report['external'] + self.report['external'][:1],
                         [{**item, 'intercepted_before_network': False} for item in self.report['external']],
                         [{**item, 'url': 'https://unexpected.invalid'} for item in self.report['external']]):
            with self.subTest(external=external), self.assertRaises(RuntimeError):
                self.check({**self.report, 'external': external})


if __name__ == '__main__':
    unittest.main()
