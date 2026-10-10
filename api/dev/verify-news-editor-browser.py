#!/usr/bin/env python3
"""Run the actual news/editor components with a private, synthetic-admin HTTP proxy."""
import argparse
import functools
import importlib.util
import json
from pathlib import Path
import subprocess
import threading
from http.server import ThreadingHTTPServer
from local_http import FixtureApi
from local_runtime import mysql_command, load_ports


def run(args):
    runtime = args.runtime.resolve()
    if runtime.name != 'review-news-1010' or load_ports(runtime) != dict(mysql=13446, redis=16549, backend=18346, frontend=18347): raise ValueError('Unexpected local runtime')
    spec = importlib.util.spec_from_file_location('frontend_probe', Path(__file__).with_name('serve-frontend.py'))
    frontend = importlib.util.module_from_spec(spec); spec.loader.exec_module(frontend)
    with FixtureApi(runtime, args.jar) as api:
        api.login('admin')
        client = api
        def files():
            rows = subprocess.check_output(mysql_command(runtime) + ['teachingopen_dev', '-e', 'SELECT id,file_path FROM sys_file ORDER BY id'], text=True).splitlines()
            return {row.split('\t', 1)[0]: row.split('\t', 1)[1] for row in rows}
        original_files = files()
        if subprocess.check_output(mysql_command(runtime) + ['teachingopen_dev', '-e', "SELECT COUNT(*) FROM teaching_news WHERE news_title='news_content_browser'"], text=True).strip() != '0': raise ValueError('Existing browser probe news')
        class Handler(frontend.LocalFrontend):
            ports = client.ports
            def api(self):
                # Test-only proxy. Credential stays in process memory and never enters browser artifacts.
                self.headers['X-Access-Token'] = client.tokens['admin']
                super().api()
            do_POST = api; do_PUT = api; do_DELETE = api; do_OPTIONS = api
        server = ThreadingHTTPServer(('127.0.0.1', api.ports['frontend']), functools.partial(Handler, directory=str(args.dist.resolve())))
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        workdir = args.output.parent
        (workdir / 'output/playwright').mkdir(parents=True, exist_ok=True)
        cli = str(args.browser_cli.resolve())
        try:
            subprocess.run([cli, '--session', 'teaching-news', 'goto', 'http://127.0.0.1:18347'], cwd=workdir, capture_output=True, text=True, check=True)
            subprocess.run([cli, '--session', 'teaching-news', 'snapshot'], cwd=workdir, capture_output=True, text=True, check=True)
            result = subprocess.run([cli, '--session', 'teaching-news', 'run-code', '--filename', str(Path(__file__).resolve().parents[2] / 'web/tests/rich-editor-preview/verify-browser.js')], cwd=workdir, capture_output=True, text=True, timeout=180)
            raw = result.stdout.split('### Result\n', 1)[-1].split('\n###', 1)[0].strip()
            parsed = json.loads(raw); args.output.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps(parsed, ensure_ascii=False, indent=2))
        finally:
            subprocess.run(mysql_command(runtime) + ['teachingopen_dev', '-e', "DELETE FROM teaching_news WHERE news_title='news_content_browser'"], check=True)
            for file_id, relative in files().items():
                if file_id in original_files: continue
                # Only request-created uploads in this dedicated test instance are removed.
                path = (runtime / 'uploads' / relative).resolve()
                if not path.is_relative_to((runtime / 'uploads').resolve()): raise ValueError('Upload escaped synthetic runtime')
                path.unlink(missing_ok=True)
                subprocess.run(mysql_command(runtime) + ['teachingopen_dev', '-e', "DELETE FROM sys_file WHERE id=CONVERT(0x" + file_id.encode().hex() + " USING utf8mb4)"], check=True)
            server.shutdown(); server.server_close()
    return not parsed.get('error') and parsed['passed'] == parsed['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True); parser.add_argument('--jar', type=Path); parser.add_argument('--dist', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browser-cli', type=Path, default=Path.home() / '.codex/skills/playwright/scripts/playwright_cli.sh')
    raise SystemExit(0 if run(parser.parse_args()) else 1)
