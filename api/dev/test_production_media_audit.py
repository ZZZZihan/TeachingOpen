"""Independent controlled tests: owned temporary files and bounded child processes.

No retained course content, product service, database, Redis, or network is used.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import production_media_audit as audit


PRIVATE = 'PRIVATE_PATH_TEXT_password=DO_NOT_REPORT'


def atom(kind, body=b''):
    return struct.pack('>I4s', len(body) + 8, kind) + body


def media_bytes(layout='before', fragmented=False):
    # The container fixture has a self-contained data reference. It has no
    # playable frames; genuine parser integration uses a separate small fixture.
    ref = atom(b'url ', b'\0\0\0\1')
    dref = atom(b'dref', b'\0' * 4 + struct.pack('>I', 1) + ref)
    nested = atom(b'trak', atom(b'mdia', atom(b'minf', atom(b'dinf', dref))))
    moov = atom(b'moov', nested + (atom(b'mvex') if fragmented else b''))
    ftyp = atom(b'ftyp', b'isom\0\0\0\0isomiso2')
    data = atom(b'mdat', b'\0' * 4096)
    fragment = atom(b'moof') if fragmented else b''
    return ftyp + (moov + fragment + data if layout == 'before' else fragment + data + moov)


def one_page_pdf():
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] /Resources << >> /Contents 4 0 R >>',
               b'<< /Length 0 >>\nstream\n\nendstream']
    content, offsets = b'%PDF-1.4\n', [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(content))
        content += str(number).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    xref = len(content)
    content += b'xref\n0 5\n0000000000 65535 f \n'
    content += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return content + f'trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


def metadata_only_mp4():
    # A local ISO BMFF video track with no media samples. This checks parser
    # execution and stream metadata, and cannot establish decoding or playback.
    matrix = struct.pack('>9I', 0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000)
    mvhd = atom(b'mvhd', b'\0' * 12 + struct.pack('>II', 1000, 1000)
                + struct.pack('>IH', 0x10000, 0x100) + b'\0' * 10 + matrix + b'\0' * 24 + struct.pack('>I', 2))
    tkhd = atom(b'tkhd', b'\0\0\0\7' + b'\0' * 8 + struct.pack('>III', 1, 0, 1000)
                + b'\0' * 16 + matrix + struct.pack('>II', 64 << 16, 64 << 16))
    mdhd = atom(b'mdhd', b'\0' * 12 + struct.pack('>IIHH', 25, 25, 0x55c4, 0))
    hdlr = atom(b'hdlr', b'\0' * 8 + b'vide' + b'\0' * 12 + b'Controlled metadata fixture\0')
    dref = atom(b'dref', b'\0' * 4 + struct.pack('>I', 1) + atom(b'url ', b'\0\0\0\1'))
    # VisualSampleEntry and an AVC configuration record. No decoder runs here.
    visual = b'\0' * 6 + struct.pack('>H', 1) + b'\0' * 16 + struct.pack('>HH', 64, 64)
    visual += struct.pack('>IIIH', 72 << 16, 72 << 16, 0, 1) + b'\0' * 32 + struct.pack('>Hh', 24, -1)
    sps, pps = bytes.fromhex('6742c00addec0440000003004000000c83c489e0'), bytes.fromhex('68ce0fc8')
    avcc = bytes([1, 66, 0xc0, 10, 0xff, 0xe1]) + struct.pack('>H', len(sps)) + sps
    avcc += b'\1' + struct.pack('>H', len(pps)) + pps
    stsd = atom(b'stsd', b'\0' * 4 + struct.pack('>I', 1) + atom(b'avc1', visual + atom(b'avcC', avcc)))
    stbl = atom(b'stbl', stsd + atom(b'stts', b'\0' * 8) + atom(b'stsc', b'\0' * 8)
                + atom(b'stsz', b'\0' * 12) + atom(b'stco', b'\0' * 8))
    minf = atom(b'minf', atom(b'vmhd', b'\0\0\0\1' + b'\0' * 8) + atom(b'dinf', dref) + stbl)
    moov = atom(b'moov', mvhd + atom(b'trak', tkhd + atom(b'mdia', mdhd + hdlr + minf)))
    return atom(b'ftyp', b'isom\0\0\0\0isomiso2avc1') + moov + atom(b'mdat')


class OwnedFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='media-audit-tests-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def file(self, name, content, mode=0o600):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(mode)
        return path

    def safe_failure(self, call):
        with self.assertRaises(audit.AuditFailure) as raised:
            call()
        self.assertNotIn(PRIVATE, str(raised.exception))
        return raised.exception

    def snapshot(self, files=None):
        """Create the private manifest contract in a new owned .devspace child."""
        runtime = self.root / '.devspace' / 'snapshot'
        runtime.mkdir(parents=True, mode=0o700)
        (runtime / 'config').mkdir(mode=0o700)
        (runtime / 'uploads').mkdir(mode=0o700)
        ports = {'mysql': 13306, 'redis': 16379, 'backend': 18091, 'frontend': 18092}
        config = '\n'.join([
            'server.address=127.0.0.1', 'server.port=18091',
            'server.servlet.context-path=/api', 'spring.redis.host=127.0.0.1',
            'spring.redis.port=16379', 'spring.quartz.auto-startup=false',
            'justauth.enabled=false', f'jeecg.path.upload={runtime / "uploads"}',
            'spring.datasource.dynamic.datasource.master.url=jdbc:mysql://127.0.0.1:13306/teachingopen_dev?useSSL=false',
        ]).encode()
        names = ['config/application-localtest.properties', 'config/mysql.cnf',
                 'config/credentials.json', 'config/snapshot-app-client.cnf',
                 'snapshot-accounts.json', 'resource-references.json', 'sanitized.sql']
        for name in names:
            self.file(str((runtime / name).relative_to(self.root)), config if name.endswith('.properties') else b'{}\n')
        self.file(str((runtime / 'ports.json').relative_to(self.root)), json.dumps(ports).encode())
        records = {}
        for relative, content in (files or {PRIVATE + '.md': ('# heading\n' + PRIVATE).encode()}).items():
            self.file(str((runtime / 'uploads' / relative).relative_to(self.root)), content)
            records[relative] = {'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
        assets = {'files': records, 'count': len(records), 'bytes': sum(r['bytes'] for r in records.values()),
                  'student_files_copied': False, 'atomic_with_database': False,
                  'source_manifest_sha256': 'b' * 64}
        self.file(str((runtime / 'assets-result.json').relative_to(self.root)), json.dumps(assets).encode())
        names.append('assets-result.json')
        manifest = {'format': 1, 'kind': 'teachingopen-private-production-fixture',
                    'complete': True, 'runtime': str(runtime), 'datadir': str(runtime / 'mysql-data'),
                    'ports': ports, 'source_sha256': 'a' * 64, 'source_manifest_sha256': 'b' * 64,
                    'schema_policy_sha256': hashlib.sha256((Path(__file__).parent / 'production-fixture-schema.json').read_bytes()).hexdigest(),
                    'source_bytes': 10, 'assets_verified': True,
                    'student_attachments': 'withheld; not copied', 'redis_sessions_restored': False,
                    'private_files': {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest() for name in names}}
        self.rewrite_json(runtime / 'snapshot-manifest.json', manifest)
        return runtime, manifest, assets

    def rewrite_json(self, path, value):
        path.write_bytes(json.dumps(value).encode())
        path.chmod(0o600)


class SnapshotBoundaryContracts(OwnedFiles):
    def test_owned_snapshot_is_accepted_without_running_a_process(self):
        runtime, expected, assets = self.snapshot()
        with patch.object(audit, 'bounded_process') as child:
            manifest, actual, paths = audit.validate_snapshot(runtime)
        self.assertEqual(manifest, expected)
        self.assertEqual(actual, assets)
        self.assertEqual(set(paths), set(assets['files']))
        child.assert_not_called()

    def test_source_live_and_unbound_snapshot_shapes_fail_before_process(self):
        variants = [('kind', 'production-live'), ('format', True), ('complete', False), ('assets_verified', False),
                    ('runtime', str(self.root / PRIVATE)), ('datadir', '/var/lib/mysql'),
                    ('source_sha256', 'invalid'), ('schema_policy_sha256', '0' * 64),
                    ('source_bytes', True), ('student_attachments', 'included'), ('redis_sessions_restored', True)]
        runtime, original, _ = self.snapshot()
        for key, value in variants:
            changed = dict(original, **{key: value})
            self.rewrite_json(runtime / 'snapshot-manifest.json', changed)
            with self.subTest(key=key), patch.object(audit, 'bounded_process') as child:
                self.safe_failure(lambda: audit.validate_snapshot(runtime))
            child.assert_not_called()

    def test_private_metadata_permissions_symlink_and_changed_binding_fail(self):
        runtime, manifest, _ = self.snapshot()
        target = runtime / 'config/credentials.json'
        target.chmod(0o644)
        self.safe_failure(lambda: audit.validate_snapshot(runtime))
        target.chmod(0o600)
        target.write_bytes(PRIVATE.encode())
        self.safe_failure(lambda: audit.validate_snapshot(runtime))
        target.write_bytes(b'{}\n')
        link = runtime / 'snapshot-manifest.json'
        link.unlink()
        real = self.file('metadata-private.json', json.dumps(manifest).encode())
        link.symlink_to(real)
        self.safe_failure(lambda: audit.validate_snapshot(runtime))

    def test_escape_symlink_extra_file_and_special_file_are_rejected(self):
        runtime, manifest, assets = self.snapshot()
        name = next(iter(assets['files']))
        target = runtime / 'uploads' / name
        original = target.read_bytes()
        target.unlink()
        target.symlink_to(self.file('external-secret.md', original))
        self.safe_failure(lambda: audit.validate_snapshot(runtime))
        target.unlink()
        target.write_bytes(original)
        target.chmod(0o600)
        extra = runtime / 'uploads' / 'student-secret.md'
        extra.write_bytes(PRIVATE.encode())
        extra.chmod(0o600)
        self.safe_failure(lambda: audit.validate_snapshot(runtime))
        extra.unlink()
        special = runtime / 'uploads' / 'pipe'
        os.mkfifo(special, 0o600)
        self.safe_failure(lambda: audit.validate_snapshot(runtime))
        special.unlink()
        bad = dict(assets, files={'../' + name: assets['files'][name]})
        self.rewrite_json(runtime / 'assets-result.json', bad)
        manifest['private_files']['assets-result.json'] = hashlib.sha256((runtime / 'assets-result.json').read_bytes()).hexdigest()
        self.rewrite_json(runtime / 'snapshot-manifest.json', manifest)
        self.safe_failure(lambda: audit.validate_snapshot(runtime))

    def test_asset_manifest_count_size_digest_and_record_shape_cannot_lie(self):
        runtime, manifest, assets = self.snapshot()
        name = next(iter(assets['files']))
        variants = [dict(assets, count=2), dict(assets, count=True), dict(assets, bytes=0),
                    dict(assets, bytes=True), dict(assets, student_files_copied=True)]
        for record in [dict(assets['files'][name], bytes=True),
                       dict(assets['files'][name], bytes=assets['files'][name]['bytes'] + 1),
                       dict(assets['files'][name], sha256='z' * 64),
                       dict(assets['files'][name], path=PRIVATE)]:
            variants.append(dict(assets, files={name: record}))
        for index, value in enumerate(variants):
            self.rewrite_json(runtime / 'assets-result.json', value)
            manifest['private_files']['assets-result.json'] = hashlib.sha256((runtime / 'assets-result.json').read_bytes()).hexdigest()
            self.rewrite_json(runtime / 'snapshot-manifest.json', manifest)
            with self.subTest(variant=index):
                self.safe_failure(lambda: audit.validate_snapshot(runtime))

    def test_runtime_symlink_and_wrong_location_are_rejected(self):
        runtime, _, _ = self.snapshot()
        link = runtime.parent / 'linked'
        link.symlink_to(runtime, target_is_directory=True)
        for path in [link, self.root, self.root / PRIVATE]:
            with self.subTest(path=path):
                self.safe_failure(lambda: audit.validate_snapshot(path))

    def test_duplicate_json_keys_and_oversize_metadata_are_rejected(self):
        runtime, manifest, _ = self.snapshot()
        path = runtime / 'snapshot-manifest.json'
        original = path.read_bytes()
        path.write_bytes(b'{"format":1,"format":1,' + original[1:])
        self.assertEqual(self.safe_failure(lambda: audit.validate_snapshot(runtime)).code, 'duplicate_json_key')
        self.rewrite_json(path, manifest)
        with patch.object(audit, 'MAX_METADATA', 32), patch.object(Path, 'read_bytes') as payload:
            self.assertEqual(self.safe_failure(lambda: audit.validate_snapshot(runtime)).code, 'metadata_limit')
        payload.assert_not_called()

    def test_probe_binary_requires_real_executable_and_exact_name(self):
        real = self.file('ffprobe', b'#!/bin/sh\nexit 0\n', 0o700)
        self.assertEqual(audit.validate_binary(real, 'ffprobe'), real)
        link = self.root / 'linked-ffprobe'
        link.symlink_to(real)
        for path, name in [(link, 'ffprobe'), (real, 'pdfinfo'), (Path('ffprobe'), 'ffprobe')]:
            with self.subTest(path=path, name=name):
                self.safe_failure(lambda: audit.validate_binary(path, name))
        real.chmod(0o600)
        self.assertEqual(self.safe_failure(lambda: audit.validate_binary(real, 'ffprobe')).code, 'invalid_probe_binary')


class Mp4ContainerContracts(OwnedFiles):
    def test_both_moov_orders_and_fragmentation_are_distinguished(self):
        for layout, fragmented, expected in [('before', False, 'moov_before_mdat'),
                                             ('after', False, 'moov_after_mdat'),
                                             ('before', True, 'moov_before_mdat')]:
            with self.subTest(layout=layout, fragmented=fragmented):
                path = self.file('container.mp4', media_bytes(layout, fragmented))
                result = audit.mp4_atoms(path)
                self.assertEqual(result['layout'], expected)
                self.assertEqual(result['fragmented'], fragmented)
                self.assertGreater(result['self_contained_data_references'], 0)
                self.assertLess(result['header_bytes_read'], path.stat().st_size)

    def test_extended_and_to_end_mdat_are_bounded_without_reading_payload(self):
        original = media_bytes()
        marker = original.index(b'mdat') - 4
        prefix, payload = original[:marker], original[marker + 8:]
        variants = [prefix + struct.pack('>I4sQ', 1, b'mdat', 16 + len(payload)) + payload,
                    prefix + struct.pack('>I4s', 0, b'mdat') + payload]
        for content in variants:
            with self.subTest(header=content[marker:marker + 16]):
                result = audit.mp4_atoms(self.file('extended.mp4', content))
                self.assertEqual(result['layout'], 'moov_before_mdat')
                self.assertLess(result['header_bytes_read'], len(content))

    def test_truncated_overrunning_and_underlength_atoms_fail(self):
        invalid = [b'\0' * 7, struct.pack('>I4s', 7, b'moov'),
                   struct.pack('>I4s', 4096, b'moov') + b'\0',
                   struct.pack('>I4s', 1, b'moov') + b'\0' * 4,
                   atom(b'ftyp', b'isom\0\0\0\0') + atom(b'mdat')]
        for content in invalid:
            with self.subTest(content=content[:16]):
                self.safe_failure(lambda: audit.mp4_atoms(self.file('broken.mp4', content)))

    def test_nested_atom_cannot_escape_its_parent_even_with_valid_top_level_size(self):
        ftyp = atom(b'ftyp', b'isom\0\0\0\0')
        nested_overrun = struct.pack('>I4s', 1000, b'trak') + b'\0' * 8
        content = ftyp + atom(b'moov', nested_overrun) + atom(b'mdat', b'\0' * 64)
        self.safe_failure(lambda: audit.mp4_atoms(self.file('nested.mp4', content)))

    def test_external_data_reference_fails_before_media_parser(self):
        ref = atom(b'url ', b'\0' * 4 + b'https://example.invalid/' + PRIVATE.encode() + b'\0')
        dref = atom(b'dref', b'\0' * 4 + struct.pack('>I', 1) + ref)
        nested = atom(b'trak', atom(b'mdia', atom(b'minf', atom(b'dinf', dref))))
        content = atom(b'ftyp', b'isom\0\0\0\0') + atom(b'moov', nested) + atom(b'mdat', b'\0' * 64)
        with patch.object(audit, 'bounded_process') as child:
            self.safe_failure(lambda: audit.probe_mp4(self.file('external.mp4', content), Path('/usr/bin/ffprobe')))
        child.assert_not_called()


class MarkdownContracts(OwnedFiles):
    def test_text_metadata_has_counts_and_preserves_bytes(self):
        content = ('\ufeff# 第一节\r\n' + PRIVATE + '\n## 第二节\r\n').encode()
        path = self.file('private.md', content)
        before = path.read_bytes()
        result = audit.inspect_markdown(path)
        self.assertEqual(result['bytes'], len(content))
        self.assertTrue(result['utf8_bom'])
        self.assertGreaterEqual(result['headings'], 2)
        self.assertNotIn(PRIVATE, json.dumps(result))
        self.assertEqual(path.read_bytes(), before)

    def test_invalid_utf8_and_nul_are_failures(self):
        for content in [b'\xff' + PRIVATE.encode(), b'# ok\n\0' + PRIVATE.encode()]:
            with self.subTest(content=content[:8]):
                self.safe_failure(lambda: audit.inspect_markdown(self.file('bad.md', content)))

    def test_oversize_markdown_fails_before_opening_payload(self):
        path = self.file('oversize.md', b'x' * 33)
        with patch.object(audit, 'MAX_MARKDOWN', 32), patch.object(Path, 'open') as opened:
            failure = self.safe_failure(lambda: audit.inspect_markdown(path))
        self.assertEqual(failure.code, 'markdown_size_limit')
        opened.assert_not_called()


class ParserOutputContracts(OwnedFiles):
    def test_mp4_metadata_discards_tags_paths_and_unknown_text(self):
        payload = {'format': {'duration': '1.25', 'filename': PRIVATE, 'tags': {'title': PRIVATE}},
                   'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': 1280,
                                'height': 720, 'pix_fmt': 'yuv420p', 'avg_frame_rate': '25/1',
                                'tags': {'comment': PRIVATE}, 'filename': PRIVATE},
                               {'codec_type': 'audio', 'codec_name': 'aac', 'channels': 2,
                                'channel_layout': 'stereo', 'sample_rate': '48000', 'tags': {'title': PRIVATE}}]}
        with patch.object(audit, 'bounded_process', return_value=json.dumps(payload).encode()) as child:
            result = audit.probe_mp4(self.file('private.mp4', media_bytes()), Path('/usr/bin/ffprobe'))
        self.assertEqual(result['duration_seconds'], 1.25)
        self.assertEqual([s['codec_name'] for s in result['streams']], ['h264', 'aac'])
        self.assertNotIn(PRIVATE, json.dumps(result))
        args = child.call_args.args[0]
        self.assertIn('-protocol_whitelist', args)
        self.assertEqual(args[args.index('-protocol_whitelist') + 1], 'file')

    def test_malformed_or_impossible_mp4_json_is_not_success(self):
        invalid = [b'not json ' + PRIVATE.encode(), b'{}',
                   json.dumps({'streams': [], 'format': {'duration': 'nan'}}).encode(),
                   json.dumps({'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'width': -1, 'height': 720}]}).encode()]
        for output in invalid:
            with self.subTest(output=output[:40]), patch.object(audit, 'bounded_process', return_value=output):
                self.safe_failure(lambda: audit.probe_mp4(self.file('invalid.mp4', media_bytes()), Path('/usr/bin/ffprobe')))

    def test_pdf_metadata_discards_title_author_and_file_text(self):
        output = f'Title: {PRIVATE}\nAuthor: {PRIVATE}\nPages: 3\nEncrypted: no\nPDF version: 1.7\n'.encode()
        with patch.object(audit, 'bounded_process', return_value=output):
            result = audit.probe_pdf(self.file('private.pdf', b'%PDF-1.7\n'), Path('/usr/bin/pdfinfo'))
        self.assertEqual(result['pages'], 3)
        self.assertFalse(result['encrypted'])
        self.assertEqual(result['pdf_version'], '1.7')
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_pdf_info_missing_or_invalid_page_count_fails(self):
        for output in [PRIVATE.encode(), b'Pages: -1\nEncrypted: no\nPDF version: 1.7\n',
                       b'Pages: 0\nEncrypted: no\nPDF version: 1.7\n']:
            with self.subTest(output=output[:40]), patch.object(audit, 'bounded_process', return_value=output):
                self.safe_failure(lambda: audit.probe_pdf(self.file('invalid.pdf', b'%PDF-1.7\n'), Path('/usr/bin/pdfinfo')))


@unittest.skipUnless(shutil.which('ffprobe') and shutil.which('pdfinfo'), 'Optional local metadata parsers are unavailable')
class OwnedParserIntegration(OwnedFiles):
    def test_real_parsers_accept_only_owned_metadata_fixtures_and_preserve_them(self):
        mp4 = self.file('metadata-only.mp4', metadata_only_mp4())
        pdf = self.file('one-page.pdf', one_page_pdf())
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [mp4, pdf]}
        video = audit.probe_mp4(mp4, Path(shutil.which('ffprobe')).resolve())
        document = audit.probe_pdf(pdf, Path(shutil.which('pdfinfo')).resolve())
        self.assertEqual(video['duration_seconds'], 1.0)
        self.assertTrue(any(s['codec_name'] == 'h264' and s['width'] == 64 and s['height'] == 64 for s in video['streams']))
        self.assertEqual(document['pages'], 1)
        self.assertFalse(document['encrypted'])
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [mp4, pdf]})


class ChildProcessContracts(OwnedFiles):
    def child(self, program, **limits):
        return audit.bounded_process([sys.executable, '-I', '-c', program], **limits)

    def test_success_returns_only_stdout_and_discards_stderr(self):
        output = self.child(f'import sys; sys.stdout.write("ok"); sys.stderr.write({PRIVATE!r})')
        self.assertEqual(output, b'ok')

    def test_exit_start_and_timeout_fail_without_child_diagnostics(self):
        cases = [lambda: self.child(f'import sys; sys.stderr.write({PRIVATE!r}); sys.exit(9)'),
                 lambda: audit.bounded_process([str(self.root / PRIVATE)], timeout=.2),
                 lambda: self.child('import time; time.sleep(5)', timeout=.1)]
        expected = ['probe_exit', 'probe_start', 'probe_timeout']
        for call, code in zip(cases, expected):
            with self.subTest(code=code):
                self.assertEqual(self.safe_failure(call).code, code)

    def test_stdout_and_stderr_caps_fail_at_the_bound(self):
        for stream in ['stdout', 'stderr']:
            with self.subTest(stream=stream):
                call = lambda: self.child(f'import sys; sys.{stream}.write("x" * 4097)', max_stdout=4096, max_stderr=4096)
                self.assertEqual(self.safe_failure(call).code, 'probe_output_limit')

    def test_dead_leader_with_descendant_held_pipe_still_kills_the_group(self):
        # All descendants are created by this test. The child leader exits first;
        # its descendant keeps inherited stdout open until the timeout cleanup.
        pidfile = self.root / 'owned-descendant.pid'
        descendant = 'import time; time.sleep(10)'
        leader = ('import pathlib, subprocess, sys; '
                  f'p=subprocess.Popen([sys.executable,"-I","-c",{descendant!r}]); '
                  f'pathlib.Path({str(pidfile)!r}).write_text(str(p.pid))')
        actual_killpg = os.killpg
        pid = None
        try:
            with patch.object(audit.os, 'killpg', wraps=actual_killpg) as kill_group:
                self.assertEqual(self.safe_failure(lambda: self.child(leader, timeout=.3)).code, 'probe_timeout')
            self.assertTrue(pidfile.exists(), 'The owned leader must have spawned a descendant')
            pid = int(pidfile.read_text())
            kill_group.assert_called()
            self.assertTrue(any(call.args[1] == signal.SIGKILL for call in kill_group.call_args_list))
        finally:
            if pidfile.exists():
                pid = int(pidfile.read_text())
            if pid is not None:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


class RepresentativeContracts(unittest.TestCase):
    def video(self, number, codec='h264', layout='moov_before_mdat', audio=2, size=10, duration=1):
        streams = [{'codec_type': 'video', 'codec_name': codec}]
        if audio is not None:
            streams.append({'codec_type': 'audio', 'codec_name': 'aac', 'channels': audio})
        return {'asset_id': f'{number:064x}', 'kind': 'mp4', 'status': 'passed', 'bytes': size,
                'metadata': {'container': {'layout': layout}, 'streams': streams, 'duration_seconds': duration}}

    def test_permutations_keep_codec_audio_layout_coverage_and_extremes(self):
        videos = [self.video(1), self.video(2, codec='hevc', layout='moov_after_mdat', audio=None),
                  self.video(3, audio=6), self.video(4, duration=100), self.video(5, size=1000)]
        failed = dict(self.video(0, codec='PRIVATE_CODEC', size=99999, duration=99999), status='failed')
        records = videos + [failed]
        selected = audit.select_representatives(records)
        self.assertEqual(selected, audit.select_representatives(list(reversed(records))))
        by_id = {r['asset_id']: r for r in videos}
        chosen = [by_id[r['asset_id']] for r in selected]
        self.assertLessEqual(len(chosen), 5)
        self.assertEqual({r['metadata']['container']['layout'] for r in chosen}, {'moov_before_mdat', 'moov_after_mdat'})
        self.assertEqual({s['codec_name'] for r in chosen for s in r['metadata']['streams'] if s['codec_type'] == 'video'}, {'h264', 'hevc'})
        self.assertEqual({s['channels'] for r in chosen for s in r['metadata']['streams'] if s['codec_type'] == 'audio'}, {2, 6})
        reasons = {r['asset_id']: r['reasons'] for r in selected}
        self.assertIn('longest_duration', reasons[videos[3]['asset_id']])
        self.assertIn('largest_bytes', reasons[videos[4]['asset_id']])

    def test_ties_have_stable_identity_and_pdf_md_limits(self):
        tied = [self.video(12, size=100, duration=20), self.video(11, size=100, duration=20)]
        pdfs = [{'asset_id': f'{n:064x}', 'kind': 'pdf', 'status': 'passed', 'bytes': size, 'metadata': {'pages': pages}}
                for n, size, pages in [(20, 100, 100), (21, 200, 1), (22, 5, 1)]]
        texts = [{'asset_id': f'{n:064x}', 'kind': 'md', 'status': 'passed', 'bytes': 100, 'metadata': {'lines': 10}}
                 for n in [31, 30]]
        records = tied + pdfs + texts
        expected = audit.select_representatives(records)
        self.assertEqual(expected, audit.select_representatives(records[3:] + records[:3]))
        picked = {r['asset_id']: r for r in expected}
        self.assertIn('longest_duration', picked[f'{11:064x}']['reasons'])
        self.assertIn('largest_bytes', picked[f'{11:064x}']['reasons'])
        self.assertEqual(sum(r['kind'] == 'pdf' for r in expected), 2)
        self.assertIn('most_pages', picked[f'{20:064x}']['reasons'])
        self.assertIn('largest_bytes', picked[f'{21:064x}']['reasons'])
        self.assertEqual([r['asset_id'] for r in expected if r['kind'] == 'md'], [f'{30:064x}'])


class AuditFlowContracts(OwnedFiles):
    def tools(self):
        # No child uses these fixture executables: flows use Markdown or mock a
        # parser result. Separate integration tests use installed real parsers.
        return (self.file('tools/ffprobe', b'#!/bin/sh\nexit 0\n', 0o700),
                self.file('tools/pdfinfo', b'#!/bin/sh\nexit 0\n', 0o700))

    def run_audit(self, runtime):
        result = audit.audit(runtime, *self.tools())
        full = json.loads((runtime / result['report_directory'] / 'report.json').read_bytes())
        return result, full

    def test_source_sentinel_rejection_prevents_probes_and_report_creation(self):
        runtime, manifest, _ = self.snapshot()
        manifest['kind'] = 'source-production-export'
        self.rewrite_json(runtime / 'snapshot-manifest.json', manifest)
        with patch.object(audit, 'bounded_process') as child, patch.object(audit, 'validate_binary') as binary:
            self.safe_failure(lambda: audit.audit(runtime, *self.tools()))
        child.assert_not_called()
        binary.assert_not_called()
        self.assertFalse((runtime / 'reports').exists())

    def test_parse_failures_and_unsupported_assets_remain_in_denominator(self):
        files = {PRIVATE + '.md': b'# ok\n', 'broken.mp4': b'bad',
                 'failed.pdf': b'%PDF-1.4\n', 'unknown.bin': b'unknown', 'image.png': b'not decoded'}
        runtime, _, _ = self.snapshot(files)
        with patch.object(audit, 'probe_pdf', side_effect=audit.AuditFailure('probe_timeout')):
            result, full = self.run_audit(runtime)
        self.assertTrue(result['completed'])
        self.assertFalse(result['passed'])
        self.assertEqual(result['counts'], {'assets': 5, 'media_checked': 3, 'passed': 1, 'failed': 3, 'inventory_only': 1})
        self.assertEqual(sum(result['failures'].values()), 3)
        self.assertEqual(len(full['records']), 5)
        self.assertEqual(len(full['representatives']), 1)
        self.assertTrue(result['safety']['unchanged'])
        self.assertNotIn(PRIVATE, json.dumps(full))
        self.assertNotIn(str(self.root), json.dumps(full))
        self.assertNotIn('records', result)
        self.assertNotIn('representatives', result)

    def test_same_size_upload_mutation_makes_aggregate_fail(self):
        runtime, _, _ = self.snapshot({'private.md': b'# a\n'})
        original = audit.inspect_markdown
        def changed(path):
            metadata = original(path)
            before = path.stat()
            path.write_bytes(b'# b\n')
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1000000))
            return metadata
        with patch.object(audit, 'inspect_markdown', side_effect=changed):
            result, full = self.run_audit(runtime)
        self.assertFalse(result['passed'])
        self.assertEqual(result['counts']['assets'], 1)
        self.assertFalse(result['safety']['unchanged'])
        self.assertEqual(result['failures'], {'snapshot_changed': 1})
        self.assertEqual(len(full['records']), 1)

    def test_failed_parser_still_checks_changed_private_configuration(self):
        runtime, _, _ = self.snapshot({'private.md': b'# a\n'})
        def failed(path):
            (runtime / 'config/credentials.json').write_bytes(PRIVATE.encode())
            raise audit.AuditFailure('markdown_utf8')
        with patch.object(audit, 'inspect_markdown', side_effect=failed):
            result, full = self.run_audit(runtime)
        self.assertFalse(result['passed'])
        self.assertEqual(result['counts']['failed'], 1)
        self.assertEqual(result['failures'], {'markdown_utf8': 1, 'private_file_binding': 1})
        self.assertFalse(result['safety']['unchanged'])
        self.assertNotIn(PRIVATE, json.dumps(full))

    def test_reports_are_fresh_private_and_collision_does_not_overwrite(self):
        runtime, _, _ = self.snapshot()
        with patch.object(audit, 'uuid4', return_value=SimpleNamespace(hex='owned-fixed-id')):
            result, _ = self.run_audit(runtime)
            directory = runtime / result['report_directory']
            before = {p.name: p.read_bytes() for p in directory.iterdir()}
            with self.assertRaises(FileExistsError):
                self.run_audit(runtime)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(directory.parent.stat().st_mode), 0o700)
        for path in directory.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(path.read_bytes(), before[path.name])
        next_result, _ = self.run_audit(runtime)
        self.assertNotEqual(result['report_directory'], next_result['report_directory'])

    def test_cli_success_and_guard_failure_do_not_expose_paths_or_content(self):
        runtime, manifest, _ = self.snapshot()
        ffprobe, pdfinfo = self.tools()
        command = [sys.executable, str(Path(__file__).with_name('audit-production-media.py')),
                   '--runtime', str(runtime), '--ffprobe', str(ffprobe), '--pdfinfo', str(pdfinfo)]
        passed = subprocess.run(command, capture_output=True, timeout=5)
        self.assertEqual(passed.returncode, 0)
        result = json.loads(passed.stdout)
        self.assertTrue(result['passed'])
        self.assertEqual(result['counts']['assets'], 1)
        manifest['kind'] = PRIVATE
        self.rewrite_json(runtime / 'snapshot-manifest.json', manifest)
        rejected = subprocess.run(command, capture_output=True, timeout=5)
        self.assertEqual(rejected.returncode, 1)
        self.assertEqual(rejected.stdout, b'')
        self.assertEqual(json.loads(rejected.stderr)['error_code'], 'snapshot_binding')
        for output in [passed.stdout, passed.stderr, rejected.stdout, rejected.stderr]:
            self.assertNotIn(PRIVATE.encode(), output)
            self.assertNotIn(str(self.root).encode(), output)
            self.assertNotIn(b'Traceback', output)


if __name__ == '__main__':
    unittest.main()
