"""Conservative checks of the environment declarations eligible for CI reuse.

This checks local declarations, not the current contents or availability of remote
Maven repositories. Unsupported configuration makes reuse unavailable; it must
never prevent the ordinary full suite from running.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET


PYTHON = '3.12.15'
JAVA = '8.0.504+1'
NODE = '26.7.0'
NPM = '11.19.0'
ACTIONS = frozenset(('actions/checkout', 'actions/setup-node', 'actions/setup-python',
                     'actions/setup-java', 'actions/upload-artifact'))
SERVICE_IMAGES = {
    'mysql': 'mysql@sha256:7dcddc01f13bab2f15cde676d44d01f61fc9f99fe7785e86196dfc07d358ae2b',
    'redis': 'redis@sha256:46f15cf64fdef63e483dcda99e74e3d51c017b1175547b6bb874152ee2391aad',
}
POMS = ('api/pom.xml', 'api/jeecg-boot-base-common/pom.xml',
        'api/jeecg-boot-module-system/pom.xml')
NS = '{http://maven.apache.org/POM/4.0.0}'
PROPERTY = re.compile(r'\$\{([^{}]+)\}')
# These omitted versions are supplied by this exact Spring Boot parent and its
# dependency BOM. New coordinates need an explicit version or a contract update.
BOOT_PARENT = ('org.springframework.boot', 'spring-boot-starter-parent', '2.1.3.RELEASE')
MANAGED_PLUGINS = frozenset((
    ('org.apache.maven.plugins', 'maven-compiler-plugin'),
    ('org.apache.maven.plugins', 'maven-surefire-plugin'),
    ('org.apache.maven.plugins', 'maven-resources-plugin'),
    ('org.springframework.boot', 'spring-boot-maven-plugin'),
))
MANAGED_DEPENDENCIES = frozenset(
    [('org.springframework.boot', 'spring-boot-starter-' + name)
     for name in ('web', 'mail', 'test', 'aop', 'actuator', 'freemarker', 'quartz',
                  'data-redis', 'websocket')]
    + [('org.projectlombok', 'lombok'), ('org.apache.commons', 'commons-pool2')])


def require(condition, message):
    if not condition:
        raise ValueError(message)


def scalar(raw):
    """Read only the simple scalar form used in the maintained CI workflow."""
    raw = re.sub(r'\s+#.*$', '', raw).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1]
    require(re.fullmatch(r'[A-Za-z0-9_./:@+\-]+', raw) is not None,
            'Unsupported environment scalar')
    return raw


def field(lines, name, indent):
    pattern = re.compile(r' {' + str(indent) + '}' + re.escape(name) + r':\s*(.*?)\s*$')
    values = [scalar(match.group(1)) for line in lines if (match := pattern.fullmatch(line))]
    require(len(values) == 1, 'Missing or duplicate environment field: ' + name)
    return values[0]


def job_blocks(text):
    require('\t' not in text and text.splitlines().count('jobs:') == 1,
            'Unsupported workflow layout')
    lines = text.splitlines()
    start = lines.index('jobs:') + 1
    require(not any(line and not line.startswith((' ', '#')) for line in lines[start:]),
            'Unsupported root mapping after jobs')
    positions = [(i, match.group(1)) for i, line in enumerate(lines[start:], start)
                 if (match := re.fullmatch(r'  ([A-Za-z0-9_-]+):', line))]
    require(bool(positions) and len({name for _, name in positions}) == len(positions),
            'Missing or duplicate jobs')
    return {name: lines[index + 1:positions[n + 1][0] if n + 1 < len(positions) else len(lines)]
            for n, (index, name) in enumerate(positions)}


def steps(lines):
    require(lines.count('    steps:') == 1, 'Unsupported job steps')
    start = lines.index('    steps:') + 1
    positions = [i for i in range(start, len(lines)) if re.match(r'      - ', lines[i])]
    require(bool(positions), 'Missing job steps')
    return [lines[index:positions[n + 1] if n + 1 < len(positions) else len(lines)]
            for n, index in enumerate(positions)]


def action_name(step):
    require(re.match(r'      - (?:name|uses|run|if|id):', step[0]) is not None,
            'Unsupported workflow step layout')
    values = []
    declarations = []
    for line in step:
        if re.match(r'(?:      - |        )(?:uses|[\"\']uses[\"\'])\s*:', line):
            declarations.append(line)
        match = re.fullmatch(r'(?:      - |        )uses:\s*(.*?)\s*', line)
        if match:
            values.append(scalar(match.group(1)))
    require(len(values) == len(declarations), 'Unsupported action declaration layout')
    require(len(values) <= 1, 'Duplicate action declaration')
    if not values:
        return None
    match = re.fullmatch(r'([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([0-9a-f]{40})', values[0])
    require(match is not None, 'Every action must use a full immutable commit SHA')
    return match.group(1)


def verify_workflow(root):
    text = (root / '.github/workflows/ci.yml').read_text()
    require(not re.search(r'\$\{\{\s*(?:vars|secrets)\.', text),
            'Remote configuration variables are not eligible for reuse')
    jobs = job_blocks(text)
    require({'frontend', 'tools', 'backend'} <= set(jobs), 'Missing complete test jobs')
    configured = {}
    for name, lines in jobs.items():
        require(field(lines, 'runs-on', 4) == 'ubuntu-22.04', 'Runner must be ubuntu-22.04')
        require(not any(re.match(r'    uses:', line) for line in lines),
                'Reusable workflows are outside this environment contract')
        found = {}
        for step in steps(lines):
            action = action_name(step)
            require(action is None or action in ACTIONS,
                    'Action is outside the supported environment contract')
            if action in ('actions/setup-python', 'actions/setup-java', 'actions/setup-node'):
                require(action not in found, 'Duplicate runtime setup action')
                require(step.count('        with:') == 1, 'Missing runtime setup inputs')
                found[action] = step
                if action == 'actions/setup-python':
                    require(field(step, 'python-version', 10) == PYTHON, 'Python version floats')
                    require(not any('python-version-file:' in line for line in step),
                            'Unsupported Python version file')
                elif action == 'actions/setup-java':
                    require(field(step, 'java-version', 10) == JAVA
                            and field(step, 'distribution', 10) == 'temurin', 'Java version floats')
                    require(not any('java-version-file:' in line for line in step),
                            'Unsupported Java version file')
                else:
                    require(field(step, 'node-version-file', 10) == 'web/.nvmrc',
                            'Node must use the fixed project version')
                    require(not any(re.match(r'          node-version:', line) for line in step),
                            'Multiple Node version inputs')
        configured[name] = found
    require('actions/setup-node' in configured['frontend'], 'Frontend Node setup missing')
    for name in ('tools', 'backend'):
        require({'actions/setup-python', 'actions/setup-java'} <= set(configured[name]),
                'Required backend/tool runtimes missing')
    require((root / 'web/.nvmrc').read_text().strip() == NODE, 'Node version floats')
    npm = re.findall(r'^\s*npm install --global npm@([^\s]+)(.*)$', text, re.MULTILINE)
    require(len(npm) == 1 and npm[0][0] == NPM
            and npm[0][1].strip() == '--ignore-scripts --no-audit --no-fund', 'npm version floats')
    backend = jobs['backend']
    require(backend.count('    services:') == 1, 'Backend services missing')
    service_lines = backend[backend.index('    services:') + 1:backend.index('    steps:')]
    names = [match.group(1) for line in service_lines
             if (match := re.fullmatch(r'      ([A-Za-z0-9_-]+):', line))]
    require(names == ['mysql', 'redis'], 'Unsupported backend services')
    for service, expected in SERVICE_IMAGES.items():
        start = service_lines.index('      ' + service + ':') + 1
        end = next((i for i in range(start, len(service_lines))
                    if re.match(r'      [A-Za-z0-9_-]+:', service_lines[i])), len(service_lines))
        require(field(service_lines[start:end], 'image', 8) == expected,
                'Service image must use the verified digest: ' + service)
    # The HTTPS tools job already uses an immutable Nginx image as well.
    pulls = re.findall(r'^\s*docker pull (\S+)\s*$', text, re.MULTILINE)
    require(pulls and all(re.fullmatch(r'[A-Za-z0-9_./-]+@sha256:[0-9a-f]{64}', value)
                          for value in pulls), 'Container pulls must use immutable digests')


def xml_text(element, name, required=False):
    nodes = element.findall(NS + name)
    require(len(nodes) <= 1, 'Duplicate Maven field: ' + name)
    if not nodes:
        require(not required, 'Missing Maven field: ' + name)
        return None
    require(len(nodes[0]) == 0, 'Unsupported nested Maven field')
    return (nodes[0].text or '').strip()


def properties(element):
    nodes = element.findall(NS + 'properties')
    require(len(nodes) <= 1, 'Duplicate Maven properties')
    result = {}
    for node in nodes[0] if nodes else []:
        key = node.tag.removeprefix(NS)
        require(key not in result and len(node) == 0, 'Duplicate or nested Maven property')
        result[key] = (node.text or '').strip()
    return result


def resolve_version(raw, values, active=()):
    require(len(active) < 64, 'Maven version property nesting exceeds the supported limit')
    def replace(match):
        key = match.group(1)
        require(key in values and key not in active, 'Unresolved or cyclic Maven version property')
        return resolve_version(values[key], values, active + (key,))
    value = PROPERTY.sub(replace, raw)
    require('${' not in value and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+\-]*', value) is not None,
            'Unsupported Maven version')
    require(value.upper() not in ('LATEST', 'RELEASE') and 'SNAPSHOT' not in value.upper(),
            'Mutable Maven version')
    return value


def verify_maven(root):
    paths = sorted(path.relative_to(root).as_posix() for path in (root / 'api').rglob('pom.xml'))
    require(paths == sorted(POMS), 'Unsupported Maven module layout')
    require(not (root / '.mvn').exists() and not (root / 'api/.mvn').exists(),
            'Maven extensions or command-line overrides are outside this contract')
    documents = {}
    for path in POMS:
        file = root / path
        require(not file.is_symlink(), 'Maven POM must be a regular source file')
        raw = file.read_text()
        require('<!DOCTYPE' not in raw and '<!ENTITY' not in raw, 'Unsupported XML declaration')
        try:
            document = ET.fromstring(raw)
        except ET.ParseError as error:
            raise ValueError('Invalid Maven XML') from error
        require(document.tag == NS + 'project'
                and all(isinstance(node.tag, str) and node.tag.startswith(NS) for node in document.iter()),
                'Unsupported Maven namespace')
        require(not document.findall('.//' + NS + 'profiles'),
                'Conditional Maven profiles are outside this environment contract')
        documents[path] = document
    parent = documents[POMS[0]]
    inherited = properties(parent)
    parent_version = xml_text(parent, 'version', True)
    root_coordinates = (xml_text(parent, 'groupId', True), xml_text(parent, 'artifactId', True),
                        parent_version)
    modules = parent.find(NS + 'modules')
    require(modules is not None and [(node.text or '').strip() for node in modules]
            == ['jeecg-boot-base-common', 'jeecg-boot-module-system'],
            'Unsupported Maven module declarations')
    for path, document in documents.items():
        values = {**inherited, **properties(document)}
        project_version = xml_text(document, 'version') or parent_version
        project_parent = document.find(NS + 'parent')
        require(project_parent is not None, 'Maven parent is required')
        declared_parent = xml_text(project_parent, 'version', True)
        if path == POMS[0]:
            require((xml_text(project_parent, 'groupId', True),
                     xml_text(project_parent, 'artifactId', True), declared_parent) == BOOT_PARENT
                    and xml_text(project_parent, 'relativePath') == '',
                    'Unsupported external Maven parent')
        else:
            require((xml_text(project_parent, 'groupId', True),
                     xml_text(project_parent, 'artifactId', True), declared_parent) == root_coordinates
                    and xml_text(project_parent, 'relativePath') in (None, '../pom.xml'),
                    'Unsupported Maven parent inheritance')
        require(not any(key in ('project.version', 'pom.version', 'project.parent.version',
                               'pom.parent.version') or key.startswith(('env.', 'settings.'))
                        for key in values),
                'Unsupported reserved Maven property override')
        values.update({'project.version': project_version, 'pom.version': project_version,
                       'project.parent.version': declared_parent, 'pom.parent.version': declared_parent})
        resolve_version(project_version, values)
        # A managed dependency can consume a version property in the external
        # parent without referencing it in the local dependency declaration.
        for key, value in values.items():
            if key.endswith('.version'):
                resolve_version(value, values)
        for node in document.iter():
            kind = node.tag.removeprefix(NS)
            if kind in ('parent', 'dependency', 'plugin', 'extension'):
                group = xml_text(node, 'groupId', kind != 'plugin') or 'org.apache.maven.plugins'
                artifact = xml_text(node, 'artifactId', True)
                coordinates = (resolve_version(group, values), resolve_version(artifact, values))
                version = xml_text(node, 'version', kind in ('parent', 'extension'))
                if version is not None:
                    resolve_version(version, values)
                elif kind in ('dependency', 'plugin'):
                    allowed = MANAGED_PLUGINS if kind == 'plugin' else MANAGED_DEPENDENCIES
                    require(coordinates in allowed, 'Unknown Maven coordinate without a fixed version')


def verify_environment_contract(root: Path) -> None:
    """Reject unsupported or floating local CI inputs without accessing the network."""
    try:
        verify_workflow(root)
        verify_maven(root)
    except (OSError, UnicodeError) as error:
        raise ValueError('Cannot read the CI environment contract') from error


def installed_packages_digest() -> str:
    """Fingerprint all installed Debian packages; this never updates or installs."""
    result = subprocess.run(['dpkg-query', '-W', '-f=${binary:Package}\t${Version}\n'],
                            check=True, capture_output=True, text=True, timeout=30)
    packages = {}
    for line in result.stdout.splitlines():
        parts = line.split('\t')
        require(len(parts) == 2 and all(parts) and parts[0] not in packages,
                'Invalid installed package inventory')
        packages[parts[0]] = parts[1]
    require(bool(packages), 'Empty installed package inventory')
    canonical = ''.join(name + '\t' + packages[name] + '\n' for name in sorted(packages))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
