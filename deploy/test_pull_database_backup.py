import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('pull', Path(__file__).with_name('pull_database_backup.py'))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


def response(output='', remote_code=0, code=0):
    return SimpleNamespace(returncode=code, stdout=json.dumps({'exit_code':remote_code,'output':output}))


class ReadStateTests(unittest.TestCase):
    def test_valid_response_is_not_repeated(self):
        with patch.object(p.subprocess,'run',return_value=response('{"latest.json":{}}')) as call:
            self.assertEqual(p.read_state(['workbench']), {'latest.json':{}})
            self.assertEqual(call.call_count,1)

    def test_empty_success_retried_once(self):
        with patch.object(p.time,'sleep'), patch.object(p.subprocess,'run',side_effect=[response(),response('{"latest.json":{}}')]) as call:
            self.assertIn('latest.json',p.read_state(['workbench']))
            self.assertEqual(call.call_count,2)

    def test_repeated_empty_output_is_failure(self):
        with patch.object(p.time,'sleep'), patch.object(p.subprocess,'run',return_value=response()) as call:
            with self.assertRaises(RuntimeError): p.read_state(['workbench'])
            self.assertEqual(call.call_count,2)

    def test_nonzero_remote_exit_cannot_be_success(self):
        with patch.object(p.time,'sleep'), patch.object(p.subprocess,'run',return_value=response('{"latest.json":{}}',remote_code=1)):
            with self.assertRaises(RuntimeError): p.read_state(['workbench'])

    def test_malformed_state_cannot_be_success(self):
        with patch.object(p.time,'sleep'), patch.object(p.subprocess,'run',return_value=response('[]')):
            with self.assertRaises(RuntimeError): p.read_state(['workbench'])


if __name__ == '__main__': unittest.main()
