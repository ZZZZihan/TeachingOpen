import importlib.util
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
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


class CommandTests(unittest.TestCase):
    def state(self):
        now = datetime.now(timezone.utc).isoformat()
        return {'latest.json':{'snapshot':'20261009T150253Z-38d13b80', 'status':'complete',
                'created_at':now, 'database_sha256':hashlib.sha256(b'backup').hexdigest()},
                'last-backup.json':{'status':'complete'},
                'last-verify.json':{'status':'passed','checked_at':now},
                'units':{'teachingopen-backup.timer':'enabled','teachingopen-backup-verify.timer':'enabled'},
                'active':{'teachingopen-backup.timer':'active','teachingopen-backup-verify.timer':'active',
                          'teachingopen-api.service':'active','teachingopen-mysql.service':'active'}}

    def run_main(self, state, extra=()):
        argv = ['pull_database_backup.py', '--workbench','workbench','--instance','example',
                '--profile','example','--region','example',*extra]
        output = io.StringIO()
        with patch.object(sys,'argv',argv), patch.object(p,'read_state',return_value=state), redirect_stdout(output):
            p.main()
        return json.loads(output.getvalue())

    def test_default_checks_without_download_or_local_files(self):
        with tempfile.TemporaryDirectory() as raw, patch.object(p.subprocess,'run') as process:
            destination = Path(raw) / 'must-not-be-created'
            result = self.run_main(self.state(), ['--destination',str(destination)])
            self.assertEqual(result['mode'],'status_only')
            self.assertFalse(result['downloaded'])
            self.assertFalse(destination.exists())
            process.assert_not_called()

    def test_default_needs_no_destination(self):
        with patch.object(p.subprocess,'run') as process:
            self.assertEqual(self.run_main(self.state())['status'],'passed')
            process.assert_not_called()

    def test_status_only_still_rejects_stale_backup(self):
        state = self.state()
        state['latest.json']['created_at'] = (datetime.now(timezone.utc)-timedelta(hours=9)).isoformat()
        with patch.object(p.subprocess,'run') as process:
            with self.assertRaisesRegex(RuntimeError,'Backup is stale'):
                self.run_main(state)
            process.assert_not_called()

    def test_download_requires_explicit_destination(self):
        with patch.object(p.subprocess,'run') as process, redirect_stdout(io.StringIO()), patch('sys.stderr',new_callable=io.StringIO):
            with self.assertRaises(SystemExit): self.run_main(self.state(), ['--download'])
            process.assert_not_called()

    def test_explicit_download_verifies_bytes_and_reuses_existing_copy(self):
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw) / 'private'
            def download(command, **kwargs):
                index = command.index('download')
                Path(command[index+2]).write_bytes(b'backup')
                return SimpleNamespace(returncode=0)
            with patch.object(p.subprocess,'run',side_effect=download) as process:
                args = ['--download','--destination',str(destination)]
                self.assertEqual(self.run_main(self.state(), args)['bytes'],6)
                self.run_main(self.state(), args)
                self.assertEqual(process.call_count,1)
            target = destination / '20261009T150253Z-38d13b80.sql.gz'
            self.assertEqual(target.read_bytes(),b'backup')
            self.assertEqual(target.stat().st_mode & 0o777,0o600)


if __name__ == '__main__': unittest.main()
