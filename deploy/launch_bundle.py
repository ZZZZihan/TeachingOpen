#!/usr/bin/env python3
"""Build, compose and verify a private portable launch bundle; never deploy."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('_launch_paths', Path(__file__).with_name('candidate_release.py'))
paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paths)

FORMAT = 1
JAR = 'api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar'
MIGRATIONS = ['api/db/phone-profile-registration.sql', 'api/db/enable-phone-registration.sql']
MIGRATION_NAMES = ['01-phone-profile-registration.sql', '02-enable-phone-registration.sql']
SUPPORT = ['deploy/launch_bundle.py', 'deploy/candidate_release.py', 'deploy/LAUNCH_BUNDLE.md',
           'deploy/application-launch.properties.template', 'api/dev/prepare_launch_data.py',
           'deploy/registration_upgrade.py']


def git(source, *args):
    result = subprocess.run(['git', '-C', str(source), *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Cannot read candidate Git state')
    return result.stdout.strip()


def receipt(path):
    path = paths.checked_path(path)
    return {'bytes': path.stat().st_size, 'sha256': paths.sha256(path)}


def inventory_digest(value):
    import hashlib
    return hashlib.sha256(paths.json_bytes(value).encode()).hexdigest()


def private_tree(root):
    paths.checked_path(root, 'directory')
    for parent, dirs, files in os.walk(root, followlinks=False):
        if stat.S_IMODE(paths.checked_path(parent, 'directory').stat().st_mode) != 0o700:
            raise ValueError('Private directory must be 0700')
        for name in dirs:
            paths.checked_path(Path(parent) / name, 'directory')
        for name in files:
            if stat.S_IMODE(paths.checked_path(Path(parent) / name).stat().st_mode) != 0o600:
                raise ValueError('Private file must be 0600')


def new_private_output(output, inputs):
    output = paths.checked_path(output, 'directory', missing=True)
    for item in inputs:
        item = paths.checked_path(item, 'directory')
        if output == item or item in output.parents or output in item.parents:
            raise ValueError('Output and input directories must be separate')
    output.mkdir(mode=0o700)
    return output


def copy_file(root, name, origin):
    write_file(root, name, paths.checked_path(origin).read_bytes())


def write_file(root, name, value):
    # mkdir(parents=True, mode=0700) applies mode only to the final directory.
    # Create each ancestor explicitly so nested tools/resources remain private.
    relative = Path(paths.relative_path(name))
    parent = root
    for part in relative.parts[:-1]:
        parent = parent / part
        if not parent.exists():
            parent.mkdir(mode=0o700)
        if stat.S_IMODE(paths.checked_path(parent, 'directory').stat().st_mode) != 0o700:
            raise ValueError('Existing private directory must be 0700')
    paths.write_file(root, name, value)


def copy_tree(root, prefix, origin):
    for name in paths.file_inventory(origin):
        copy_file(root, prefix + '/' + name, origin / name)


def compiled_inputs(source):
    """Freeze build-relevant tracked inputs, with actual source bytes checked."""
    tracked = git(source, 'ls-files', '-z').split('\0')
    selected = []
    for name in tracked:
        if not name:
            continue
        if name.startswith('api/') and (name.endswith('/pom.xml') or '/src/main/' in name):
            selected.append(name)
        elif name.startswith('web/') and not name.startswith(('web/tests/', 'web/nginx/')):
            selected.append(name)
    result = {'api': {}, 'web': {}}
    for name in selected:
        result[name.split('/')[0]][name] = receipt(source / name)
    if not all(result.values()):
        raise ValueError('Missing backend or frontend build inputs')
    # Ignored/untracked files inside source/public would otherwise bypass Git provenance.
    source_directories = {'web/src', 'web/public'}
    source_directories.update(name.split('/src/main/')[0] + '/src/main'
                              for name in selected if name.startswith('api/') and '/src/main/' in name)
    source_directories.update(path.relative_to(source).as_posix()
                              for path in (source / 'api').glob('*/src/main'))
    for dirname in sorted(source_directories):
        expected = {name for name in selected if name.startswith(dirname + '/')}
        actual = {dirname + '/' + name for name in paths.file_inventory(source / dirname)}
        if expected != actual:
            raise ValueError('Build source directory has untracked or missing files')
    for path in (source / 'web').glob('.env*'):
        if 'web/' + path.name not in selected:
            raise ValueError('Untracked frontend environment file is forbidden')
    return result


def run_logged(command, cwd, logfile, env=None):
    with logfile.open('xb') as stream:
        logfile.chmod(0o600)
        result = subprocess.run(command, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise ValueError('Build failed; inspect the private build log')


def tool_version(command, env=None):
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    if result.returncode:
        raise ValueError('Cannot query build tool version')
    return (result.stdout + result.stderr).strip().splitlines()[0]


def build(args):
    source = paths.checked_path(args.source, 'directory')
    commit = paths.git_commit(source)
    before = compiled_inputs(source)
    java_home = paths.checked_path(args.java_home, 'directory')
    java = paths.checked_path(java_home / 'bin/java')
    mvn = paths.checked_path(args.maven)
    cache = paths.checked_path(args.maven_cache, 'directory')
    version = tool_version([str(java), '-version'])
    if not re.search(r'"1\.8\.', version):
        raise ValueError('Expected JDK 8')
    npm = shutil.which('npm')
    node = shutil.which('node')
    if not npm or not node or not (source / 'web/node_modules').is_dir():
        raise ValueError('Existing Node, npm and project dependencies are required')
    environment = dict(os.environ, JAVA_HOME=str(java_home))
    versions = {'java': version, 'maven': tool_version([str(mvn), '--version'], environment),
                'node': tool_version([node, '--version']), 'npm': tool_version([npm, '--version'])}
    output = new_private_output(args.output, [source])
    write_file(output, 'build-inputs.json', paths.json_bytes({'source_commit': commit, 'compiled_inputs': before}))
    commands = {
        'api': [str(mvn), '-B', '-s', 'dev/maven-settings.xml',
                '-Dmaven.repo.local=' + str(cache), '-DskipTests', 'clean', 'package'],
        'web': [npm, 'run', 'build'],
    }
    run_logged(commands['api'], source / 'api', output / 'backend-build.log', environment)
    run_logged(commands['web'], source / 'web', output / 'frontend-build.log')
    if paths.git_commit(source) != commit or compiled_inputs(source) != before:
        raise ValueError('Candidate changed during build')
    copy_file(output, 'app/app.jar', source / JAR)
    copy_tree(output, 'web/dist', source / 'web/dist')
    artifacts = paths.file_inventory(output / 'app')
    dist = paths.file_inventory(output / 'web/dist')
    value = {
        'format': FORMAT, 'kind': 'teachingopen-launch-build', 'complete': True,
        'built_at_utc': datetime.now(timezone.utc).isoformat(), 'source_commit': commit,
        'compiled_inputs': before,
        'compiled_input_sha256': {key: inventory_digest(val) for key, val in before.items()},
        'tools': versions,
        'commands': {'api': 'mvn -B -s dev/maven-settings.xml -Dmaven.repo.local=<private-cache> -DskipTests clean package',
                     'web': 'npm run build'},
        'tests_run_by_build': False, 'services_started': False,
        'jar': artifacts['app.jar'], 'dist': dist,
        'logs': {name: receipt(output / name) for name in ['backend-build.log', 'frontend-build.log']},
    }
    write_file(output, 'build.json', paths.json_bytes(value))
    private_tree(output)
    return build_summary(output, value)


def verify_build(directory, source=None):
    directory = paths.checked_path(directory, 'directory')
    private_tree(directory)
    value = paths.read_json(directory / 'build.json')
    if value.get('format') != FORMAT or value.get('kind') != 'teachingopen-launch-build' or value.get('complete') is not True:
        raise ValueError('Incomplete build receipt')
    if receipt(directory / 'app/app.jar') != value.get('jar'):
        raise ValueError('JAR differs from build receipt')
    if paths.file_inventory(directory / 'web/dist') != paths.checked_inventory(value.get('dist')):
        raise ValueError('Frontend differs from build receipt')
    for name, expected in value['logs'].items():
        if name not in ['backend-build.log', 'frontend-build.log'] or receipt(directory / name) != expected:
            raise ValueError('Build log differs from receipt')
    if source is not None and compiled_inputs(source) != value['compiled_inputs']:
        raise ValueError('Final candidate build inputs differ; rebuild once after the change')
    for key, val in value['compiled_inputs'].items():
        if key not in ('api', 'web') or inventory_digest(val) != value['compiled_input_sha256'][key]:
            raise ValueError('Compiled input receipt differs')
    return value


def build_summary(directory, value):
    return {'directory': str(directory), 'source_commit': value['source_commit'],
            'build_receipt_sha256': paths.sha256(directory / 'build.json'),
            'jar_sha256': value['jar']['sha256'], 'dist_files': len(value['dist']),
            'dist_inventory_sha256': inventory_digest(value['dist']),
            'tests_run_by_build': value['tests_run_by_build'], 'services_started': False}


def data_verify(source, package):
    result = subprocess.run([sys.executable, str(source / 'api/dev/prepare_launch_data.py'),
                             'verify', '--package', str(package)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Clean launch data verification failed')
    return paths.read_json(package / 'manifest.json')


def upgrade_manifest(source):
    # Execute only the source explicitly selected as a trusted clean candidate.
    specification = importlib.util.spec_from_file_location('_launch_upgrade', source / 'deploy/registration_upgrade.py')
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    value = module.migration_manifest(source)
    if [tuple(row) for row in module.MIGRATIONS] != list(zip(MIGRATIONS, MIGRATION_NAMES)):
        raise ValueError('Upgrade runner migration contract differs')
    return value


def create(args):
    source = paths.checked_path(args.source, 'directory')
    commit = paths.git_commit(source)
    required = SUPPORT + MIGRATIONS + ['api/Dockerfile.db', 'web/nginx/default.conf']
    for name in required:
        if git(source, 'ls-files', '--error-unmatch', name) != name:
            raise ValueError('Required release source file is not tracked')
    build_dir = paths.checked_path(args.build, 'directory')
    data_dir = paths.checked_path(args.data_package, 'directory')
    built = verify_build(build_dir, source)
    data = data_verify(source, data_dir)
    output = new_private_output(args.output, [source, build_dir, data_dir])
    copy_file(output, 'app/app.jar', build_dir / 'app/app.jar')
    copy_tree(output, 'web/dist', build_dir / 'web/dist')
    copy_file(output, 'web/nginx.conf', source / 'web/nginx/default.conf')
    copy_tree(output, 'initial-data', data_dir)
    for name, frozen_name in zip(MIGRATIONS, MIGRATION_NAMES):
        copy_file(output, 'migrations/' + frozen_name, source / name)
    copy_file(output, 'migrations/registration_upgrade.py', source / 'deploy/registration_upgrade.py')
    write_file(output, 'migrations/migration-manifest.json', paths.json_bytes(upgrade_manifest(source)))
    copy_file(output, 'migrations/Dockerfile.db.reference', source / 'api/Dockerfile.db')
    copy_file(output, 'config/application-launch.properties.template', source / 'deploy/application-launch.properties.template')
    copy_file(output, 'RUNBOOK.md', source / 'deploy/LAUNCH_BUNDLE.md')
    for name in ['build.json', 'backend-build.log', 'frontend-build.log']:
        copy_file(output, 'evidence/' + name, build_dir / name)
    # Freeze verifiers as source for review; no file is executed automatically by create/verify.
    for name in SUPPORT:
        copy_file(output, 'tools/' + name, source / name)
    immutable = paths.file_inventory(output)
    value = {
        'format': FORMAT, 'kind': 'teachingopen-private-launch-bundle', 'complete': True,
        'source_commit': commit, 'build_source_commit': built['source_commit'],
        'compiled_input_sha256': built['compiled_input_sha256'],
        'build_receipt_sha256': paths.sha256(build_dir / 'build.json'),
        'jar': built['jar'], 'dist_files': len(built['dist']),
        'dist_inventory_sha256': inventory_digest(built['dist']),
        'initial_data_manifest_sha256': paths.sha256(data_dir / 'manifest.json'),
        'initial_data_source_commit': data['source_commit'],
        'initial_data_counts': data['counts']['retained'], 'course_assets': data['assets'],
        'registration_upgrade_manifest_sha256': paths.sha256(output / 'migrations/migration-manifest.json'),
        'migration_order_new_database': ['initial-data/mysql/seed.sql'] + ['migrations/' + name for name in MIGRATION_NAMES],
        'migration_order_existing_database': ['migrations/' + name for name in MIGRATION_NAMES],
        'source_files': {name: receipt(source / name) for name in required},
        'files': immutable, 'services_started': False,
        'runtime_data_checked': False, 'cloud_deployed': False, 'human_accepted': False,
        'target': {'architecture': None, 'domain': None, 'provider': None,
                   'runtime_images': None, 'tls': None, 'secrets_configured': False},
    }
    if paths.git_commit(source) != commit or compiled_inputs(source) != built['compiled_inputs']:
        raise ValueError('Source changed during bundle creation')
    write_file(output, 'manifest.json', paths.json_bytes(value))
    return verify_bundle(output, expected_manifest=None, source=source)


def verify_bundle(bundle, expected_manifest=None, source=None):
    bundle = paths.checked_path(bundle, 'directory')
    private_tree(bundle)
    manifest_hash = paths.sha256(bundle / 'manifest.json')
    if expected_manifest:
        paths.check_digest(expected_manifest)
        if manifest_hash != expected_manifest:
            raise ValueError('Bundle manifest differs from independently frozen SHA256')
    value = paths.read_json(bundle / 'manifest.json')
    if value.get('format') != FORMAT or value.get('kind') != 'teachingopen-private-launch-bundle' or value.get('complete') is not True:
        raise ValueError('Incomplete launch bundle')
    for field in ['source_commit', 'build_source_commit', 'initial_data_source_commit']:
        if not isinstance(value.get(field), str) or not re.fullmatch('[0-9a-f]{40}', value[field]):
            raise ValueError('Invalid source commit receipt')
    if any(value.get(field) is not False for field in ['services_started', 'runtime_data_checked', 'cloud_deployed', 'human_accepted']):
        raise ValueError('Offline manifest cannot claim runtime or delivery acceptance')
    actual = paths.file_inventory(bundle)
    actual.pop('manifest.json')
    if actual != paths.checked_inventory(value.get('files')):
        raise ValueError('Bundle file inventory differs')
    built = paths.read_json(bundle / 'evidence/build.json')
    if built.get('format') != FORMAT or built.get('kind') != 'teachingopen-launch-build' or built.get('complete') is not True:
        raise ValueError('Incomplete build provenance')
    if built['source_commit'] != value['build_source_commit'] or built['compiled_input_sha256'] != value['compiled_input_sha256']:
        raise ValueError('Build source provenance differs')
    for key, entries in built['compiled_inputs'].items():
        if key not in ('api', 'web') or inventory_digest(entries) != built['compiled_input_sha256'][key]:
            raise ValueError('Compiled input evidence differs')
    for name, expected in built['logs'].items():
        if name not in ['backend-build.log', 'frontend-build.log'] or receipt(bundle / 'evidence' / name) != expected:
            raise ValueError('Build log provenance differs')
    if receipt(bundle / 'app/app.jar') != built['jar'] or built['jar'] != value['jar']:
        raise ValueError('JAR provenance differs')
    dist = paths.file_inventory(bundle / 'web/dist')
    if dist != built['dist'] or inventory_digest(dist) != value['dist_inventory_sha256'] or len(dist) != value['dist_files']:
        raise ValueError('Frontend provenance differs')
    if paths.sha256(bundle / 'evidence/build.json') != value['build_receipt_sha256']:
        raise ValueError('Build evidence fingerprint differs')
    if paths.sha256(bundle / 'initial-data/manifest.json') != value['initial_data_manifest_sha256']:
        raise ValueError('Initial data provenance differs')
    data = paths.read_json(bundle / 'initial-data/manifest.json')
    if data['counts']['retained'] != value['initial_data_counts'] or data['assets'] != value['course_assets']:
        raise ValueError('Initial data summary differs')
    if data['source_commit'] != value['initial_data_source_commit']:
        raise ValueError('Initial data source provenance differs')
    expected_new_order = ['initial-data/mysql/seed.sql'] + ['migrations/' + name for name in MIGRATION_NAMES]
    if value['migration_order_new_database'] != expected_new_order or value['migration_order_existing_database'] != expected_new_order[1:]:
        raise ValueError('Migration order differs')
    frozen_sources = {name: 'tools/' + name for name in SUPPORT}
    frozen_sources.update({name: 'migrations/' + frozen_name for name, frozen_name in zip(MIGRATIONS, MIGRATION_NAMES)})
    frozen_sources.update({'api/Dockerfile.db': 'migrations/Dockerfile.db.reference',
                          'web/nginx/default.conf': 'web/nginx.conf'})
    if set(value['source_files']) != set(frozen_sources):
        raise ValueError('Required release source inventory differs')
    for name, copied in frozen_sources.items():
        if receipt(bundle / copied) != value['source_files'][name]:
            raise ValueError('Copied release source provenance differs')
    if receipt(bundle / 'RUNBOOK.md') != value['source_files']['deploy/LAUNCH_BUNDLE.md'] or receipt(bundle / 'config/application-launch.properties.template') != value['source_files']['deploy/application-launch.properties.template']:
        raise ValueError('Runbook or configuration template differs')
    if receipt(bundle / 'migrations/registration_upgrade.py') != value['source_files']['deploy/registration_upgrade.py']:
        raise ValueError('Upgrade runner source differs')
    if paths.sha256(bundle / 'migrations/migration-manifest.json') != value['registration_upgrade_manifest_sha256']:
        raise ValueError('Upgrade manifest fingerprint differs')
    upgrade = paths.read_json(bundle / 'migrations/migration-manifest.json')
    expected_upgrade = {'format': 1, 'kind': 'teachingopen-registration-upgrade',
                        'automatic_apply': False, 'ddl_transactional': False,
                        'initialization_order': ['schema', 'data', *MIGRATION_NAMES],
                        'existing_database_order': MIGRATION_NAMES,
                        'steps': [{'source': name, 'file': frozen_name, **value['source_files'][name]}
                                  for name, frozen_name in zip(MIGRATIONS, MIGRATION_NAMES)]}
    if upgrade != expected_upgrade:
        raise ValueError('Upgrade manifest source or order differs')
    if source is not None:
        source = paths.checked_path(source, 'directory')
        if paths.git_commit(source) != value['source_commit']:
            raise ValueError('Source commit differs')
        if compiled_inputs(source) != built['compiled_inputs']:
            raise ValueError('Source build inputs differ')
        for name, expected in value['source_files'].items():
            paths.relative_path(name)
            if receipt(source / name) != expected:
                raise ValueError('Source release input differs')
        data_verify(source, bundle / 'initial-data')
    return {'bundle': str(bundle), 'manifest_sha256': manifest_hash,
            'source_commit': value['source_commit'], 'build_source_commit': value['build_source_commit'],
            'jar_sha256': value['jar']['sha256'], 'dist_files': value['dist_files'],
            'initial_data_counts': value['initial_data_counts'],
            'asset_file_count': value['course_assets']['count'],
            'registration_upgrade_manifest_sha256': value['registration_upgrade_manifest_sha256'],
            'immutable_files': len(actual), 'permissions': 'directories 0700; files 0600',
            'source_checked': source is not None, 'services_started': False,
            'runtime_data_checked': False, 'cloud_deployed': False, 'human_accepted': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    build_parser = sub.add_parser('build')
    for flag in ['source', 'java-home', 'maven', 'maven-cache', 'output']:
        build_parser.add_argument('--' + flag, required=True)
    create_parser = sub.add_parser('create')
    for flag in ['source', 'build', 'data-package', 'output']:
        create_parser.add_argument('--' + flag, required=True)
    verify_parser = sub.add_parser('verify')
    verify_parser.add_argument('--bundle', required=True)
    verify_parser.add_argument('--manifest-sha256')
    verify_parser.add_argument('--source')
    args = parser.parse_args(argv)
    try:
        if args.action == 'build':
            result = build(args)
        elif args.action == 'create':
            result = create(args)
        else:
            result = verify_bundle(args.bundle, args.manifest_sha256, args.source)
        print(paths.json_bytes(result), end='')
        return 0
    except (ValueError, KeyError, OSError, TypeError, json.JSONDecodeError):
        # Avoid copying paths containing real resource names or SQL content into logs.
        print('Launch bundle operation failed; inputs or private evidence require inspection.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
