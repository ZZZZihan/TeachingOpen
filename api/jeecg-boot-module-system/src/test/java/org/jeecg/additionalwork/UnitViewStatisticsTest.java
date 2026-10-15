package org.jeecg.additionalwork;

import org.apache.ibatis.session.SqlSessionFactory;
import org.apache.shiro.authz.UnauthorizedException;
import org.h2.jdbcx.JdbcDataSource;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.service.ISysDepartService;
import org.jeecg.modules.teaching.entity.TeachingCourseUnit;
import org.jeecg.modules.teaching.entity.TeachingCourse;
import org.jeecg.modules.teaching.enums.UnitViewLogResult;
import org.jeecg.modules.teaching.mapper.TeachingCourseUnitMapper;
import org.jeecg.modules.teaching.mapper.TeachingCourseMapper;
import org.jeecg.modules.teaching.mapper.TeachingDepartDayLogMapper;
import org.jeecg.modules.teaching.service.ITeachingDepartDayLogService;
import org.jeecg.modules.teaching.service.LegacyUnitViewMarkerStore;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.jeecg.modules.teaching.service.impl.TeachingDepartDayLogServiceImpl;
import org.junit.Before;
import org.junit.Test;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.mybatis.spring.transaction.SpringManagedTransactionFactory;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.mockito.AdditionalAnswers.delegatesTo;

/** Real Spring transactions and production mapper SQL; H2 does not replace MySQL migration acceptance. */
public class UnitViewStatisticsTest {
    private JdbcTemplate jdbc;
    private TeachingDepartDayLogServiceImpl target;
    private ITeachingDepartDayLogService service;
    private TeachingDepartDayLogMapper logs;
    private TeachingCourseUnitMapper units;
    private TeachingCourseUnitMapper actualUnits;
    private SysUserMapper users;
    private TeachingCourseMapper courses;
    private TeachingAccessService teachingAccess;
    private LegacyUnitViewMarkerStore legacy;
    private SysUser actor;
    private TeachingCourseUnit unit;
    private TeachingCourse course;
    private AtomicBoolean failAfterWrite;
    private AtomicBoolean rejectWrite;

