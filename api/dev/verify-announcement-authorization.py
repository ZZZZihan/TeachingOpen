#!/usr/bin/env python3
"""Notification administration, audience isolation, HTML and no-side-effect regressions.

Runs only through FixtureApi's task-owned synthetic localhost runtime. Never sends
mail/SMS and all HTML effects are local DOM markers (browser companion tests them).
"""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX = 'fixture_h02_'
TITLE = 'fixture-h02-'
TABLES = ('sys_announcement', 'sys_announcement_send', 'sys_message', 'sys_sms_template')
TRIGGER = PREFIX + 'receipt_failure'
HTML = '<p>通知保留<strong>格式</strong></p><table><tr><td>表格</td></tr></table><img src="data:image/png;base64,broken" onerror="document.body.dataset.h02=1"><a href="javascript:document.body.dataset.h02=2">链接</a><svg onload="document.body.dataset.h02=3"></svg>'
BASE = '/sys/annountCement/'
SEND = '/sys/sysAnnouncementSend/'


def workbook():
    rows = [['合成通知导入'], [], ['标题', '内容', '优先级', '消息类型', '通告对象类型', '发布状态', '发布人'],
            [TITLE + 'import', HTML, 'L', '1', 'ALL', '1', 'forged_sender']]
    cells = []
    for row_index, row in enumerate(rows, 1):
        cells.append('<row r="' + str(row_index) + '">' + ''.join(
            '<c r="' + chr(65 + col) + str(row_index) + '" t="inlineStr"><is><t>' + escape(value) + '</t></is></c>'
            for col, value in enumerate(row)) + '</row>')
    output = io.BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        archive.writestr('_rels/.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="通知" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        # The deployed POI 3.9 reader requires a StylesTable relationship, even for unstyled cells.
        archive.writestr('xl/styles.xml', '<?xml version="1.0"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        archive.writestr('xl/worksheets/sheet1.xml', '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(cells) + '</sheetData></worksheet>')
    return output.getvalue()


def verify(args):
    if args.output.exists():
        raise RuntimeError('Preserve existing notification evidence; select a new output file')
    cases = []
    def check(name, passed):
        cases.append({'case': name, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)

    with FixtureApi(args.runtime.resolve(), args.jar) as api, ExitStack() as stack:
        def sql(statement):
            return subprocess.check_output(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement], text=True).strip()
        def literal(value):
            return '0x' + str(value).encode().hex()
        # The schema calls the template table sys_sms_template in existing installations.
        tables = [table for table in TABLES if sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='" + table + "'") == '1']
        def snapshot():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest() for table in tables}
        original = snapshot()
        if sql("SELECT COUNT(*) FROM sys_announcement WHERE id LIKE '" + PREFIX + "%' OR titile LIKE '" + TITLE + "%'") != '0':
            raise RuntimeError('Existing H02 synthetic fixtures must not be overwritten')
        if sql("SELECT COUNT(*) FROM sys_user_role WHERE id='" + PREFIX + "role'") != '0':
            raise RuntimeError('Existing H02 synthetic role grant')
        if sql("SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name='" + TRIGGER + "'") != '0':
            raise RuntimeError('Existing H02 synthetic trigger')
        registration_times = {actor: sql("SELECT IFNULL(DATE_FORMAT(create_time,'%Y-%m-%d %H:%i:%s'),'NULL') FROM sys_user WHERE id="
                                         + literal('fixture_' + actor)) for actor in ('student_a', 'teacher_a')}
        for actor in ('student_a', 'student_b', 'teacher_a', 'admin'):
            api.login(actor)
        spec = importlib.util.spec_from_file_location('notification_transport_probe', Path(__file__).with_name('verify-notification-websocket.py'))
        transport = importlib.util.module_from_spec(spec); spec.loader.exec_module(transport)
        sockets = {}
        for actor in ('student_a', 'student_b'):
            client = transport.Socket(api.ports['backend'], 'fixture_' + actor); stack.callback(client.close)
            client.send({'type': 'authenticate', 'token': api.tokens[actor]})
            if (client.receive() or {}).get('cmd') != 'authenticated':
                raise RuntimeError('Actual authenticated notification socket required')
            sockets[actor] = client
        def quiet():
            return all(client.receive(.04) is None for client in sockets.values())
        def success(method, route, actor='admin', data=None):
            status, result, _ = api.request(method, route, actor, data)
            return status == 200 and result and result.get('success') is True, result or {}
        def denied(name, method, route, actor='student_a', data=None):
            before = snapshot()
            status, result, _ = api.request(method, route, actor, data)
            check(name + ' is an authorization refusal', status == 200 and result and result.get('success') is False and result.get('code') == 510 and '没有权限' in result.get('message', ''))
            check(name + ' leaves notification/audience/outbound-message rows unchanged', snapshot() == before)
            check(name + ' sends no socket event', quiet())
        def command(suffix, **extra):
            return dict(titile=TITLE + suffix, msgContent=HTML, msgType='ALL', msgCategory='1', priority='L',
                        startTime='2026-01-01 00:00:00', endTime='2035-01-01 00:00:00', **extra)
        def create(suffix, **extra):
            body = command(suffix); body.update(extra)
            allowed, _ = success('POST', BASE + 'add', data=body)
            check('administrator creates ' + suffix, allowed)
            ident = sql('SELECT id FROM sys_announcement WHERE titile=' + literal(TITLE + suffix))
            if not ident:
                raise RuntimeError('Expected synthetic announcement was not created: ' + suffix)
            return ident
        def announcement(ident):
            return json.loads(bytes.fromhex(sql("SELECT HEX(JSON_OBJECT('sender',sender,'sendStatus',send_status,'delFlag',del_flag,'msgContent',msg_content,'createBy',create_by,'openType',open_type,'userIds',user_ids)) FROM sys_announcement WHERE id=" + literal(ident))).decode())
        def seed(suffix, recipient='fixture_student_a', status='1'):
            ident = PREFIX + suffix
            sql("INSERT INTO sys_announcement (id,titile,msg_content,msg_category,msg_type,send_status,del_flag,sender,create_time,end_time) VALUES (" + literal(ident) + ',' + literal(TITLE + suffix) + ',' + literal(HTML) + ",'1','USER'," + literal(status) + ",'0','fixture_admin','2026-01-01','2035-01-01')")
            sql("INSERT INTO sys_announcement_send (id,annt_id,user_id,read_flag) VALUES (" + literal(ident + '_receipt') + ',' + literal(ident) + ',' + literal(recipient) + ",'0')")
            return ident
        trigger_created = False
        try:
            if args.expect_legacy:
                allowed, _ = success('POST', BASE + 'add', actor='student_a', data=command('legacy'))
                check('legacy ordinary user can write notification', allowed)
                ident = sql('SELECT id FROM sys_announcement WHERE titile=' + literal(TITLE + 'legacy'))
                allowed, _ = success('GET', BASE + 'doReleaseData?id=' + quote(ident), actor='student_a')
                check('legacy ordinary user can publish', allowed)
                check('legacy notification contains unsanitized event handler', 'onerror' in announcement(ident)['msgContent'])
                check('legacy broadcast reaches another user', (sockets['student_b'].receive(.5) or {}).get('msgId') == ident)
                success('GET', BASE + 'listByUser', actor='student_b')
                allowed, response = success('GET', BASE + 'queryById?id=' + quote(ident), actor='student_b')
                check('legacy raw content reaches recipient API', allowed and 'onerror' in response.get('result', {}).get('msgContent', ''))
            else:
                for actor in registration_times:
                    sql('UPDATE sys_user SET create_time=NULL WHERE id=' + literal('fixture_' + actor))
                private = seed('private')
                foreign = seed('foreign', 'fixture_student_b')
                draft = seed('draft', status='0')
                expired_all = seed('expired-all')
                sql("UPDATE sys_announcement SET msg_type='ALL',end_time='2000-01-01' WHERE id=" + literal(expired_all))
                for actor in ('student_a', 'teacher_a'):
                    for method, endpoint, data in [('POST', 'add', command('denied')), ('PUT', 'edit', dict(command('changed'), id=private)),
                            ('DELETE', 'delete?id=' + private, None), ('DELETE', 'deleteBatch?ids=' + private + ',' + foreign, None),
                            ('GET', 'doReleaseData?id=' + private, None), ('GET', 'doReovkeData?id=' + private, None),
                            ('POST', 'importExcel', None), ('GET', 'list', None), ('GET', 'exportXls', None)]:
                        denied(actor + ' ' + endpoint, method, BASE + endpoint, actor, data)
                    for method, endpoint, data in [('POST', 'add', {'anntId':foreign,'userId':'fixture_student_a'}),
                            ('PUT','edit',{'id':private+'_receipt','userId':'fixture_student_b'}), ('DELETE','delete?id='+private+'_receipt',None),
                            ('DELETE','deleteBatch?ids='+private+'_receipt',None), ('GET','list',None)]:
                        denied(actor + ' raw receipt ' + endpoint, method, SEND + endpoint, actor, data)
                    for prefix in ('/message/sysMessage/', '/message/sysMessageTemplate/'):
                        for method, endpoint, data in [('GET','list',None),('GET','queryById?id=synthetic',None),('GET','exportXls',None),
                                ('POST','add',{}),('PUT','edit',{}),('POST','importExcel',None),('DELETE','delete?id=synthetic',None),('DELETE','deleteBatch?ids=synthetic',None)]:
                            denied(actor + ' ' + prefix + endpoint, method, prefix + endpoint, actor, data)
                    denied(actor + ' template send', 'POST', '/message/sysMessageTemplate/sendMsg', actor, {})
                    denied(actor + ' direct all-user socket send', 'POST', '/webSocketApi/sendAll', actor,
                           {'message':'fixture-h02-denied'})
                    denied(actor + ' direct targeted socket send', 'POST', '/webSocketApi/sendUser', actor,
                           {'userId':'fixture_student_b','message':'fixture-h02-denied'})
                denied('cross-recipient read', 'GET', BASE + 'queryById?id=' + foreign)
                denied('draft read', 'GET', BASE + 'queryById?id=' + draft)
                denied('missing registration date cannot read expired ALL history', 'GET', BASE + 'queryById?id=' + expired_all)
                denied('missing registration date cannot mark expired ALL history', 'PUT', SEND + 'editByAnntIdAndUserId', data={'anntId':expired_all})
                denied('cross-recipient receipt detail', 'GET', SEND + 'queryById?id=' + foreign + '_receipt')
                denied('cross-recipient mark read', 'PUT', SEND + 'editByAnntIdAndUserId', data={'anntId':foreign})
                denied('SQL syntax is only an unknown identifier', 'PUT', SEND + 'editByAnntIdAndUserId', data={'anntId':private + "' OR '1'='1"})
                denied('cross-recipient sync', 'GET', BASE + 'syncNotic?anntId=' + foreign)
                for endpoint in (BASE + 'queryById?id=' + private, BASE + 'listByUser', SEND + 'getMyAnnouncementSend?userId=fixture_student_b'):
                    allowed, result = success('GET', endpoint, actor='student_a')
                    serialized = json.dumps(result, ensure_ascii=False)
                    check('recipient reads sanitized historical HTML ' + endpoint, allowed and 'onerror' not in serialized and 'javascript:' not in serialized and TITLE + 'private' in serialized)
                    check('foreign recipient data not exposed ' + endpoint, TITLE + 'foreign' not in serialized)
                    check('ineligible expired ALL not exposed ' + endpoint, TITLE + 'expired-all' not in serialized)
                allowed, _ = success('PUT', SEND + 'editByAnntIdAndUserId', actor='student_a', data={'anntId':private})
                check('owner marks own notice read', allowed and sql('SELECT read_flag FROM sys_announcement_send WHERE id=' + literal(private+'_receipt')) == '1')
                check('owner mark-read preserves foreign receipt', sql('SELECT read_flag FROM sys_announcement_send WHERE id=' + literal(foreign+'_receipt')) == '0')
                allowed, _ = success('GET', BASE+'syncNotic?anntId='+private, actor='student_a')
                check('read sync only reaches owner session', allowed and (sockets['student_a'].receive(.5) or {}).get('cmd') == 'user' and sockets['student_b'].receive(.1) is None)
                allowed, _ = success('PUT', SEND+'readAll', actor='student_a')
                check('readAll preserves draft and other user rows', allowed and sql('SELECT read_flag FROM sys_announcement_send WHERE id='+literal(draft+'_receipt')) == '0' and sql('SELECT read_flag FROM sys_announcement_send WHERE id='+literal(foreign+'_receipt')) == '0')
                check('readAll preserves ineligible expired ALL receipt', sql('SELECT read_flag FROM sys_announcement_send WHERE id='+literal(expired_all+'_receipt')) == '0')
                sql("UPDATE sys_user SET create_time='1999-01-01' WHERE id='fixture_student_a'")
                allowed, _ = success('GET', BASE+'queryById?id='+expired_all, actor='student_a')
                check('known account predating ALL expiry retains entitled history', allowed)
                allowed, result = success('GET', SEND+'getMyAnnouncementSend', actor='student_a')
                check('known account inbox keeps entitled ALL history', allowed and TITLE+'expired-all' in json.dumps(result))
                sql("UPDATE sys_user SET create_time='2001-01-01' WHERE id='fixture_student_a'")
                denied('known account cannot read ALL expired before registration', 'GET', BASE+'queryById?id='+expired_all)
                sql("UPDATE sys_user SET create_time=NULL WHERE id='fixture_student_a'")
                ident = create('authored', id=PREFIX+'forged', sender='forged', sendStatus='1', delFlag='1', createBy='forged', openType='component', openPage='forged')
                row = announcement(ident)
                check('authoring binds server identity draft state and excludes dynamic component fields', row['sender']=='fixture_admin' and row['createBy']=='fixture_admin' and row['sendStatus']=='0' and row['delFlag']=='0' and row['openType'] is None and ident != PREFIX+'forged')
                check('write sanitizer retains ordinary markup and strips active HTML', 'onerror' not in row['msgContent'] and 'javascript:' not in row['msgContent'] and '<strong>' in row['msgContent'] and '<table>' in row['msgContent'])
                check('creating a draft sends no socket event', quiet())
                allowed, _ = success('GET', BASE+'doReleaseData?id='+ident)
                check('admin publishes ALL and both recipients get refresh', allowed and all((client.receive(.5) or {}).get('msgId')==ident for client in sockets.values()))
                for actor in ('student_a','teacher_a'):
                    allowed, result = success('GET', BASE+'listByUser', actor=actor)
                    check(actor+' still receives published ALL notices', allowed and TITLE+'authored' in json.dumps(result))
                    for endpoint in (BASE+'queryById?id='+ident, SEND+'getMyAnnouncementSend'):
                        allowed, result = success('GET', endpoint, actor=actor)
                        check(actor+' with missing registration date reads active ALL '+endpoint, allowed and TITLE+'authored' in json.dumps(result))
                allowed, _ = success('GET', BASE+'doReovkeData?id='+ident)
                check('admin revokes with recipient refresh', allowed and all((client.receive(.5) or {}).get('msgId')==ident for client in sockets.values()))
                denied('revoked notice no longer readable', 'GET', BASE+'queryById?id='+ident)
                targeted = create('targeted', msgType='USER', userIds='fixture_student_a,')
                allowed, _ = success('GET', BASE+'doReleaseData?id='+targeted)
                check('targeted publication only reaches assigned recipient', allowed and (sockets['student_a'].receive(.5) or {}).get('msgId')==targeted and sockets['student_b'].receive(.1) is None)
                edit_body = command('targeted'); edit_body.update(id=targeted, msgType='USER', userIds='fixture_student_b,', sendStatus='0', sender='forged')
                allowed, _ = success('PUT', BASE+'edit', data=edit_body)
                check('admin audience edit succeeds and preserves publication identity', allowed and announcement(targeted)['sendStatus']=='1' and announcement(targeted)['sender']=='fixture_admin')
                check('audience edit refreshes new recipient', (sockets['student_b'].receive(.5) or {}).get('msgId')==targeted)
                check('removed audience receives no new content event', sockets['student_a'].receive(.1) is None)
                denied('removed recipient cannot reuse same token to read', 'GET', BASE+'queryById?id='+targeted)
                allowed, _ = success('GET', BASE+'queryById?id='+targeted, actor='student_b')
                check('new recipient reads reassigned notice', allowed)
                role_id = sql("SELECT role_id FROM sys_user_role WHERE user_id='fixture_admin' LIMIT 1")
                sql("INSERT INTO sys_user_role(id,user_id,role_id) VALUES ('"+PREFIX+"role','fixture_student_a',"+literal(role_id)+")")
                allowed, _ = success('GET', BASE+'list', actor='student_a'); check('live admin grant permits existing token', allowed)
                allowed, _ = success('POST', '/webSocketApi/sendAll', actor='student_a',
                                     data={'message':'fixture-h02-before-revocation'})
                check('live admin grant permits direct socket send on existing token', allowed and all(
                    (client.receive(.5) or {}).get('msgTxt') == 'fixture-h02-before-revocation' for client in sockets.values()))
                sql("DELETE FROM sys_user_role WHERE id='"+PREFIX+"role'")
                denied('live admin removal rejects same token with warm principal', 'POST', BASE+'add', data=command('revoked-role'))
                denied('live admin removal rejects same-token direct all-user socket send', 'POST', '/webSocketApi/sendAll',
                       data={'message':'fixture-h02-after-revocation'})
                denied('live admin removal rejects same-token direct targeted socket send', 'POST', '/webSocketApi/sendUser',
                       data={'userId':'fixture_student_b','message':'fixture-h02-after-revocation'})
                before = snapshot()
                sql("CREATE TRIGGER " + TRIGGER + " BEFORE INSERT ON sys_announcement_send FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic H02 receipt failure'")
                trigger_created = True
                failing = command('rollback'); failing.update(msgType='USER',userIds='fixture_student_a,')
                allowed, result = success('POST', BASE+'add', data=failing)
                check('receipt database failure rolls back parent notification', not allowed and result.get('success') is False and snapshot()==before)
                check('rollback produces no broadcast', quiet())
                sql('DROP TRIGGER '+TRIGGER); trigger_created = False
                boundary = '----teaching-h02-synthetic'
                data = ('--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="fixture.xlsx"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n').encode()+workbook()+('\r\n--'+boundary+'--\r\n').encode()
                request = Request('http://127.0.0.1:'+str(api.ports['backend'])+'/api'+BASE+'importExcel',data=data,method='POST',headers={'X-Access-Token':api.tokens['admin'],'Content-Type':'multipart/form-data; boundary='+boundary})
                try: response=urlopen(request,timeout=15)
                except HTTPError as error: response=error
                with response: imported=json.loads(response.read())
                import_id=sql('SELECT id FROM sys_announcement WHERE titile='+literal(TITLE+'import'))
                check('real XLSX import uses authorized command path', imported.get('success') is True and bool(import_id))
                if import_id:
                    row=announcement(import_id)
                    check('import strips HTML and resets untrusted sender/publication', row['sendStatus']=='0' and row['sender']=='fixture_admin' and 'onerror' not in row['msgContent'])
                allowed,_=success('DELETE',BASE+'deleteBatch?ids='+ident+','+targeted)
                check('admin batch soft-delete completes',allowed and sql('SELECT COUNT(*) FROM sys_announcement WHERE id IN ('+literal(ident)+','+literal(targeted)+") AND del_flag='1'")=='2')
                for client in sockets.values():
                    while client.receive(.03) is not None: pass
                denied('deleted target unavailable to previous recipient','GET',BASE+'queryById?id='+targeted,actor='student_b')
        finally:
            if trigger_created: sql('DROP TRIGGER '+TRIGGER)
            sql("DELETE FROM sys_user_role WHERE id='"+PREFIX+"role'")
            sql("DELETE FROM sys_announcement_send WHERE annt_id IN (SELECT id FROM sys_announcement WHERE id LIKE '"+PREFIX+"%' OR titile LIKE '"+TITLE+"%')")
            sql("DELETE FROM sys_announcement WHERE id LIKE '"+PREFIX+"%' OR titile LIKE '"+TITLE+"%'")
            for actor, timestamp in registration_times.items():
                sql('UPDATE sys_user SET create_time=' + ('NULL' if timestamp == 'NULL' else literal(timestamp))
                    + ' WHERE id=' + literal('fixture_' + actor))
            check('synthetic cleanup restores account registration dates', all(
                sql("SELECT IFNULL(DATE_FORMAT(create_time,'%Y-%m-%d %H:%i:%s'),'NULL') FROM sys_user WHERE id="
                    + literal('fixture_' + actor)) == timestamp for actor, timestamp in registration_times.items()))
            check('synthetic cleanup restores notification tables',snapshot()==original)
        result={'status':'passed' if all(case['passed'] for case in cases) else 'failed','jar_sha256':api.jar_sha256,
                'mode':'legacy-reproduced' if args.expect_legacy else 'fixed','cases':cases,
                'passed':sum(case['passed'] for case in cases),'total':len(cases),'failed':sum(not case['passed'] for case in cases),
                'expected_legacy':bool(args.expect_legacy),
                'scope':'synthetic HTTP/MySQL and authenticated localhost WebSocket; no production or external delivery'}
        args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        if result['status']!='passed': raise SystemExit(1)
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--runtime',type=Path,required=True); parser.add_argument('--jar',type=Path)
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--expect-legacy',action='store_true')
    verify(parser.parse_args())
