#!/usr/bin/env python3
"""Loopback-only synthetic list fixture. No proxy, authentication or database."""
import argparse
import json
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

p = argparse.ArgumentParser()
p.add_argument('--directory', required=True)
p.add_argument('--port', type=int, required=True)
a = p.parse_args()
lock = threading.Lock()
state = {'mode': 'normal', 'requests': [], 'deleted': []}

def records(kind):
    course = [{'id': 'synthetic-course-' + str(n), 'courseName': '合成课程 ' + str(n) + (' · 观察自然并记录实验过程的长名称示例' if n == 1 else ''), 'courseType': str(1 + n % 2), 'courseType_dictText': '合成性质 ' + str(1 + n % 2), 'courseCategory_dictText': '合成科学', 'departIds_dictText': '合成部门 A', 'departId': 'synthetic-depart-a', 'isShared': n % 2 == 0, 'showHome': n % 3 == 0, 'courseCover': '', 'courseMap': '', 'createBy': '合成管理员', 'createTime': '2026-10-03 08:00:00', 'orderNum': n, 'courseDesc': '合成介绍'} for n in range(1, 24)]
    unit = [{'id': 'synthetic-unit-' + str(n), 'courseId': 'synthetic-course-' + str(1 + n % 2), 'courseName': '合成课程 ' + str(1 + n % 2), 'unitName': '合成单元 ' + str(n), 'unitIntro': '合成简介：观察过程、记录变化并解释你的判断。' * (3 if n == 1 else 1), 'unitCover': '', 'courseWorkType': 2, 'courseWorkType_dictText': '合成 Scratch', 'createBy': '合成管理员', 'createTime': '2026-10-03 08:00:00', 'orderNum': n} for n in range(1, 18)]
    return [row for row in (course if kind == 'course' else unit) if row['id'] not in state['deleted']]

class Handler(SimpleHTTPRequestHandler):
    def reply(self, status, body, content_type='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/__state':
            return self.reply(200, state)
        if parsed.path.startswith('/teaching/'):
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            with lock:
                mode = state['mode']
                state['requests'].append({'method': 'GET', 'path': parsed.path, 'params': params, 'mode': mode})
            if parsed.path.endswith('/exportXls'):
                return self.reply(200, bytes.fromhex('d0cf11e0a1b11ae1') + b'synthetic-export-fixture', 'application/vnd.ms-excel')
            if not parsed.path.endswith('/list'):
                return self.reply(404, {'success': False, 'message': 'Synthetic endpoint missing'})
            if mode == 'slow-list' or params.get('courseName') == 'slow-old':
                time.sleep(2)
            if mode == 'network-error':
                return self.reply(503, {'success': False})
            if mode == 'list-error':
                return self.reply(200, {'success': False, 'message': '合成业务拒绝；SQL detail must not render'})
            if mode == 'malformed':
                return self.reply(200, {'success': True, 'result': {'records': [None], 'total': 'bad'}})
            kind = 'unit' if 'CourseUnit' in parsed.path else 'course'
            rows = records(kind)
            for key in ['courseName', 'unitName', 'courseType', 'departId', 'courseId']:
                if params.get(key):
                    rows = [row for row in rows if params[key] in str(row.get(key, ''))]
            total = len(rows)
            page = max(1, int(params.get('pageNo', 1)))
            size = max(1, int(params.get('pageSize', 10)))
            page_rows = [] if mode == 'empty' else rows[(page - 1) * size:page * size]
            return self.reply(200, {'success': True, 'result': {'records': page_rows, 'total': 0 if mode == 'empty' else total}})
        return super().do_GET()

    def do_POST(self):
        data = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        if self.path.endswith('/importExcel'):
            state['requests'].append({'method': 'IMPORT', 'path': self.path, 'synthetic': True, 'bytes': len(data)})
            return self.reply(200, {'success': True, 'message': '合成导入结果'})
        body = json.loads(data or '{}')
        if self.path == '/__mode':
            if body.get('mode') not in ['normal', 'empty', 'list-error', 'network-error', 'malformed', 'slow-list', 'delete-error', 'slow-delete']:
                return self.reply(400, {'success': False})
            state['mode'] = body['mode']
            return self.reply(200, {'success': True})
        if self.path == '/__reset':
            state.update(mode='normal', requests=[], deleted=[])
            return self.reply(200, {'success': True})
        return self.reply(404, {'success': False})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        with lock:
            mode = state['mode']
            state['requests'].append({'method': 'DELETE', 'path': parsed.path, 'params': params, 'mode': mode})
        if mode == 'slow-delete':
            time.sleep(2)
        if mode == 'delete-error':
            return self.reply(503, {'success': False})
        if parsed.path.endswith('/delete') or parsed.path.endswith('/deleteBatch'):
            state['deleted'].extend(params.get('ids', params.get('id', '')).strip(',').split(','))
            return self.reply(200, {'success': True, 'message': '合成删除成功'})
        return self.reply(404, {'success': False})

print('Synthetic administrator preview only, 127.0.0.1:' + str(a.port), flush=True)
ThreadingHTTPServer(('127.0.0.1', a.port), partial(Handler, directory=a.directory)).serve_forever()