    @Before public void setup() throws Exception {
        JdbcDataSource data = new JdbcDataSource();
        data.setURL("jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=15000");
        jdbc = new JdbcTemplate(data);
        jdbc.execute("CREATE TABLE sys_depart(id VARCHAR(64) PRIMARY KEY,depart_name VARCHAR(64),del_flag VARCHAR(1))");
        jdbc.execute("CREATE TABLE teaching_depart_day_log(id VARCHAR(64) PRIMARY KEY, depart_id VARCHAR(64),depart_name VARCHAR(64),create_time DATE,unit_open_count INT,course_work_assign_count INT,additional_work_assign_count INT,course_work_correct_count INT,additional_work_correct_count INT,course_work_submit_count INT,additional_work_submit_count INT)");
        jdbc.execute("CREATE TABLE teaching_unit_view_event(depart_id VARCHAR(64),unit_id VARCHAR(64),observed_user_id VARCHAR(64) NOT NULL,event_state VARCHAR(32) NOT NULL,counted_day DATE,observed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,PRIMARY KEY(depart_id,unit_id),CHECK((event_state='COUNTED' AND counted_day IS NOT NULL) OR (event_state='LEGACY_UNRESOLVED' AND counted_day IS NULL)))");
        jdbc.execute("CREATE TABLE teaching_course_unit(id VARCHAR(64) PRIMARY KEY,course_id VARCHAR(64),del_flag INT)");
        jdbc.execute("CREATE TABLE teaching_course(id VARCHAR(64) PRIMARY KEY,del_flag INT)");
        jdbc.execute("CREATE TABLE teaching_course_dept(course_id VARCHAR(64),dept_id VARCHAR(64))");
        jdbc.execute("CREATE TABLE sys_user_depart(user_id VARCHAR(64),dep_id VARCHAR(64))");
        jdbc.update("INSERT INTO sys_depart VALUES('class-a','合成班级','0')");
        jdbc.update("INSERT INTO teaching_course VALUES('course-a',0)");
        jdbc.update("INSERT INTO teaching_course_unit VALUES('unit-a','course-a',0)");
        jdbc.update("INSERT INTO teaching_course_dept VALUES('course-a','class-a')");
        jdbc.update("INSERT INTO sys_user_depart VALUES('teacher-a','class-a')");
        SqlSessionFactoryBean factoryBean = new SqlSessionFactoryBean();
        factoryBean.setDataSource(data);
        factoryBean.setTransactionFactory(new SpringManagedTransactionFactory());
        factoryBean.setMapperLocations(new ClassPathResource[] {
                new ClassPathResource("org/jeecg/modules/teaching/mapper/xml/TeachingDepartDayLogMapper.xml"),
                new ClassPathResource("org/jeecg/modules/teaching/mapper/xml/TeachingCourseUnitMapper.xml") });
        SqlSessionFactory factory = factoryBean.getObject();
        assertNotNull(factory);
        SqlSessionTemplate sessions = new SqlSessionTemplate(factory);
        TeachingDepartDayLogMapper realLogs = sessions.getMapper(TeachingDepartDayLogMapper.class);
        actualUnits = sessions.getMapper(TeachingCourseUnitMapper.class);
        logs = mock(TeachingDepartDayLogMapper.class, delegatesTo(realLogs));
        failAfterWrite = new AtomicBoolean(); rejectWrite = new AtomicBoolean();
        doAnswer(call -> {
            if (rejectWrite.get()) return 0;
            int rows = realLogs.insertDayLog(call.getArgument(0), call.getArgument(1));
            if (failAfterWrite.get()) throw new JeecgBootException("合成事务故障");
            return rows;
        }).when(logs).insertDayLog(any(), anyString());
        doAnswer(call -> {
            if (rejectWrite.get()) return 0;
            int rows = realLogs.incrementDayCounter(call.getArgument(0), call.getArgument(1), call.getArgument(2), call.getArgument(3));
            if (failAfterWrite.get()) throw new JeecgBootException("合成事务故障");
            return rows;
        }).when(logs).incrementDayCounter(anyString(), anyString(), anyString(), anyString());
        users = mock(SysUserMapper.class); units = mock(TeachingCourseUnitMapper.class);
        courses = mock(TeachingCourseMapper.class); teachingAccess = mock(TeachingAccessService.class);
        legacy = mock(LegacyUnitViewMarkerStore.class);
        actor = new SysUser(); actor.setId("teacher-a"); actor.setStatus(1); actor.setDelFlag(0); actor.setUserIdentity(2);
        unit = new TeachingCourseUnit(); unit.setId("unit-a"); unit.setCourseId("course-a"); unit.setDelFlag(0);
        course = new TeachingCourse(); course.setId("course-a"); course.setDelFlag(0);
        when(courses.selectById("course-a")).thenAnswer(call -> course);
        when(users.selectById(anyString())).thenAnswer(call -> {
            SysUser copy = new SysUser(); copy.setId(call.getArgument(0)); copy.setStatus(actor.getStatus());
            copy.setDelFlag(actor.getDelFlag()); copy.setUserIdentity(actor.getUserIdentity()); return copy;
        });
        when(units.selectById(anyString())).thenAnswer(call -> {
            TeachingCourseUnit copy = new TeachingCourseUnit(); copy.setId(call.getArgument(0));
            copy.setDelFlag(unit.getDelFlag()); copy.setCourseId(unit.getCourseId()); return copy;
        });
        when(units.getUserDepartIdByUnitId(anyString(), anyString())).thenReturn("class-a");
        ISysDepartService departments = mock(ISysDepartService.class);
        when(departments.getOne(any())).thenAnswer(call -> {
            List<SysDepart> rows = jdbc.query("SELECT id,depart_name,del_flag FROM sys_depart WHERE id='class-a' AND del_flag='0' FOR UPDATE", (rs,n) -> {
                SysDepart row = new SysDepart(); row.setId(rs.getString(1)); row.setDepartName(rs.getString(2)); row.setDelFlag(rs.getString(3)); return row;
            });
            return rows.isEmpty() ? null : rows.get(0);
        });
        target = new TeachingDepartDayLogServiceImpl();
        ReflectionTestUtils.setField(target,"baseMapper",logs);
        ReflectionTestUtils.setField(target,"sysDepartService",departments);
        ReflectionTestUtils.setField(target,"users",users);
        ReflectionTestUtils.setField(target,"units",units);
        ReflectionTestUtils.setField(target,"courses",courses);
        ReflectionTestUtils.setField(target,"teachingAccessService",teachingAccess);
        ReflectionTestUtils.setField(target,"legacyUnitViews",legacy);
        setTime("2026-10-10T16:00:00Z");
        TransactionInterceptor transactions = new TransactionInterceptor(new DataSourceTransactionManager(data), new AnnotationTransactionAttributeSource());
        ProxyFactory proxy = new ProxyFactory(target); proxy.addAdvice(transactions);
        service = (ITeachingDepartDayLogService) proxy.getProxy();
    }

