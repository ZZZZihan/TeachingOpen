"""Bounded offline inspection of a reviewed private course-asset snapshot.

No database, service or browser calls. This proves metadata parsing, not decoding,
browser playback/seeking, rendering, or a fresh full-content hash of the snapshot.
"""
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import struct
import subprocess
import time
from uuid import uuid4

from local_recovery import local_path, private_write, sha256
from local_runtime import DEFAULT_PORTS, validate_ports
from production_fixture import FORMAT, KIND, SCHEMA_PROFILE, ordinary_asset, read_private, safe_relative

REPORT_FORMAT = 1
PROBE_TIMEOUT = 20
MAX_STDOUT = 512 * 1024
MAX_STDERR = 64 * 1024
MAX_METADATA = 16 * 1024 * 1024
MAX_MARKDOWN = 4 * 1024 * 1024
MAX_ATOMS = 4096
MAX_HEADER_BYTES = 128 * 1024
PRIVATE_FILES = frozenset({
    'config/application-localtest.properties', 'config/mysql.cnf', 'config/credentials.json',
    'config/snapshot-app-client.cnf', 'snapshot-accounts.json', 'resource-references.json',
    'sanitized.sql', 'assets-result.json',
})
HEX = re.compile(r'[0-9a-f]{64}')


class AuditFailure(ValueError):
    """Only constant error codes cross the private-data boundary."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _ordinary(path, directory=False, private=False):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise AuditFailure('unsafe_path')
    mode = path.lstat().st_mode
    if not (stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)):
        raise AuditFailure('not_ordinary')
    if private and mode & 0o077:
        raise AuditFailure('not_private')
    return path


def _json_private(path):
    _ordinary(path, private=True)
    if path.stat().st_size > MAX_METADATA:
        raise AuditFailure('metadata_limit')
    try:
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise AuditFailure('duplicate_json_key')
                result[key] = value
            return result
        result = json.loads(read_private(path), object_pairs_hook=pairs)
    except (ValueError, UnicodeError) as error:
        if isinstance(error, AuditFailure):
            raise
        raise AuditFailure('invalid_json') from None
    if not isinstance(result, dict):
        raise AuditFailure('invalid_json_shape')
    return result


def _valid_digest(value):
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def _ports(runtime):
    path = runtime / 'ports.json'
    result = _json_private(path) if path.exists() or path.is_symlink() else dict(DEFAULT_PORTS)
    try:
        return validate_ports(result)
    except (ValueError, TypeError):
        raise AuditFailure('invalid_ports') from None


def validate_snapshot(runtime):
    """Validate file bindings only; deliberately do not call fixture.verify()."""
    runtime = Path(runtime)
    if not runtime.is_absolute():
        raise AuditFailure('runtime_not_absolute')
    try:
        runtime = local_path(runtime)
        _ordinary(runtime, directory=True, private=True)
        manifest = _json_private(runtime / 'snapshot-manifest.json')
        if (type(manifest.get('format')) is not int or manifest['format'] != FORMAT or manifest.get('kind') != KIND
                or manifest.get('complete') is not True or manifest.get('runtime') != str(runtime)
                or manifest.get('datadir') != str(runtime / 'mysql-data')
                or manifest.get('ports') != _ports(runtime)):
            raise AuditFailure('snapshot_binding')
        if (any(not _valid_digest(manifest.get(key)) for key in
                ('source_sha256', 'source_manifest_sha256', 'schema_policy_sha256'))
                or manifest['schema_policy_sha256'] != sha256(SCHEMA_PROFILE)
                or type(manifest.get('source_bytes')) is not int or manifest['source_bytes'] <= 0
                or manifest.get('assets_verified') is not True
                or manifest.get('student_attachments') != 'withheld; not copied'
                or manifest.get('redis_sessions_restored') is not False):
            raise AuditFailure('source_policy_binding')
        private = manifest.get('private_files')
        if not isinstance(private, dict) or set(private) != PRIVATE_FILES:
            raise AuditFailure('private_file_allowlist')
        for name, digest in private.items():
            path = _ordinary(runtime / name, private=True)
            if not _valid_digest(digest) or sha256(path) != digest:
                raise AuditFailure('private_file_binding')
        assets = _json_private(runtime / 'assets-result.json')
        files = assets.get('files')
        if (not isinstance(files, dict) or not _valid_digest(assets.get('source_manifest_sha256'))
                or assets.get('student_files_copied') is not False
                or assets.get('atomic_with_database') is not False
                or type(assets.get('count')) is not int or assets['count'] != len(files)
                or type(assets.get('bytes')) is not int):
            raise AuditFailure('asset_manifest_shape')
        paths = {}
        for relative, record in files.items():
            if (not isinstance(record, dict) or set(record) != {'bytes', 'sha256'}
                    or type(record['bytes']) is not int or record['bytes'] < 0
                    or not _valid_digest(record['sha256']) or safe_relative(relative) != relative):
                raise AuditFailure('asset_record_shape')
            item = ordinary_asset(runtime / 'uploads', relative)
            _ordinary(item, private=True)
            if item.stat().st_size != record['bytes']:
                raise AuditFailure('asset_size_binding')
            paths[relative] = item
        if assets['bytes'] != sum(record['bytes'] for record in files.values()):
            raise AuditFailure('asset_totals_binding')
        inventory = inventory_metadata(runtime / 'uploads')
        if set(inventory) != set(paths):
            raise AuditFailure('upload_file_allowlist')
        return manifest, assets, paths
    except AuditFailure:
        raise
    except (ValueError, OSError, TypeError, KeyError):
        raise AuditFailure('snapshot_guard') from None


def inventory_metadata(root):
    """All upload file stat metadata; no asset content reads or hash claims."""
    _ordinary(root, directory=True, private=True)
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            _ordinary(Path(directory) / name, directory=True, private=True)
        for name in files:
            item = _ordinary(Path(directory) / name, private=True)
            info = item.stat()
            result[item.relative_to(root).as_posix()] = {
                'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns,
                'mode': stat.S_IMODE(info.st_mode), 'device': info.st_dev, 'inode': info.st_ino,
            }
    return result


def validate_binary(path, name):
    try:
        path = _ordinary(Path(path))
        if path.name != name or not os.access(path, os.X_OK):
            raise AuditFailure('invalid_probe_binary')
        return path
    except OSError:
        raise AuditFailure('invalid_probe_binary') from None


def bounded_process(args, timeout=PROBE_TIMEOUT, max_stdout=MAX_STDOUT, max_stderr=MAX_STDERR):
    """Drain bounded pipes; kill/reap a child process group on every failure."""
    output, counts = bytearray(), {'stdout': 0, 'stderr': 0}
    deadline = time.monotonic() + timeout
    process, completed = None, False
    try:
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True,
                                   env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C'})
        with selectors.DefaultSelector() as selector:
            for pipe, name in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AuditFailure('probe_timeout')
                for key, _ in selector.select(min(remaining, .1)):
                    block = os.read(key.fileobj.fileno(), 8192)
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    name = key.data
                    counts[name] += len(block)
                    if counts[name] > (max_stdout if name == 'stdout' else max_stderr):
                        raise AuditFailure('probe_output_limit')
                    if name == 'stdout':
                        output.extend(block)
        try:
            code = process.wait(timeout=max(.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise AuditFailure('probe_timeout') from None
        if code != 0:
            raise AuditFailure('probe_exit')
        completed = True
        return bytes(output)
    except OSError:
        raise AuditFailure('probe_start') from None
    finally:
        if process is not None:
            # Reap even on output-limit/timeout; raw child diagnostics are discarded.
            if not completed or process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            for pipe in (process.stdout, process.stderr):
                pipe.close()


def mp4_atoms(path):
    """Seek atom headers plus dref flags, never mdat payload or the full video.

    Covers ISO MOV/MP4 moov/trak/mdia/minf/dinf/dref paths. It is not a general
    container security validator. Probe disables MOV drefs independently.
    """
    total, budget, atoms, references = path.stat().st_size, 0, 0, 0
    top = []
    with path.open('rb') as source:
        def read_at(offset, size):
            nonlocal budget
            budget += size
            if budget > MAX_HEADER_BYTES:
                raise AuditFailure('mp4_header_limit')
            source.seek(offset)
            data = source.read(size)
            if len(data) != size:
                raise AuditFailure('mp4_truncated')
            return data

        def atom(offset, end):
            nonlocal atoms
            atoms += 1
            if atoms > MAX_ATOMS or end - offset < 8:
                raise AuditFailure('mp4_atom_limit' if atoms > MAX_ATOMS else 'mp4_truncated')
            size, kind = struct.unpack('>I4s', read_at(offset, 8))
            header = 8
            if size == 1:
                if end - offset < 16:
                    raise AuditFailure('mp4_truncated')
                size = struct.unpack('>Q', read_at(offset + 8, 8))[0]
                header = 16
            elif size == 0:
                size = end - offset
            if kind == b'uuid':
                header += 16
            if size < header or size > end - offset:
                raise AuditFailure('mp4_invalid_size')
            return kind, offset + header, offset + size

        def walk(start, end, depth=0):
            nonlocal references
            if depth > 8:
                raise AuditFailure('mp4_depth_limit')
            offset = start
            while offset < end:
                kind, payload, next_offset = atom(offset, end)
                if depth == 0:
                    top.append((kind, offset))
                if kind in {b'moov', b'trak', b'mdia', b'minf', b'dinf'}:
                    walk(payload, next_offset, depth + 1)
                elif kind == b'dref':
                    if next_offset - payload < 8:
                        raise AuditFailure('mp4_invalid_dref')
                    full, count = struct.unpack('>II', read_at(payload, 8))
                    if full != 0 or count > MAX_ATOMS:
                        raise AuditFailure('mp4_invalid_dref')
                    entry = payload + 8
                    for _ in range(count):
                        entry_kind, body, entry_end = atom(entry, next_offset)
                        if (entry_kind not in {b'url ', b'urn '} or entry_end - body != 4
                                or read_at(body, 4) != b'\x00\x00\x00\x01'):
                            raise AuditFailure('mp4_external_dref')
                        references += 1
                        entry = entry_end
                    if entry != next_offset:
                        raise AuditFailure('mp4_invalid_dref')
                offset = next_offset
        walk(0, total)
    moov = [offset for kind, offset in top if kind == b'moov']
    mdat = [offset for kind, offset in top if kind == b'mdat']
    if len(moov) != 1 or not mdat:
        raise AuditFailure('mp4_required_atoms')
    return {'layout': 'moov_before_mdat' if moov[0] < mdat[0] else 'moov_after_mdat',
            'fragmented': any(kind == b'moof' for kind, _ in top),
            'top_level_atoms': len(top), 'header_bytes_read': budget,
            'self_contained_data_references': references}


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def _label(value):
    # Codec/profile labels only; never arbitrary tags, descriptions or diagnostics.
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_. ()-]{1,64}', value) else None


def probe_mp4(path, ffprobe):
    container = mp4_atoms(path)
    entries = ('format=duration,format_name:stream=codec_type,codec_name,profile,width,height,'
               'pix_fmt,duration,r_frame_rate,avg_frame_rate,channels,sample_rate')
    data = bounded_process([str(ffprobe), '-v', 'error', '-protocol_whitelist', 'file', '-f', 'mov',
                            '-enable_drefs', '0', '-use_absolute_path', '0', '-show_entries', entries,
                            '-of', 'json', '-i', str(path)])
    try:
        raw = json.loads(data)
        streams = raw['streams']
        if not isinstance(streams, list) or not 1 <= len(streams) <= 64:
            raise AuditFailure('mp4_invalid_probe')
        result = []
        for stream in streams:
            if not isinstance(stream, dict) or stream.get('codec_type') not in {'video', 'audio', 'subtitle', 'data', 'attachment'}:
                raise AuditFailure('mp4_invalid_probe')
            item = {'codec_type': stream['codec_type']}
            for key in ('codec_name', 'profile', 'pix_fmt'):
                item[key] = _label(stream.get(key))
            for key in ('width', 'height', 'channels', 'sample_rate'):
                value = stream.get(key)
                if (stream['codec_type'] == 'video' and key in {'width', 'height'} and key in stream
                        and (type(value) is not int or not 1 <= value <= 1000000)):
                    raise AuditFailure('mp4_invalid_probe')
                item[key] = int(value) if str(value).isdigit() and 0 <= int(value) <= 1000000 else None
            item['duration_seconds'] = _number(stream.get('duration'))
            for key in ('r_frame_rate', 'avg_frame_rate'):
                value = stream.get(key)
                item[key] = value if isinstance(value, str) and re.fullmatch(r'\d{1,10}/\d{1,10}', value) else None
            result.append(item)
        if not any(stream['codec_type'] == 'video' for stream in result):
            raise AuditFailure('mp4_no_video')
        duration = _number(raw.get('format', {}).get('duration'))
        if duration is None:
            duration = max((stream['duration_seconds'] for stream in result
                            if stream['duration_seconds'] is not None), default=None)
        return {'container': container, 'streams': result, 'duration_seconds': duration}
    except (ValueError, TypeError, KeyError, AttributeError):
        raise AuditFailure('mp4_invalid_probe') from None


def probe_pdf(path, pdfinfo):
    data = bounded_process([str(pdfinfo), '-enc', 'UTF-8', str(path)])
    try:
        text = data.decode('utf-8', errors='strict')
        pages = re.findall(r'^Pages:\s+(\d+)\s*$', text, re.M)
        encrypted = re.findall(r'^Encrypted:\s+(yes|no)\b.*$', text, re.M)
        version = re.findall(r'^PDF version:\s+(\d\.\d)\s*$', text, re.M)
        if len(pages) != 1 or int(pages[0]) < 1 or len(encrypted) != 1 or len(version) != 1:
            raise AuditFailure('pdf_invalid_probe')
        return {'pages': int(pages[0]), 'encrypted': encrypted[0] == 'yes', 'pdf_version': version[0]}
    except UnicodeError:
        raise AuditFailure('pdf_invalid_probe') from None


def inspect_markdown(path):
    if path.stat().st_size > MAX_MARKDOWN:
        raise AuditFailure('markdown_size_limit')
    with path.open('rb') as source:
        data = source.read(MAX_MARKDOWN + 1)
    if len(data) > MAX_MARKDOWN:
        raise AuditFailure('markdown_size_limit')
    if b'\0' in data:
        raise AuditFailure('markdown_nul')
    try:
        text = data.decode('utf-8-sig', errors='strict')
    except UnicodeError:
        raise AuditFailure('markdown_utf8') from None
    return {'bytes': len(data), 'lines': len(text.splitlines()),
            'headings': len(re.findall(r'^ {0,3}#{1,6}(?:\s|$)', text, re.M)),
            'utf8_bom': data.startswith(b'\xef\xbb\xbf'),
            'newline_counts': {'crlf': data.count(b'\r\n'),
                               'lf': data.count(b'\n') - data.count(b'\r\n'),
                               'cr': data.count(b'\r') - data.count(b'\r\n')}}


def _video_features(record):
    meta = record['metadata']
    streams = meta['streams']
    features = {'layout:' + meta['container']['layout']}
    for stream in streams:
        if stream['codec_type'] == 'video':
            features.add('codec:' + str(stream.get('codec_name')))
        elif stream['codec_type'] == 'audio':
            features.add('audio:' + str(stream.get('codec_name')) + '/' + str(stream.get('channels')))
    if not any(stream['codec_type'] == 'audio' for stream in streams):
        features.add('audio:none')
    return features


def select_representatives(records):
    """Deterministic bounded coverage first, then long/large and page extremes."""
    valid = sorted((record for record in records if record['status'] == 'passed'), key=lambda r: r['asset_id'])
    selected = []

    def add(record, reason, limit, kind):
        old = next((item for item in selected if item['asset_id'] == record['asset_id']), None)
        if old:
            old['reasons'] = sorted(set(old['reasons'] + [reason]))
        elif sum(item['kind'] == kind for item in selected) < limit:
            selected.append({'asset_id': record['asset_id'], 'kind': kind, 'reasons': [reason]})

    videos = [record for record in valid if record['kind'] == 'mp4']
    remaining = set().union(*(_video_features(record) for record in videos)) if videos else set()
    # Reserve two slots for long/large assets while prioritizing varied formats.
    candidates = list(videos)
    for _ in range(3):
        if not candidates or not remaining:
            break
        best = min(candidates, key=lambda r: (-len(_video_features(r) & remaining), r['asset_id']))
        covered = _video_features(best) & remaining
        if not covered:
            break
        for reason in sorted(covered):
            add(best, reason, 5, 'mp4')
        remaining -= covered
        candidates.remove(best)
    if videos:
        longest = min(videos, key=lambda r: (-(r['metadata'].get('duration_seconds') or 0), r['asset_id']))
        largest = min(videos, key=lambda r: (-r['bytes'], r['asset_id']))
        add(longest, 'longest_duration', 5, 'mp4')
        add(largest, 'largest_bytes', 5, 'mp4')
    pdfs = [record for record in valid if record['kind'] == 'pdf']
    if pdfs:
        for record, reason in ((min(pdfs, key=lambda r: (-r['metadata']['pages'], r['asset_id'])), 'most_pages'),
                               (min(pdfs, key=lambda r: (-r['bytes'], r['asset_id'])), 'largest_bytes'),
                               (min(pdfs, key=lambda r: (r['metadata']['pages'], r['asset_id'])), 'fewest_pages'),
                               (min(pdfs, key=lambda r: (r['bytes'], r['asset_id'])), 'smallest_bytes')):
            add(record, reason, 2, 'pdf')
    markdown = [record for record in valid if record['kind'] == 'md']
    if markdown:
        add(min(markdown, key=lambda r: (-r['metadata']['lines'], -r['bytes'], r['asset_id'])), 'most_lines', 1, 'md')
    return selected


def _range(values):
    values = [value for value in values if value is not None]
    return {'min': min(values), 'max': max(values)} if values else {'min': None, 'max': None}


def _statistics(records):
    groups = {kind: [r for r in records if r['kind'] == kind and r['status'] == 'passed']
              for kind in ('mp4', 'pdf', 'md')}
    videos, pdfs, markdown = (groups[kind] for kind in ('mp4', 'pdf', 'md'))
    video_streams = [s for r in videos for s in r['metadata']['streams'] if s['codec_type'] == 'video']
    audio_groups = Counter()
    for record in videos:
        labels = sorted(str(s['codec_name']) + '/' + str(s['channels'])
                        for s in record['metadata']['streams'] if s['codec_type'] == 'audio')
        audio_groups['+'.join(labels) if labels else 'none'] += 1
    return {
        'mp4': {'video_codecs': dict(Counter(s['codec_name'] or 'unknown' for s in video_streams)),
                'video_profiles': dict(Counter(s['profile'] or 'unknown' for s in video_streams)),
                'audio_groups': dict(audio_groups),
                'layouts': dict(Counter(r['metadata']['container']['layout'] for r in videos)),
                'duration_seconds': _range(r['metadata']['duration_seconds'] for r in videos),
                'bytes': _range(r['bytes'] for r in videos)},
        'pdf': {'pages': _range(r['metadata']['pages'] for r in pdfs),
                'bytes': _range(r['bytes'] for r in pdfs),
                'encrypted': sum(r['metadata']['encrypted'] for r in pdfs),
                'versions': dict(Counter(r['metadata']['pdf_version'] for r in pdfs))},
        'md': {'lines': _range(r['metadata']['lines'] for r in markdown),
               'headings': _range(r['metadata']['headings'] for r in markdown),
               'bytes': _range(r['bytes'] for r in markdown),
               'utf8_bom': sum(r['metadata']['utf8_bom'] for r in markdown),
               'newline_counts': {key: sum(r['metadata']['newline_counts'][key] for r in markdown)
                                  for key in ('crlf', 'lf', 'cr')}},
    }


def _binding(runtime, manifest):
    return {'manifest_sha256': sha256(runtime / 'snapshot-manifest.json'),
            'assets_result_sha256': sha256(runtime / 'assets-result.json'),
            'schema_policy_sha256': sha256(SCHEMA_PROFILE),
            'config_sha256': _digest({'private_files': manifest['private_files'], 'ports': _ports(runtime)}),
            'source_sha256': manifest['source_sha256'],
            'source_manifest_sha256': manifest['source_manifest_sha256']}


def _inventory_summary(inventory):
    return {'file_count': len(inventory), 'bytes': sum(item['bytes'] for item in inventory.values()),
            'stat_inventory_sha256': _digest(inventory), 'scope': 'all_upload_file_stat_metadata_only'}


def _new_report_directory(runtime):
    reports = runtime / 'reports'
    if reports.exists() or reports.is_symlink():
        _ordinary(reports, directory=True, private=True)
    else:
        reports.mkdir(mode=0o700)
    target = reports / ('media-audit-' + uuid4().hex)
    target.mkdir(mode=0o700)
    return target


def audit(runtime, ffprobe, pdfinfo):
    """Return a shareable aggregate; full opaque records stay in mode-600 JSON."""
    runtime = Path(runtime)
    manifest, assets, paths = validate_snapshot(runtime)
    ffprobe, pdfinfo = validate_binary(ffprobe, 'ffprobe'), validate_binary(pdfinfo, 'pdfinfo')
    before = _inventory_summary(inventory_metadata(runtime / 'uploads'))
    binding = _binding(runtime, manifest)
    tool_binding = {'audit_module_sha256': sha256(Path(__file__).resolve()),
                    'audit_cli_sha256': sha256(Path(__file__).with_name('audit-production-media.py')),
                    'ffprobe_sha256': sha256(ffprobe), 'pdfinfo_sha256': sha256(pdfinfo)}
    report_dir = _new_report_directory(runtime)
    records, after, after_binding, terminal_error = [], None, None, None
    try:
        for relative, path in sorted(paths.items()):
            extension = path.suffix.lower().lstrip('.')
            record = {'asset_id': hashlib.sha256(relative.encode('utf-8')).hexdigest(),
                      'kind': extension if extension in {'mp4', 'pdf', 'md', 'jpg', 'png'} else 'unsupported',
                      'bytes': assets['files'][relative]['bytes'],
                      'source_sha256': assets['files'][relative]['sha256'], 'status': 'passed'}
            try:
                if extension == 'mp4':
                    record['metadata'] = probe_mp4(path, ffprobe)
                elif extension == 'pdf':
                    record['metadata'] = probe_pdf(path, pdfinfo)
                elif extension == 'md':
                    record['metadata'] = inspect_markdown(path)
                elif extension in {'jpg', 'png'}:
                    record['status'] = 'inventory_only'
                else:
                    raise AuditFailure('unsupported_asset_type')
            except (AuditFailure, OSError) as error:
                record['status'] = 'failed'
                record['error_code'] = error.code if isinstance(error, AuditFailure) else 'asset_read'
            records.append(record)
    finally:
        # Always recheck bindings and the complete upload stat inventory after probes.
        try:
            final_manifest, _, _ = validate_snapshot(runtime)
            after = _inventory_summary(inventory_metadata(runtime / 'uploads'))
            after_binding = _binding(runtime, final_manifest)
        except (AuditFailure, OSError) as error:
            terminal_error = error.code if isinstance(error, AuditFailure) else 'snapshot_after_read'
    unchanged = terminal_error is None and before == after and binding == after_binding
    if not unchanged and terminal_error is None:
        terminal_error = 'snapshot_changed'
    failures = Counter(r['error_code'] for r in records if r['status'] == 'failed')
    if terminal_error:
        failures[terminal_error] += 1
    representatives = select_representatives(records)
    safety = {'before': before, 'after': after, 'binding_after': after_binding,
              'unchanged': unchanged, 'after_error_code': terminal_error,
              'full_asset_content_hash_performed': False,
              'selected_content_hash_scope': 'source_manifest_claim_only'}
    summary = {'format': REPORT_FORMAT, 'kind': 'teachingopen-private-media-audit-summary',
               'completed': True, 'passed': not failures,
               'counts': {'assets': len(records), 'media_checked': sum(r['kind'] in {'mp4', 'pdf', 'md'} for r in records),
                          'passed': sum(r['status'] == 'passed' for r in records),
                          'failed': sum(r['status'] == 'failed' for r in records),
                          'inventory_only': sum(r['status'] == 'inventory_only' for r in records)},
               'extensions': dict(Counter(r['kind'] for r in records)), 'failures': dict(failures),
               'statistics': _statistics(records), 'binding': binding, 'tool_binding': tool_binding,
               'safety': safety, 'selection_counts': dict(Counter(r['kind'] for r in representatives)),
               'report_directory': report_dir.relative_to(runtime).as_posix()}
    full = {'format': REPORT_FORMAT, 'kind': 'teachingopen-private-media-audit',
            'summary': summary, 'records': records, 'representatives': representatives,
            'limitations': ['metadata parsing only; no full decoding, rendering or browser playback/seeking',
                            'jpg/png inventory only; image decoding untested',
                            'Markdown headings count ATX-shaped lines; no complete Markdown syntax parsing',
                            'dref inspection covers standard moov/trak/mdia/minf/dinf paths only',
                            'asset source_sha256 is a bound acquisition claim; asset content was not fully rehashed']}
    private_write(report_dir / 'report.json', json.dumps(full, sort_keys=True, indent=2) + '\n')
    private_write(report_dir / 'summary.json', json.dumps(summary, sort_keys=True, indent=2) + '\n')
    return summary
