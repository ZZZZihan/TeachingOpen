#!/usr/bin/env python3
"""Require complete real-menu browser evidence for this immutable checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VIEWPORTS = [{'width': 1440, 'height': 1000}, {'width': 390, 'height': 1200}]
HTTPS_FIXTURE = 'https://menu-fixture.invalid/learning'
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
SOURCES = (
    'web/src/views/home/modules/Header.vue', 'web/src/components/menu/tmenu.js',
    'web/src/components/brand/CampusMasthead.vue', 'web/src/assets/brand/wordmark.svg',
    'web/src/store/mutation-types.js', 'web/src/utils/teachingMenuUrl.js',
)
REQUIRED_CHECKS = {
    'Chromium binary exists (browser is required, never skipped)',
    'all four synthetic HTTPS navigation requests intercepted before network',
    'no unexpected outbound request', 'no browser runtime or protocol error',
} | {str(viewport['width']) + ' ' + behavior for viewport in VIEWPORTS for behavior in (
    'actual Header contains mounted TMenu', 'unsafe leaf URL has expected baseline/fixed link shape',
    'top dangerous navigation cannot execute on real click',
    'group dangerous navigation cannot execute on real click',
    'child dangerous navigation cannot execute on real click', 'safe descendants remain navigable',
    'normal SPA route including query and fragment navigates', 'normal submenu title navigates',
    'native same-origin editor preserves path and query', 'HTTPS same-tab navigation is preserved',
    'HTTPS popup navigates', 'HTTPS popup has no opener',
)}
REQUIRED_CLICKS = {str(viewport['width']) + ' ' + label for viewport in VIEWPORTS for label in (
    'top-level unsafe', 'submenu-title unsafe', 'child unsafe',
    'safe child beneath disabled unsafe title', 'route', 'normal submenu title',
    'static editor', 'HTTPS same tab', 'HTTPS new tab',
)}
SCREENSHOTS = tuple(str(viewport['width']) + '-' + label + '.png'
                    for viewport in VIEWPORTS for label in (
                        'unsafe-before-click', 'unsafe-after-click', 'normal-route', 'https-new-tab'))


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def check(report_path, sha, root=ROOT):
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or git(root, 'rev-parse', 'HEAD').decode().strip() != sha:
        raise RuntimeError('Menu browser gate requires the immutable current checkout SHA')
    report_path = Path(report_path)
    report = json.loads(report_path.read_text())
    if (not isinstance(report, dict) or report.get('completed') is not True
            or report.get('expected_legacy') is not False or report.get('errors') != []
            or report.get('blocked') != [] or report.get('viewports') != VIEWPORTS):
        raise RuntimeError('Menu browser evidence is incomplete, legacy, or contains browser/network errors')
    browser = report.get('browser')
    if not isinstance(browser, dict) or not re.match(r'^(?:HeadlessChrome|Chrome|Chromium)/\d', browser.get('product', '')):
        raise RuntimeError('Menu browser evidence must identify the actual Chromium browser')
    checks = report.get('checks')
    if (not isinstance(checks, list) or not checks
            or any(not isinstance(item, dict) or item.get('passed') is not True
                   or not isinstance(item.get('case'), str) for item in checks)):
        raise RuntimeError('Every required menu browser check must have passed')
    names = [item['case'] for item in checks]
    if (len(set(names)) != len(names) or not REQUIRED_CHECKS.issubset(names)
            or type(report.get('passed')) is not int or report['passed'] != len(checks)
            or type(report.get('total')) is not int or report['total'] != len(checks)
            or type(report.get('failed')) is not int or report['failed'] != 0):
        raise RuntimeError('Menu browser evidence is missing behaviors or has inconsistent counts')
    clicks = report.get('clicks')
    if (not isinstance(clicks, list) or any(not isinstance(item, dict)
            or not isinstance(item.get('case'), str)
            or item.get('input') != 'Chromium Input.dispatchMouseEvent' for item in clicks)):
        raise RuntimeError('Menu navigation requires real Chromium mouse input')
    click_names = [item['case'] for item in clicks]
    if len(set(click_names)) != len(click_names) or not REQUIRED_CLICKS.issubset(click_names):
        raise RuntimeError('Menu browser evidence is missing real navigation clicks')
    expected_external = {'url': HTTPS_FIXTURE, 'resourceType': 'Document', 'intercepted_before_network': True}
    if report.get('external') != [expected_external] * 4:
        raise RuntimeError('All synthetic HTTPS navigation must be intercepted before network')
    source = report.get('source')
    if not isinstance(source, dict) or source.get('ref') != sha or source.get('resolved_ref') != sha:
        raise RuntimeError('Menu browser source is not the immutable current candidate')
    files = source.get('files')
    if (not isinstance(files, list) or len(files) != len(SOURCES)
            or any(not isinstance(item, dict) or not isinstance(item.get('file'), str) for item in files)
            or {item['file'] for item in files} != set(SOURCES)):
        raise RuntimeError('Menu browser source manifest is incomplete')
    for item in files:
        if item.get('sha256') != hashlib.sha256(git(root, 'show', sha + ':' + item['file'])).hexdigest():
            raise RuntimeError('Menu browser rendered source differs from candidate: ' + item['file'])
    if json.loads((report_path.parent / 'sources.json').read_text()) != source:
        raise RuntimeError('Menu browser source artifact does not match the report')
    for name in SCREENSHOTS:
        path = report_path.parent / name
        if not path.is_file() or not path.read_bytes().startswith(PNG_SIGNATURE):
            raise RuntimeError('Missing menu viewport screenshot: ' + name)
    return {'status': 'passed', 'github_sha': sha, 'checks': len(checks), 'clicks': len(clicks),
            'browser': browser['product'], 'source_files': len(files), 'screenshots': len(SCREENSHOTS)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--report', type=Path, default=ROOT / 'ci-results/teaching-menu-browser/report.json')
    args = parser.parse_args()
    print(json.dumps(check(args.report, args.sha), ensure_ascii=False))
