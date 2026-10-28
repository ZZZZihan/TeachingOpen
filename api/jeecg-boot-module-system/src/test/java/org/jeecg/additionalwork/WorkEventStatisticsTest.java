package org.jeecg.additionalwork;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.h2.jdbcx.JdbcDataSource;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.service.*;
import org.jeecg.modules.teaching.entity.*;
import org.jeecg.modules.teaching.mapper.*;
import org.jeecg.modules.teaching.service.*;
import org.jeecg.modules.teaching.service.impl.*;
import org.jeecg.modules.teaching.vo.StudentWorkSubmission;
import org.junit.Before;
import org.junit.Test;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.mybatis.spring.transaction.SpringManagedTransactionFactory;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.*;
import java.util.concurrent.*;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Actual SQL/transactions and production ledger mapper, plus real business services.
 * H2 is not a substitute for the HTTP/MySQL migration and failure probes. */
public class WorkEventStatisticsTest {
    private JdbcTemplate jdbc;
    private TransactionInterceptor transactions;
    private ITeachingWorkService grading;
    private TeachingWorkSubmissionService submission;
    private TeachingDepartDayLogServiceImpl dailyTarget;
    private LegacyUnitViewMarkerStore redis;
    private TeachingWorkMapper workMapper;

    @Before public void setup() throws Exception {
        JdbcDataSource data = new JdbcDataSource();
        data.setURL("jdbc:h2:mem:"+UUID.randomUUID()+";MODE=MySQL;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=15000");
        jdbc = new JdbcTemplate(data);
        jdbc.execute("CREATE TABLE sys_user(id VARCHAR(64) PRIMARY KEY)");
        jdbc.update("INSERT INTO sys_user VALUES('student-a')");
        jdbc.execute("CREATE TABLE sys_depart(id VARCHAR(64) PRIMARY KEY,depart_name VARCHAR(64),del_flag VARCHAR(1))");
        jdbc.execute("CREATE TABLE teaching_work(id VARCHAR(64) PRIMARY KEY,user_id VARCHAR(64),depart_id VARCHAR(64),course_id VARCHAR(64),additional_id VARCHAR(64),work_name VARCHAR(64),work_status VARCHAR(4),work_file VARCHAR(64),work_type VARCHAR(4),del_flag INT)");
        jdbc.execute("CREATE TABLE teaching_work_correct(id VARCHAR(64) PRIMARY KEY,work_id VARCHAR(64),score INT,comment VARCHAR(200))");
        jdbc.execute("CREATE TABLE teaching_work_comment(id VARCHAR(64) PRIMARY KEY,work_id VARCHAR(64),comment VARCHAR(200))");
        jdbc.execute("CREATE TABLE sys_data_log(id VARCHAR(64) PRIMARY KEY,data_id VARCHAR(64),content CLOB)");
        jdbc.execute("CREATE TABLE teaching_depart_day_log(id VARCHAR(64) PRIMARY KEY,depart_id VARCHAR(64),depart_name VARCHAR(64),create_time DATE,unit_open_count INT,course_work_assign_count INT,additional_work_assign_count INT,course_work_correct_count INT,additional_work_correct_count INT,course_work_submit_count INT,additional_work_submit_count INT)");
        jdbc.execute("CREATE TABLE teaching_work_event(work_id VARCHAR(64),event_type VARCHAR(32),depart_id VARCHAR(64) NOT NULL,event_state VARCHAR(32) NOT NULL,counted_day DATE,observed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,PRIMARY KEY(work_id,event_type),CHECK(event_type IN ('SUBMIT','CORRECT')),CHECK((event_state='COUNTED' AND counted_day IS NOT NULL) OR (event_state IN ('LEGACY_REVIEW','LEGACY_UNRESOLVED','READY') AND counted_day IS NULL)))");
        jdbc.execute("CREATE TABLE teaching_work_event_cutover(id INT PRIMARY KEY)");
        jdbc.update("INSERT INTO teaching_work_event_cutover VALUES(1)");
        jdbc.update("INSERT INTO sys_depart VALUES('class-a','合成班级','0')");
        jdbc.update("INSERT INTO teaching_work VALUES('work-a','student-a','class-a','unit-a','','original','1','file-a','2',0)");
        SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
        factory.setDataSource(data); factory.setTransactionFactory(new SpringManagedTransactionFactory());
        factory.setMapperLocations(new ClassPathResource[]{new ClassPathResource("org/jeecg/modules/teaching/mapper/xml/TeachingDepartDayLogMapper.xml")});
        TeachingDepartDayLogMapper logs = new SqlSessionTemplate(factory.getObject()).getMapper(TeachingDepartDayLogMapper.class);
        transactions = new TransactionInterceptor(new DataSourceTransactionManager(data),new AnnotationTransactionAttributeSource());
        workMapper=mock(TeachingWorkMapper.class);
        when(workMapper.selectOne(any())).thenAnswer(call -> {
            QueryWrapper<TeachingWork> q=call.getArgument(0); q.getSqlSegment();
            return readWork(q.getParamNameValuePairs().values().iterator().next().toString(),true);
        });
        when(workMapper.updateById(any())).thenAnswer(call -> updateWork(call.getArgument(0)));
        ISysDepartService departments=mock(ISysDepartService.class);
        when(departments.getOne(any())).thenAnswer(call -> jdbc.queryForObject("SELECT * FROM sys_depart WHERE id='class-a' FOR UPDATE",(rs,n)->{
            SysDepart row=new SysDepart();row.setId(rs.getString("id"));row.setDepartName(rs.getString("depart_name"));return row;
        }));
        redis=mock(LegacyUnitViewMarkerStore.class);
        when(redis.contains(anyString(),anyString())).thenThrow(new IllegalStateException("Redis unavailable"));
        dailyTarget=new TeachingDepartDayLogServiceImpl();
        ReflectionTestUtils.setField(dailyTarget,"baseMapper",logs);
        ReflectionTestUtils.setField(dailyTarget,"sysDepartService",departments);
        ReflectionTestUtils.setField(dailyTarget,"works",workMapper);
        ReflectionTestUtils.setField(dailyTarget,"legacyUnitViews",redis);
        ReflectionTestUtils.setField(dailyTarget,"clock",Clock.fixed(Instant.parse("2026-10-11T16:00:00Z"),ZoneOffset.UTC));
        ITeachingDepartDayLogService daily=(ITeachingDepartDayLogService)proxy(dailyTarget);
        TeachingAccessService access=mock(TeachingAccessService.class);
        TeachingWorkCorrectMapper corrections=mock(TeachingWorkCorrectMapper.class);
        doAnswer(call -> {jdbc.update("DELETE FROM teaching_work_correct WHERE work_id=?",(Object)call.getArgument(0));return null;}).when(corrections).deleteByMainId(anyString());
        when(corrections.insert(any())).thenAnswer(call->{TeachingWorkCorrect row=call.getArgument(0);return jdbc.update("INSERT INTO teaching_work_correct VALUES(?,?,?,?)",UUID.randomUUID().toString(),row.getWorkId(),row.getScore(),row.getComment());});
        TeachingWorkCommentMapper comments=mock(TeachingWorkCommentMapper.class);
        doAnswer(call->{jdbc.update("DELETE FROM teaching_work_comment WHERE work_id=?",(Object)call.getArgument(0));return null;}).when(comments).deleteByMainId(anyString());
        when(comments.insert(any())).thenAnswer(call->{TeachingWorkComment row=call.getArgument(0);return jdbc.update("INSERT INTO teaching_work_comment VALUES(?,?,?)",UUID.randomUUID().toString(),row.getWorkId(),row.getComment());});
        TeachingWorkServiceImpl target=new TeachingWorkServiceImpl();
        ReflectionTestUtils.setField(target,"teachingWorkMapper",workMapper);
        ReflectionTestUtils.setField(target,"teachingAccessService",access);
        ReflectionTestUtils.setField(target,"teachingWorkCorrectMapper",corrections);
        ReflectionTestUtils.setField(target,"teachingWorkCommentMapper",comments);
        ReflectionTestUtils.setField(target,"dailyLog",daily);
        ReflectionTestUtils.setField(target,"attachmentAccess",mock(TeachingWorkAttachmentAccessService.class));
        grading=(ITeachingWorkService)proxy(target);

        TeachingWorkSubmissionService submitTarget=new TeachingWorkSubmissionService();
        SysUserMapper users=mock(SysUserMapper.class);when(users.selectOne(any())).thenAnswer(call->{
            jdbc.queryForObject("SELECT id FROM sys_user WHERE id='student-a' FOR UPDATE",String.class);
            return new SysUser().setId("student-a").setStatus(1).setDelFlag(0);
        });
        ReflectionTestUtils.setField(submitTarget,"users",users);
        LoginUser student=new LoginUser();student.setId("student-a");student.setUsername("student-a");when(access.currentUser()).thenReturn(student);
        ITeachingWorkService works=mock(ITeachingWorkService.class);
        when(works.list(any())).thenAnswer(call->Collections.singletonList(readWork("work-a",true)));
        when(works.updateById(any())).thenAnswer(call->updateWork(call.getArgument(0))==1);
        when(works.getById(anyString())).thenAnswer(call->readWork(call.getArgument(0),false));
        ITeachingCourseUnitService units=mock(ITeachingCourseUnitService.class);
        TeachingCourseUnit unit=new TeachingCourseUnit();unit.setId("unit-a");unit.setCourseId("course-a");unit.setDelFlag(0);when(units.getById(anyString())).thenReturn(unit);
        ITeachingCourseService courses=mock(ITeachingCourseService.class);
        TeachingCourse course=new TeachingCourse();course.setId("course-a");course.setDelFlag(0);when(courses.getById(anyString())).thenReturn(course);
        ITeachingCourseDeptService bindings=mock(ITeachingCourseDeptService.class);
        TeachingCourseDept binding=new TeachingCourseDept();binding.setDeptId("class-a");when(bindings.list(any())).thenReturn(Collections.singletonList(binding));
        ISysUserDepartService memberships=mock(ISysUserDepartService.class);when(memberships.userDepartIds(anyString())).thenReturn(Collections.singletonList("class-a"));
        ISysDataLogService history=mock(ISysDataLogService.class);
        doAnswer(call->{jdbc.update("INSERT INTO sys_data_log VALUES(?,?,?)",UUID.randomUUID().toString(),call.getArgument(1),call.getArgument(2));return null;}).when(history).addDataLog(anyString(),anyString(),anyString());
        Object[][] fields={{"access",access},{"works",works},{"units",units},{"courses",courses},{"courseDeparts",bindings},{"userDeparts",memberships},{"attachmentAccess",mock(TeachingWorkAttachmentAccessService.class)},{"history",history},{"dailyLog",daily}};
        for(Object[] field:fields)ReflectionTestUtils.setField(submitTarget,(String)field[0],field[1]);
        submission=(TeachingWorkSubmissionService)proxy(submitTarget);
    }

