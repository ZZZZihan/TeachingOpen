#!/usr/bin/env python3
"""Do not accept skipped/missing Surefire suites as a green backend build."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {'RichTextSanitizerTest', 'AccountRegistrationServiceTest', 'AccountRecoveryServiceTest', 'CourseMapPositionServiceTest', 'PublicDictionaryBoundaryTest', 'DisabledTransitBoundaryTest', 'AccountAuthorizationTest', 'AdditionalWorkAuthorizationTest', 'AdditionalWorkStatisticsTest', 'PaginationBoundaryTest', 'WorkStarControllerTest', 'WorkCloneServiceTest',
            'AccountRecoverySessionTest', 'PublicUserDirectoryTest', 'TeachingDepartDayLogWriteBoundaryTest'}


def check(reports):
    counts = {}
    for path in reports.glob('TEST-*.xml'):
        suite = ET.parse(path).getroot()
        name = suite.attrib['name'].rsplit('.', 1)[-1]
        if name not in EXPECTED:
            continue
        tests = int(suite.attrib['tests'])
        if tests <= 0 or any(int(suite.attrib.get(k, '0')) for k in ('failures', 'errors', 'skipped')):
            raise RuntimeError('Core Java suite did not fully pass: ' + name)
        counts[name] = tests
    if set(counts) != EXPECTED:
        raise RuntimeError('Missing core Java test reports: ' + ', '.join(sorted(EXPECTED-set(counts))))
    return {'status': 'passed', 'suites': counts, 'tests': sum(counts.values())}


if __name__ == '__main__':
    result = check(ROOT / 'api/jeecg-boot-module-system/target/surefire-reports')
    output = ROOT / 'ci-results'
    output.mkdir(exist_ok=True)
    (output / 'java-tests.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