    private void setTime(String time) { ReflectionTestUtils.setField(target,"clock",Clock.fixed(Instant.parse(time), ZoneOffset.UTC)); }
    private int events() { return jdbc.queryForObject("SELECT COUNT(*) FROM teaching_unit_view_event",Integer.class); }
    private int total() { return jdbc.queryForObject("SELECT COALESCE(SUM(unit_open_count),0) FROM teaching_depart_day_log",Integer.class); }
    private void noWrites() { assertEquals(0,events()); assertEquals(0,total()); }
    private void fails(Runnable action, Class<? extends RuntimeException> expected) {
        try { action.run(); fail("request should fail"); } catch (RuntimeException failure) { assertTrue(failure.toString(),expected.isInstance(failure)); }
    }

    @Test public void firstViewCommitsEventAndCounterOnOneShanghaiDate() {
        assertEquals(UnitViewLogResult.COUNTED,service.recordUnitView("teacher-a","unit-a"));
        assertEquals(1,events()); assertEquals(1,total());
        assertEquals("2026-10-11",jdbc.queryForObject("SELECT CAST(counted_day AS VARCHAR) FROM teaching_unit_view_event",String.class));
        assertEquals("2026-10-11",jdbc.queryForObject("SELECT CAST(create_time AS VARCHAR) FROM teaching_depart_day_log",String.class));
    }

    @Test public void failureAfterFirstCounterWriteRollsBackBothAndRetryCountsOnce() {
        failAfterWrite.set(true);
        fails(() -> service.recordUnitView("teacher-a","unit-a"),JeecgBootException.class); noWrites();
        failAfterWrite.set(false);
        assertEquals(UnitViewLogResult.COUNTED,service.recordUnitView("teacher-a","unit-a"));
        assertEquals(UnitViewLogResult.ALREADY_COUNTED,service.recordUnitView("teacher-a","unit-a"));
        assertEquals(1,events()); assertEquals(1,total());
    }

    @Test public void failureAfterExistingCounterUpdateAlsoRollsBackTheNewEvent() {
        service.recordUnitView("teacher-a","unit-a");
        failAfterWrite.set(true);
        fails(() -> service.recordUnitView("teacher-a","unit-b"),JeecgBootException.class);
        assertEquals(1,events()); assertEquals(1,total());
        failAfterWrite.set(false);
        assertEquals(UnitViewLogResult.COUNTED,service.recordUnitView("teacher-a","unit-b"));
        assertEquals(2,events()); assertEquals(2,total());
    }

    @Test public void zeroAffectedCounterRowsAbortAndLeaveNoCompletedMarker() {
        rejectWrite.set(true);
        fails(() -> service.recordUnitView("teacher-a","unit-a"),JeecgBootException.class); noWrites();
        rejectWrite.set(false); service.recordUnitView("teacher-a","unit-a"); assertEquals(1,total());
    }

    @Test public void committedRetryNeedsNoRedisAndSurvivesResponseLoss() {
        service.recordUnitView("teacher-a","unit-a");
        when(legacy.contains(anyString(),anyString())).thenThrow(new IllegalStateException("合成Redis断连"));
        assertEquals(UnitViewLogResult.ALREADY_COUNTED,service.recordUnitView("teacher-a","unit-a"));
        assertEquals(1,total()); verify(legacy,times(1)).contains("class-a","unit-a");
    }

    @Test public void concurrentFirstViewsCommitOneEventAndOneCounter() throws Exception {
        int attempts=12;
        ExecutorService pool=Executors.newFixedThreadPool(attempts);
        CountDownLatch ready=new CountDownLatch(attempts), start=new CountDownLatch(1);
        List<Future<UnitViewLogResult>> responses=new ArrayList<>();
        try {
            for(int i=0;i<attempts;i++) responses.add(pool.submit(() -> { ready.countDown(); assertTrue(start.await(10,TimeUnit.SECONDS)); return service.recordUnitView("teacher-a","unit-a"); }));
            assertTrue(ready.await(10,TimeUnit.SECONDS)); start.countDown();
            int counted=0;
            for(Future<UnitViewLogResult> response:responses) if(response.get(30,TimeUnit.SECONDS)==UnitViewLogResult.COUNTED) counted++;
            assertEquals(1,counted); assertEquals(1,events()); assertEquals(1,total());
            assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM teaching_depart_day_log",Integer.class).intValue());
            verify(legacy,times(1)).contains("class-a","unit-a");
        } finally { start.countDown(); pool.shutdownNow(); }
    }

    @Test public void lifetimeDeduplicationSpansDaysAndMembersInTheSameClass() {
        service.recordUnitView("teacher-a","unit-a"); setTime("2026-11-10T16:00:00Z");
        assertEquals(UnitViewLogResult.ALREADY_COUNTED,service.recordUnitView("teacher-b","unit-a"));
        assertEquals(1,events()); assertEquals(1,total());
    }

