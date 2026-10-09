import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import check_java_results as java
import registration_mysql as registration


class CiGuardsTest(unittest.TestCase):
    def test_configuration_comments_are_not_placeholders_but_missing_values_fail(self):
        template = '# Fill @PLACEHOLDER@ in a private copy\nserver.port=@API_PORT@\n'
        self.assertEqual(registration.render_properties(template, {'API_PORT':'18259'}),
                         'server.port=18259\n')
        with self.assertRaises(KeyError): registration.render_properties(template, {})

    def test_local_or_self_hosted_execution_is_rejected_before_connection(self):
        for environment in ({}, {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'self-hosted'}):
            with patch.dict(os.environ, environment, clear=True), patch.object(registration.subprocess, 'run') as call:
                with self.assertRaises(RuntimeError):
                    registration.main()
                call.assert_not_called()

    def test_unrelated_workspace_is_rejected_before_connection(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted',
                'GITHUB_WORKSPACE':'/unrelated'}, clear=True), patch.object(registration.subprocess, 'run') as call:
            with self.assertRaises(RuntimeError):
                registration.main()
            call.assert_not_called()

    def test_missing_or_skipped_java_suites_are_not_success(self):
        with tempfile.TemporaryDirectory() as raw:
            reports = Path(raw)
            with self.assertRaises(RuntimeError): java.check(reports)
            for name in java.EXPECTED:
                (reports / ('TEST-' + name + '.xml')).write_text(
                    '<testsuite name="' + name + '" tests="1" failures="0" errors="0" skipped="0"/>')
            self.assertEqual(java.check(reports)['tests'], 4)
            name = sorted(java.EXPECTED)[0]
            (reports / ('TEST-' + name + '.xml')).write_text(
                '<testsuite name="' + name + '" tests="1" skipped="1"/>')
            with self.assertRaises(RuntimeError): java.check(reports)


if __name__ == '__main__': unittest.main()