    private Object proxy(Object target){ProxyFactory factory=new ProxyFactory(target);factory.addAdvice(transactions);return factory.getProxy();}
    private TeachingWork readWork(String id,boolean lock){List<TeachingWork> rows=jdbc.query("SELECT * FROM teaching_work WHERE id=?"+(lock?" FOR UPDATE":""),(rs,n)->{
        TeachingWork work=new TeachingWork();work.setId(rs.getString("id"));work.setUserId(rs.getString("user_id"));work.setDepartId(rs.getString("depart_id"));work.setCourseId(rs.getString("course_id"));work.setAdditionalId(rs.getString("additional_id"));work.setWorkName(rs.getString("work_name"));work.setWorkStatus(rs.getString("work_status"));work.setWorkFile(rs.getString("work_file"));work.setWorkType(rs.getString("work_type"));work.setDelFlag(rs.getInt("del_flag"));return work;
    },id);return rows.isEmpty()?null:rows.get(0);}
    private int updateWork(TeachingWork work){return jdbc.update("UPDATE teaching_work SET work_name=COALESCE(?,work_name),work_status=COALESCE(?,work_status) WHERE id=?",work.getWorkName(),work.getWorkStatus(),work.getId());}
    private void grade(String name,Integer score,String comment){TeachingWork work=new TeachingWork();work.setId("work-a");work.setWorkName(name);work.setWorkStatus("2");TeachingWorkCorrect feedback=new TeachingWorkCorrect();feedback.setScore(score);feedback.setComment(comment);grading.updateMain(work,Collections.singletonList(feedback),null);}
    private void submit(){StudentWorkSubmission request=new StudentWorkSubmission();request.setId("work-a");request.setWorkName("submitted");request.setWorkStatus("1");submission.submit(request);}
    private int count(String table){return jdbc.queryForObject("SELECT COUNT(*) FROM "+table,Integer.class);}
    private int total(String column){return jdbc.queryForObject("SELECT COALESCE(SUM("+column+"),0) FROM teaching_depart_day_log",Integer.class);}
    private List<String> snapshot(){List<String> rows=new ArrayList<>();for(String table:Arrays.asList("teaching_work","teaching_work_correct","teaching_work_comment","sys_data_log","teaching_work_event","teaching_depart_day_log"))rows.add(jdbc.queryForList("SELECT * FROM "+table+" ORDER BY 1").toString());return rows;}
    private void fails(Runnable operation){try{operation.run();fail("must fail");}catch(RuntimeException expected){}}
    private void concurrent(Runnable operation)throws Exception{int n=8;ExecutorService pool=Executors.newFixedThreadPool(n);CountDownLatch ready=new CountDownLatch(n),go=new CountDownLatch(1);List<Future<?>> tasks=new ArrayList<>();try{for(int i=0;i<n;i++)tasks.add(pool.submit(()->{ready.countDown();if(!go.await(10,TimeUnit.SECONDS))throw new AssertionError();operation.run();return null;}));assertTrue(ready.await(10,TimeUnit.SECONDS));go.countDown();for(Future<?> task:tasks)task.get(25,TimeUnit.SECONDS);}finally{go.countDown();pool.shutdownNow();}}

