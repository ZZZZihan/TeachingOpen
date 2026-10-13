#!/usr/bin/env python3
"""Validate a local rules export against an immutable candidate JAR, without a database connection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def preflight(args):
    source = Path(__file__).with_name('RuleConfigurationPreflight.java')
    exported, jar, output = args.input.resolve(), args.jar.resolve(), args.output.resolve()
    if output.exists() or output in (exported, jar, source.resolve()):
        raise ValueError('Output must be a new report file; existing evidence is never replaced')
    if not exported.is_file() or exported.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('Input must be a local JSON export no larger than 20 MiB')
    if not jar.is_file():
        raise ValueError('Candidate JAR does not exist')
    java_home = args.java_home or os.environ.get('JAVA_HOME')
    javac = str(Path(java_home) / 'bin/javac') if java_home else shutil.which('javac')
    if not javac or not Path(javac).is_file():
        raise ValueError('Set --java-home or JAVA_HOME to a local JDK with javac')
    java = str(Path(javac).resolve().with_name('java'))
    input_hash, jar_hash = sha256(exported), sha256(jar)
    with tempfile.TemporaryDirectory(prefix='teachingopen-rule-preflight-') as directory:
        work = Path(directory)
        libraries, classes = work / 'lib', work / 'classes'
        libraries.mkdir(); classes.mkdir()
        with zipfile.ZipFile(jar) as archive:
            for entry in archive.infolist():
                name = entry.filename
                if name.startswith('BOOT-INF/lib/') and name.endswith('.jar'):
                    with (libraries / Path(name).name).open('xb') as target:
                        target.write(archive.read(entry))
                elif name == 'BOOT-INF/classes/org/jeecg/modules/system/service/CheckRuleValidator.class':
                    target = classes / name[len('BOOT-INF/classes/'):]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(entry))
        if not (classes / 'org/jeecg/modules/system/service/CheckRuleValidator.class').is_file():
            raise ValueError('Candidate JAR is missing CheckRuleValidator; use the patched packaged JAR')
        classpath = str(classes) + os.pathsep + str(libraries / '*')
        # Do not inherit JVM agents/options from the launching shell.
        environment = {key: value for key, value in os.environ.items()
                       if key not in ('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'CLASSPATH')}
        steps = [
            [javac, '-encoding', 'UTF-8', '-proc:none', '-cp', classpath, '-d', str(classes), str(source)],
            [java, '-cp', classpath, 'RuleConfigurationPreflight', str(exported), str(work / 'result.json')],
        ]
        for command in steps:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env=environment, timeout=120, check=False)
            if result.returncode != 0:
                # Exceptions may contain private exported configuration: never echo subprocess logs.
                raise ValueError('Offline validator failed; verify the JSON export format, candidate JAR and JDK')
        report = json.loads((work / 'result.json').read_text(encoding='utf-8'))
    if sha256(exported) != input_hash or sha256(jar) != jar_hash:
        raise ValueError('Input or candidate changed during preflight; no report accepted')
    report.update({
        'scope': 'offline-local-export', 'production_connected': False,
        'configuration_modified': False, 'handlers_executed': False, 'regex_values_matched': False,
        'input_sha256': input_hash, 'jar_sha256': jar_hash,
        'verifier_sha256': sha256(Path(__file__)), 'helper_sha256': sha256(source),
        'not_verified': [
            'Export completeness and correspondence to the intended deployment database',
            'Existence and state of parentId/pid records referenced by fill parameters',
            'Live account authorization, generated codes, imports, concurrency and capacity',
            'Application release acceptance or independent security review',
        ],
    })
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Local JSON with fill_rules and check_rules arrays')
    parser.add_argument('--jar', type=Path, required=True, help='Fixed Spring Boot candidate JAR')
    parser.add_argument('--output', type=Path, required=True, help='New sanitized JSON report; never overwritten')
    parser.add_argument('--java-home', type=Path, help='Local JDK home (defaults to JAVA_HOME or PATH)')
    args = parser.parse_args()
    try:
        report = preflight(args)
    except (ValueError, OSError, subprocess.TimeoutExpired, zipfile.BadZipFile) as failure:
        parser.exit(2, str(failure) + '\n')
    print(json.dumps({'compatible': report['compatible'], 'checked_rows': report['checked_rows'],
                      'incompatible_rows': report['incompatible_rows'], 'scope': report['scope']}))
    return 0 if report['compatible'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
