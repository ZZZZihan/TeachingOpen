#!/usr/bin/env python3
"""Do not accept skipped/missing Surefire suites as a green backend build."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    'RichTextSanitizerTest',
    'AccountRegistrationServiceTest',
    'AccountRecoveryServiceTest',
    'AccountRecoverySessionTest',
    'PublicUserDirectoryTest',
    'CourseMapPositionServiceTest',
    'PublicDictionaryBoundaryTest',
    'DisabledTransitBoundaryTest',
    'AccountAuthorizationTest',
    'AdditionalWorkAuthorizationTest',
    'AdditionalWorkStatisticsTest',
    'PaginationBoundaryTest',
    'WorkStarControllerTest',
    'WorkCloneServiceTest',
    'DuplicateCheckSecurityTest',
    'DictionaryAdministrationTest',
    'TeachingDepartDayLogWriteBoundaryTest',
    'UserProfileValidationTest',
    'UnitViewStatisticsTest',
    'InfrastructureAdministrationTest',
    'AnnouncementAuthorizationTest',
    'QuerySqlBoundaryTest',
    'UserReadAuthorizationTest',
    'DepartmentSelectionTest',
    'WorkAttachmentAuthorizationTest',
    'LocalFileReferenceAuthorizationTest',
    'WorkEventStatisticsTest',
    'LiveAuthenticationScopeTest',
    'TeachingMenuSecurityTest',
    'AuditLogAuthorizationTest',
    'AutoLogSafetyTest',
    'FileDeletionConcurrencyTest',
    'FileDeletionReadBoundaryTest',
    'FileEncodedReferenceDeletionTest',
    'AdditionalWorkReadAuthorizationTest',
    'ScratchAssetAdministrationTest',
    'GlobalRuleAdministrationTest',
    'GlobalManagementAuthorizationTest',
}


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='Print the exact Surefire selection required by this gate')
    args = parser.parse_args()
    if args.list:
        print(','.join(sorted(EXPECTED)))
        raise SystemExit(0)
    result = check(ROOT / 'api/jeecg-boot-module-system/target/surefire-reports')
    output = ROOT / 'ci-results'
    output.mkdir(exist_ok=True)
    (output / 'java-tests.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
