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
            for actor in ('admin','student_a','teacher_a','teacher_b'):
                api.login(actor)
            fixtures=[('teachingCourse',{'id':prefix+'course','courseName':'合成课程','isShared':False,'showHome':False,'orderNum':0}),('teachingCourseUnit',{'id':prefix+'unit_a','unitName':'单元 A','courseId':prefix+'course','mapX':1,'mapY':2,'showCourseVideo':False}),('teachingCourseUnit',{'id':prefix+'unit_b','unitName':'单元 B','courseId':prefix+'course','mapX':3,'mapY':4,'showCourseVideo':True})]
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
            ctrl='teachingCourseUnit';a=prefix+'unit_a';b=prefix+'unit_b'
            body=[{'id':a,'mapX':0,'mapY':-2},{'id':b,'mapX':8,'mapY':0}]
            succeeds('valid map batch succeeds',ctrl,body,'editBatch')
            check('both map positions persisted',query("SELECT CONCAT(map_x,':',map_y) FROM teaching_course_unit WHERE id='"+a+"'")=='0:-2' and query("SELECT CONCAT(map_x,':',map_y) FROM teaching_course_unit WHERE id='"+b+"'")=='8:0')
            check('map batch preserves names visibility and parent',query("SELECT CONCAT(unit_name,':',show_course_video,':',course_id) FROM teaching_course_unit WHERE id='"+a+"'")=='修改内容:0:'+prefix+'course')
            succeeds('identical map batch remains successful',ctrl,body,'editBatch')
            for order in ('last','first'):
                existing={'id':a,'mapX':99 if order=='last' else 101};missing={'id':prefix+'absent','mapX':1}
                batch=[existing,missing] if order=='last' else [missing,existing]
                if args.expect_legacy:
                    succeeds('legacy missing '+order+' batch falsely succeeds',ctrl,batch,'editBatch')
                    check('legacy partial map update persists '+order,query("SELECT map_x FROM teaching_course_unit WHERE id='"+a+"'")==str(existing['mapX']))
                else:
                    rejects('missing '+order+' rejects entire batch',ctrl,batch,404,'editBatch')
            if not args.expect_legacy:
                for title,batch in [('empty',[]),('null entry',[{'id':a,'mapX':17},None]),('missing ID',[{'id':a,'mapX':17},{'mapX':1}]),('blank ID',[{'id':a,'mapX':17},{'id':' '}]),('duplicate ID',[{'id':a,'mapX':17},{'id':a,'mapX':18}])]:
                    rejects('invalid batch '+title,ctrl,batch,400,'editBatch')
                # A data error on the second write must roll back the first update and audit fields.
                prior=snapshot();status,res=request(ctrl,[{'id':a,'mapX':123},{'id':b,'unitName':'过'*1000}],endpoint='editBatch')
                check('second batch SQL write fails',status>=400 or res.get('success') is False)
                check('SQL batch failure rolls back all columns',snapshot()==prior)
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
            preserved=files==file_inventory(api.runtime/'uploads')
            cases.extend([{'case':'all non-audit tables restored','passed':restored},{'case':'all attachment bytes unchanged','passed':preserved}])
            result={'expected_legacy':args.expect_legacy,'jar_sha256':api.jar_sha256,'passed':sum(c['passed'] for c in cases),'total':len(cases),'exception':error,'cases':cases,'observations':observations,'scope':'Real synthetic Java/MySQL HTTP and rollback; legacy observations are defect reproduction, not fixed acceptance. No authenticated browser or concurrent-edit version control.'}
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