    @Test public void gradingSqlFailureRollsBackParentFeedbackEventAndStats(){
        List<String> before=snapshot();jdbc.execute("ALTER TABLE teaching_depart_day_log ADD CONSTRAINT fail_grade CHECK(course_work_correct_count=0)");
        fails(()->grade("must rollback",0,"valid zero"));assertEquals(before,snapshot());
        jdbc.execute("ALTER TABLE teaching_depart_day_log DROP CONSTRAINT fail_grade");grade("accepted",0,"valid zero");grade("retry",5,"updated");
        assertEquals(1,total("course_work_correct_count"));assertEquals(1,count("teaching_work_event"));assertEquals(Integer.valueOf(5),jdbc.queryForObject("SELECT score FROM teaching_work_correct",Integer.class));
    }
    @Test public void metadataStatusAndBlankFeedbackDoNotCount(){
        TeachingWork work=new TeachingWork();work.setId("work-a");work.setWorkName("renamed");work.setWorkStatus("2");grading.updateMain(work,null,null);grading.updateMain(work,Collections.emptyList(),null);grade("blank",null,"  ");
        assertEquals(0,count("teaching_work_event"));assertEquals(0,count("teaching_depart_day_log"));grade("comment only",null,"good work");assertEquals(1,total("course_work_correct_count"));
    }
    @Test public void concurrentGradingsCountOnlyOnce()throws Exception{concurrent(()->grade("concurrent",0,"feedback"));assertEquals(1,count("teaching_work_event"));assertEquals(1,total("course_work_correct_count"));assertEquals(1,count("teaching_work_correct"));}
    @Test public void studentSqlFailureRollsBackHistoryWorkAndEvent(){
        List<String> before=snapshot();jdbc.execute("ALTER TABLE teaching_depart_day_log ADD CONSTRAINT fail_submit CHECK(course_work_submit_count=0)");fails(this::submit);assertEquals(before,snapshot());
        jdbc.execute("ALTER TABLE teaching_depart_day_log DROP CONSTRAINT fail_submit");submit();submit();assertEquals(1,total("course_work_submit_count"));assertEquals(1,count("teaching_work_event"));assertEquals(2,count("sys_data_log"));
    }
    @Test public void concurrentSubmissionsAndLaterRetriesIgnoreRedis()throws Exception{concurrent(this::submit);submit();assertEquals(1,total("course_work_submit_count"));assertEquals(1,count("teaching_work_event"));verifyZeroInteractions(redis);}
    @Test public void submitAndCorrectHaveIndependentKeysAndSameShanghaiDay(){submit();grade("graded",4,"ok");assertEquals(2,count("teaching_work_event"));assertEquals(1,total("course_work_submit_count"));assertEquals(1,total("course_work_correct_count"));assertEquals("2026-10-12",jdbc.queryForObject("SELECT DISTINCT CAST(counted_day AS VARCHAR) FROM teaching_work_event",String.class));assertEquals("2026-10-12",jdbc.queryForObject("SELECT CAST(create_time AS VARCHAR) FROM teaching_depart_day_log",String.class));}
    @Test public void staleStudentSaveAndSubmitPreserveGradedWorkAndFeedback(){
        submit();grade("graded",0,"first line\nsecond line");
        for(String current:Arrays.asList("2","3","4")){
            jdbc.update("UPDATE teaching_work SET work_status=?",current);
            for(String requested:Arrays.asList("0","1")){
                List<String> before=snapshot();
                StudentWorkSubmission request=new StudentWorkSubmission();request.setId("work-a");
                request.setWorkName("stale overwrite");request.setWorkFile("new-file");request.setWorkStatus(requested);
                try{submission.submit(request);fail("A reviewed work must reject the stale editor");}
                catch(JeecgBootException expected){assertTrue(expected.getMessage().contains("作业状态已变化"));}
                assertEquals(before,snapshot());
            }
        }
        assertEquals(1,total("course_work_submit_count"));assertEquals(1,total("course_work_correct_count"));
    }
    @Test public void unknownStoredStatusCannotBeChangedByStudent(){
        for(String status:Arrays.asList(null,"","9")){
            jdbc.update("UPDATE teaching_work SET work_status=?",status);
            List<String> before=snapshot();
            try{submit();fail("Unknown status must not become an editable work");}
            catch(JeecgBootException expected){assertTrue(expected.getMessage().contains("作业状态已变化"));}
            assertEquals(before,snapshot());
        }
    }
    @Test public void additionalWorkUsesOnlyItsOwnCounter(){jdbc.update("UPDATE teaching_work SET course_id='',additional_id='assignment-a'");grade("additional",0,"zero");assertEquals(1,total("additional_work_correct_count"));assertEquals(0,total("course_work_correct_count"));}
    @Test public void unresolvedLegacyMustBeExplicitlyReviewedBeforeFutureFirstGrade(){
        jdbc.update("INSERT INTO teaching_work_event(work_id,event_type,depart_id,event_state) VALUES('work-a','CORRECT','class-a','LEGACY_REVIEW')");List<String> before=snapshot();fails(()->grade("blocked",4,"not committed"));assertEquals(before,snapshot());
        jdbc.update("UPDATE teaching_work_event SET event_state='READY'");grade("first genuine grade",4,"ok");assertEquals(1,total("course_work_correct_count"));assertEquals("COUNTED",jdbc.queryForObject("SELECT event_state FROM teaching_work_event",String.class));
    }
    @Test public void reviewedLegacyPreservesOldAggregateWithoutInventingADate(){jdbc.update("INSERT INTO teaching_work_event(work_id,event_type,depart_id,event_state) VALUES('work-a','CORRECT','class-a','LEGACY_UNRESOLVED')");grade("updated",3,"ok");assertEquals(0,count("teaching_depart_day_log"));assertNull(jdbc.queryForObject("SELECT counted_day FROM teaching_work_event",java.sql.Date.class));verifyZeroInteractions(redis);}
    @Test public void ledgerFailureRollsBackWorkAndFeedback(){jdbc.execute("ALTER TABLE teaching_work_event ADD CONSTRAINT reject_event CHECK(event_type='SUBMIT')");List<String> before=snapshot();fails(()->grade("blocked",4,"not committed"));assertEquals(before,snapshot());}
    @Test public void incompleteCutoverCannotRecountOldWorks(){jdbc.update("DELETE FROM teaching_work_event_cutover");List<String> before=snapshot();fails(this::submit);fails(()->grade("blocked",4,"not committed"));assertEquals(before,snapshot());}
}