    @Test public void theSameUnitInAnotherClassHasItsOwnEvent() {
        service.recordUnitView("teacher-a","unit-a");
        jdbc.update("INSERT INTO sys_depart VALUES('class-b','第二合成班级','0')");
        when(units.getUserDepartIdByUnitId(anyString(),anyString())).thenReturn("class-b");
        ISysDepartService secondClass = mock(ISysDepartService.class);
        when(secondClass.getOne(any())).thenAnswer(call -> jdbc.queryForObject(
                "SELECT id,depart_name FROM sys_depart WHERE id='class-b' FOR UPDATE", (rs,n) -> {
                    SysDepart row = new SysDepart(); row.setId(rs.getString(1)); row.setDepartName(rs.getString(2)); return row;
                }));
        ReflectionTestUtils.setField(target,"sysDepartService",secondClass);
        assertEquals(UnitViewLogResult.COUNTED,service.recordUnitView("teacher-b","unit-a"));
        assertEquals(2,events()); assertEquals(2,total());
    }

    @Test public void legacyMarkersRemainUnresolvedEvenIfRedisIsLaterCleared() {
        when(legacy.contains("class-a","unit-a")).thenReturn(true);
        assertEquals(UnitViewLogResult.LEGACY_UNRESOLVED,service.recordUnitView("teacher-a","unit-a"));
        assertEquals(1,events()); assertEquals(0,total());
        assertNull(jdbc.queryForObject("SELECT counted_day FROM teaching_unit_view_event",java.sql.Date.class));
        doReturn(false).when(legacy).contains("class-a","unit-a");
        assertEquals(UnitViewLogResult.LEGACY_UNRESOLVED,service.recordUnitView("teacher-b","unit-a"));
        assertEquals(0,total()); verify(legacy,times(1)).contains("class-a","unit-a");
    }

    @Test public void failedLegacyLookupIsRetryableAndCannotInventANewCount() {
        when(legacy.contains("class-a","unit-a")).thenThrow(new IllegalStateException("合成Redis断连"));
        fails(() -> service.recordUnitView("teacher-a","unit-a"),IllegalStateException.class); noWrites();
        doReturn(false).when(legacy).contains("class-a","unit-a");
        assertEquals(UnitViewLogResult.COUNTED,service.recordUnitView("teacher-a","unit-a")); assertEquals(1,total());
    }

    @Test public void currentActorStateAndNullIdentityAreSafe() {
        actor.setUserIdentity(null);
        assertEquals(UnitViewLogResult.NOT_APPLICABLE,service.recordUnitView("teacher-a","unit-a")); noWrites();
        actor.setUserIdentity(1);
        assertEquals(UnitViewLogResult.NOT_APPLICABLE,service.recordUnitView("teacher-a","unit-a")); noWrites();
        actor.setStatus(2);
        fails(() -> service.recordUnitView("teacher-a","unit-a"),UnauthorizedException.class); noWrites();
        actor.setStatus(1); actor.setDelFlag(1);
        fails(() -> service.recordUnitView("teacher-a","unit-a"),UnauthorizedException.class); noWrites();
        when(users.selectById("teacher-a")).thenReturn(null);
        fails(() -> service.recordUnitView("teacher-a","unit-a"),UnauthorizedException.class); noWrites();
        verifyZeroInteractions(legacy);
    }

    @Test public void invalidOrDeletedUnitAndDeletedDepartmentCannotWrite() {
        fails(() -> service.recordUnitView(null,"unit-a"),JeecgBootException.class);
        fails(() -> service.recordUnitView("teacher-a","unit a"),JeecgBootException.class);
        unit.setDelFlag(1);
        fails(() -> service.recordUnitView("teacher-a","unit-a"),JeecgBootException.class);
        unit.setDelFlag(0);
        when(units.selectById("UNIT-A")).thenReturn(unit);
        fails(() -> service.recordUnitView("teacher-a","UNIT-A"),JeecgBootException.class);
        jdbc.update("UPDATE sys_depart SET del_flag='1'");
        fails(() -> service.recordUnitView("teacher-a","unit-a"),JeecgBootException.class); noWrites();
        verifyZeroInteractions(legacy);
    }

