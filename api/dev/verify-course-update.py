#!/usr/bin/env python3
"""Exercise real course/unit update outcomes and atomic batches in owned local fixtures."""
import argparse,json
from pathlib import Path
from local_http import FixtureApi
from local_recovery import database_inventory,file_inventory,sql,private_write


def verify(args):
    if args.output.exists():
        raise RuntimeError('Choose a fresh evidence path')
    cases=[];observations=[];prefix='fixture_update_'
    def check(name,ok):
        cases.append({'case':name,'passed':bool(ok)})
        print(('PASS ' if ok else 'FAIL ')+name,flush=True)
        if not ok:
            raise AssertionError(name)
    with FixtureApi(args.runtime,args.jar) as api:
        # Actual login initializes the fixture user's selected organization.
        # Establish the probe baseline after that authentication setup.
        for actor in ('admin','student_a','teacher_a','teacher_b'):
            api.login(actor)
        before=database_inventory(api.runtime);files=file_inventory(api.runtime/'uploads')
        def query(statement):
            return sql(api.runtime,'USE teachingopen_dev; '+statement)
        for table in ('teaching_course','teaching_course_unit'):
            if query("SELECT COUNT(*) FROM "+table+" WHERE id LIKE '"+prefix+"%'")!='0':
                raise RuntimeError('Existing probe data must be preserved')
        def snapshot():
            return {t:query("SELECT * FROM "+t+" WHERE id LIKE '"+prefix+"%' ORDER BY id") for t in ('teaching_course','teaching_course_unit')}
        def request(controller,body,actor='admin',endpoint='edit'):
            status,result,_=api.request('PUT','/teaching/'+controller+'/'+endpoint,actor,body)
            observations.append({'route':controller+'/'+endpoint,'http':status,'code':(result or {}).get('code'),'success':(result or {}).get('success')})
            return status,result or {}
        def succeeds(name,controller,body,endpoint='edit'):
            status,res=request(controller,body,endpoint=endpoint)
            check(name,status==200 and res.get('success') is True)
        def rejects(name,controller,body,code=404,endpoint='edit'):
            prior=snapshot();status,res=request(controller,body,endpoint=endpoint)
            check(name,status==200 and res.get('success') is False and res.get('code')==code)
            check(name+' preserves all probe columns',snapshot()==prior)
        error=None
        try:
            fixtures=[('teachingCourse',{'id':prefix+'course_other','courseName':'另一合成课程','isShared':False,'showHome':False,'orderNum':0}),('teachingCourseUnit',{'id':prefix+'unit_other','unitName':'其他课程单元','courseId':prefix+'course_other','mapX':5,'mapY':6,'mediaContent':'其他课程正文'}),('teachingCourse',{'id':prefix+'course','courseName':'合成课程','isShared':False,'showHome':False,'orderNum':0}),('teachingCourseUnit',{'id':prefix+'unit_a','unitName':'单元 A','courseId':prefix+'course','mapX':1,'mapY':2,'showCourseVideo':False}),('teachingCourseUnit',{'id':prefix+'unit_b','unitName':'单元 B','courseId':prefix+'course','mapX':3,'mapY':4,'showCourseVideo':True})]
            for controller,body in fixtures:
                status,res,_=api.request('POST','/teaching/'+controller+'/add','admin',body)
                check('fixture creation '+body['id'],status==200 and res and res.get('success'))
            for controller,table,rid,field,column in [('teachingCourse','teaching_course',prefix+'course','courseName','course_name'),('teachingCourseUnit','teaching_course_unit',prefix+'unit_a','unitName','unit_name')]:
                succeeds(controller+' existing row updates',controller,{'id':rid,field:'修改内容'})
                check(controller+' new content persisted',query("SELECT "+column+" FROM "+table+" WHERE id='"+rid+"'")=='修改内容')
                succeeds(controller+' identical update remains successful',controller,{'id':rid,field:'修改内容'})
                missing={'id':rid+'_missing',field:'不应创建'}
                if args.expect_legacy:
                    prior=snapshot();succeeds(controller+' legacy missing target falsely succeeds',controller,missing)
                    check(controller+' missing target really absent',snapshot()==prior and query("SELECT COUNT(*) FROM "+table+" WHERE id='"+rid+"_missing'")=='0')
                else:
                    rejects(controller+' missing target rejected',controller,missing)
                    for bad in ({field:'无 ID'},{'id':'',field:'空 ID'},{'id':'  ',field:'空白 ID'},{'id':None,field:'null ID'}):
                        rejects(controller+' malformed ID rejected '+str(bad.get('id')),controller,bad,400)
                    # A row read earlier and then removed must also be rejected.
                    removed=rid+'_deleted'
                    status,res,_=api.request('POST','/teaching/'+controller+'/add','admin',{'id':removed,field:'待删除','courseId':prefix+'course'})
                    check(controller+' create then delete fixture accepted',res and res.get('success'))
                    status,res,_=api.request('DELETE','/teaching/'+controller+'/delete?id='+removed,'admin')
                    check(controller+' actual deletion accepted',res and res.get('success') and query("SELECT COUNT(*) FROM "+table+" WHERE id='"+removed+"'")=='0')
                    rejects(controller+' stale edit after deletion rejected',controller,{'id':removed,field:'旧表单'})
                for actor in ('teacher_a','teacher_b','student_a',None):
                    prior=snapshot();status,res=request(controller,{'id':rid,field:'越权'},actor)
                    check(controller+' denied '+str(actor),res.get('success') is False and status==(200 if actor else 401) and res.get('code')==(510 if actor else 401))
                    check(controller+' denied update preserves rows '+str(actor),snapshot()==prior)
            ctrl='teachingCourseUnit';a=prefix+'unit_a';b=prefix+'unit_b';course=prefix+'course'
            positions=[{'id':a,'mapX':0,'mapY':-2},{'id':b,'mapX':8,'mapY':0}]
            def map_body(units, course_id=course):
                return units if args.expect_legacy else {'courseId':course_id,'units':units}
            body=map_body(positions)
            noncoordinate_columns=query("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='teachingopen_dev' AND TABLE_NAME='teaching_course_unit' AND COLUMN_NAME NOT IN ('map_x','map_y') ORDER BY ORDINAL_POSITION").splitlines()
            def content_snapshot():
                return query("SELECT "+','.join('`'+column+'`' for column in noncoordinate_columns)+" FROM teaching_course_unit WHERE id LIKE '"+prefix+"%' ORDER BY id")
            before_content=content_snapshot()
            succeeds('valid map batch succeeds',ctrl,body,'editBatch')
            check('both map positions persisted',query("SELECT CONCAT(map_x,':',map_y) FROM teaching_course_unit WHERE id='"+a+"'")=='0:-2' and query("SELECT CONCAT(map_x,':',map_y) FROM teaching_course_unit WHERE id='"+b+"'")=='8:0')
            check('map batch preserves every noncoordinate column including content and audit fields',content_snapshot()==before_content)
            succeeds('identical map batch remains successful',ctrl,body,'editBatch')
            for order in ('last','first'):
                existing={'id':a,'mapX':99 if order=='last' else 101,'mapY':21};missing={'id':prefix+'absent','mapX':1,'mapY':2}
                batch=[existing,missing] if order=='last' else [missing,existing]
                if args.expect_legacy:
                    succeeds('legacy missing '+order+' batch falsely succeeds',ctrl,batch,'editBatch')
                    check('legacy partial map update persists '+order,query("SELECT map_x FROM teaching_course_unit WHERE id='"+a+"'")==str(existing['mapX']))
                else:
                    rejects('missing '+order+' rejects entire batch',ctrl,map_body(batch),409,'editBatch')
            if not args.expect_legacy:
                for title,batch in [('empty',[]),('null entry',[{'id':a,'mapX':17,'mapY':18},None]),('missing ID',[{'id':a,'mapX':17,'mapY':18},{'mapX':1,'mapY':2}]),('blank ID',[{'id':a,'mapX':17,'mapY':18},{'id':' ','mapX':1,'mapY':2}]),('duplicate ID',[{'id':a,'mapX':17,'mapY':18},{'id':a,'mapX':18,'mapY':19}]),('missing coordinate',[{'id':a,'mapX':17,'mapY':18},{'id':b,'mapX':1}])]:
                    rejects('invalid batch '+title,ctrl,map_body(batch),400,'editBatch')
                rejects('cross-course batch rejects all targets',ctrl,map_body([{'id':a,'mapX':77,'mapY':88},{'id':prefix+'unit_other','mapX':99,'mapY':100}]),409,'editBatch')
                rejects('wrong declared course rejects existing units',ctrl,map_body(positions,prefix+'course_other'),409,'editBatch')
                query("UPDATE teaching_course_unit SET del_flag=1 WHERE id='"+b+"'")
                rejects('deleted target rejects entire map batch',ctrl,map_body([{'id':a,'mapX':33,'mapY':34},{'id':b,'mapX':35,'mapY':36}]),409,'editBatch')
                query("UPDATE teaching_course_unit SET del_flag=NULL WHERE id='"+b+"'")
                # Extra complete-entity fields cannot be routed into the coordinate-only update.
                malicious=[dict(unit,unitName='覆盖名称',mediaContent='覆盖正文',courseVideo='覆盖附件',courseId=prefix+'course_other',delFlag=1,showCourseVideo=True,createBy='other',updateBy='other') for unit in positions]
                before_content=content_snapshot()
                succeeds('extra entity fields ignored by map DTO',ctrl,map_body(malicious),'editBatch')
                check('map DTO preserves every unrelated field',content_snapshot()==before_content)
                # An older outer content form submits coordinates read before the map save.
                succeeds('outer content save after map save accepted',ctrl,{'id':a,'unitIntro':'地图之后保存正文','mapX':1,'mapY':2})
                check('outer content edit persisted',query("SELECT unit_intro FROM teaching_course_unit WHERE id='"+a+"'")=='地图之后保存正文')
                check('outer content save cannot overwrite current map coordinates',query("SELECT CONCAT(map_x,':',map_y) FROM teaching_course_unit WHERE id='"+a+"'")=='0:-2')
                # Real MySQL failure on the second write must undo the first coordinate update.
                trigger='fixture_update_second_position_failure'
                check('failure trigger name is unoccupied',query("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='teachingopen_dev' AND TRIGGER_NAME='"+trigger+"'")=='0')
                prior=snapshot()
                query("\nDELIMITER $$\nCREATE TRIGGER "+trigger+" BEFORE UPDATE ON teaching_course_unit FOR EACH ROW BEGIN IF NEW.id='"+b+"' AND NEW.map_x=456 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic second coordinate write failure'; END IF; END$$\nDELIMITER ;\n")
                try:
                    status,res=request(ctrl,map_body([{'id':a,'mapX':123,'mapY':124},{'id':b,'mapX':456,'mapY':457}]),endpoint='editBatch')
                    check('second map SQL write fails with owned trigger marker',status==200 and res.get('success') is False and res.get('code')==500 and 'synthetic second coordinate write failure' in res.get('message',''))
                    check('real SQL batch failure rolls back all columns',snapshot()==prior)
                finally:
                    query("DROP TRIGGER "+trigger)
                check('owned failure trigger removed',query("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA='teachingopen_dev' AND TRIGGER_NAME='"+trigger+"'")=='0')
                succeeds('valid batch recovers after SQL failure',ctrl,body,'editBatch')
                for actor in ('teacher_a','teacher_b','student_a',None):
                    prior=snapshot();status,res=request(ctrl,body,actor,'editBatch')
                    check('batch denied '+str(actor),res.get('success') is False and res.get('code')==(510 if actor else 401))
                    check('denied batch preserves rows '+str(actor),snapshot()==prior)
            check('single update retained course flags and order',query("SELECT CONCAT(is_shared,':',show_home,':',order_num) FROM teaching_course WHERE id='"+prefix+"course'")=='0:0:0')
        except Exception as exc:
            error=type(exc).__name__
            raise
        finally:
            for table in ('teaching_course_unit','teaching_course'):
                query("DELETE FROM "+table+" WHERE id LIKE '"+prefix+"%'")
            after=database_inventory(api.runtime)
            restored=all(before[t]==after[t] for t in before if t!='sys_log')
            changed_tables=[t for t in before if t!='sys_log' and before[t]!=after[t]]
            preserved=files==file_inventory(api.runtime/'uploads')
            cases.extend([{'case':'all non-audit tables restored','passed':restored},{'case':'all attachment bytes unchanged','passed':preserved}])
            result={'expected_legacy':args.expect_legacy,'jar_sha256':api.jar_sha256,'passed':sum(c['passed'] for c in cases),'total':len(cases),'exception':error,'changed_tables':changed_tables,'cases':cases,'observations':observations,'scope':'Real synthetic Spring/Shiro/MyBatis/MySQL HTTP, coordinate-only persistence, outer stale content form and real second-write trigger rollback. No production or authenticated browser acceptance.'}
            private_write(args.output,json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            if not restored or not preserved:
                raise AssertionError('Probe cleanup mismatch')
    if not all(c['passed'] for c in cases):
        raise AssertionError('Course update check failed')
    print(str(result['passed'])+'/'+str(result['total'])+' checks passed')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True);parser.add_argument('--jar',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--expect-legacy',action='store_true')
    verify(parser.parse_args())