    @Test public void readablePreviewWithoutAnApplicableClassSucceedsWithoutInventingStatistics() {
        when(units.getUserDepartIdByUnitId("teacher-a","unit-a")).thenReturn(null);
        assertEquals(UnitViewLogResult.NOT_APPLICABLE,service.recordUnitView("teacher-a","unit-a"));
        assertEquals(UnitViewLogResult.NOT_APPLICABLE,service.recordUnitView("teacher-a","unit-a"));
        noWrites(); verify(teachingAccess,times(2)).requireCourse("course-a"); verifyZeroInteractions(legacy);
    }

    @Test public void courseReadDenialPrecedesBothTeacherAndStudentStatisticsBranches() {
        doThrow(new UnauthorizedException("合成跨班私有课程")).when(teachingAccess).requireCourse("course-a");
        fails(() -> service.recordUnitView("teacher-a","unit-a"),UnauthorizedException.class);
        actor.setUserIdentity(1);
        fails(() -> service.recordUnitView("teacher-a","unit-a"),UnauthorizedException.class);
        actor.setUserIdentity(null);
        fails(() -> service.recordUnitView("teacher-a","unit-a"),UnauthorizedException.class);
        noWrites(); verifyZeroInteractions(legacy);
        verify(units,never()).getUserDepartIdByUnitId(anyString(),anyString());
    }

    @Test public void aDeletedOrMissingCourseCannotBecomeASuccessfulNoopForAnyIdentity() {
        for (Integer identity : new Integer[] {2,1,null}) {
            actor.setUserIdentity(identity);
            course.setDelFlag(1);
            fails(() -> service.recordUnitView("teacher-a","unit-a"),JeecgBootException.class);
            when(courses.selectById("course-a")).thenReturn(null);
            fails(() -> service.recordUnitView("teacher-a","unit-a"),JeecgBootException.class);
            when(courses.selectById("course-a")).thenAnswer(call -> course);
        }
        noWrites(); verifyZeroInteractions(teachingAccess,legacy);
    }

    @Test public void studentValidatesTheUnitBeforeReturningANonCountingResponse() {
        actor.setUserIdentity(1);
        unit.setDelFlag(1);
        fails(() -> service.recordUnitView("teacher-a","unit-a"),JeecgBootException.class);
        unit.setDelFlag(0);
        assertEquals(UnitViewLogResult.NOT_APPLICABLE,service.recordUnitView("teacher-a","unit-a"));
        noWrites(); verify(teachingAccess).requireCourse("course-a"); verifyZeroInteractions(legacy);
    }

    @Test public void productionClassAccessQueryRequiresCurrentMembershipAndLiveUnitCourseDepartment() {
        assertEquals("class-a",actualUnits.getUserDepartIdByUnitId("teacher-a","unit-a"));
        assertNull(actualUnits.getUserDepartIdByUnitId("outsider","unit-a"));
        assertNull(actualUnits.getUserDepartIdByUnitId("teacher-a","missing"));
        jdbc.update("UPDATE teaching_course_unit SET del_flag=1"); assertNull(actualUnits.getUserDepartIdByUnitId("teacher-a","unit-a"));
        jdbc.update("UPDATE teaching_course_unit SET del_flag=0");
        jdbc.update("UPDATE teaching_course SET del_flag=1"); assertNull(actualUnits.getUserDepartIdByUnitId("teacher-a","unit-a"));
        jdbc.update("UPDATE teaching_course SET del_flag=0");
        jdbc.update("UPDATE sys_depart SET del_flag='1'"); assertNull(actualUnits.getUserDepartIdByUnitId("teacher-a","unit-a"));
        jdbc.update("UPDATE sys_depart SET del_flag='0'");
        jdbc.update("DELETE FROM sys_user_depart"); assertNull(actualUnits.getUserDepartIdByUnitId("teacher-a","unit-a"));
    }

    @Test public void legacyBridgeUsesExistingSetWithoutSwallowingErrorsOrWriting() {
        RedisTemplate<String,Object> redis=mock(RedisTemplate.class);
        SetOperations<String,Object> sets=mock(SetOperations.class); when(redis.opsForSet()).thenReturn(sets);
        LegacyUnitViewMarkerStore bridge=new LegacyUnitViewMarkerStore(redis);
        when(sets.isMember("departLog:unitView:class-a","unit-a")).thenReturn(true,false,null);
        assertTrue(bridge.contains("class-a","unit-a")); assertFalse(bridge.contains("class-a","unit-a"));
        fails(() -> bridge.contains("class-a","unit-a"),JeecgBootException.class);
        when(sets.isMember(anyString(),any())).thenThrow(new IllegalStateException("合成Redis断连"));
        fails(() -> bridge.contains("class-a","unit-a"),IllegalStateException.class);
        verify(sets,times(4)).isMember("departLog:unitView:class-a","unit-a");
        verifyNoMoreInteractions(sets);
    }
}
