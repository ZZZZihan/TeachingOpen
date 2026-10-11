package org.jeecg.infrastructure;

import com.alibaba.fastjson.JSON;
import com.alibaba.druid.pool.DruidDataSource;
import org.jeecg.common.util.dynamic.db.DataSourceCachePool;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import java.sql.*;
import java.util.logging.Logger;
import java.util.concurrent.atomic.AtomicInteger;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayOutputStream;
import java.util.*;
import org.apache.poi.ss.usermodel.*;
import org.apache.shiro.authz.UnauthorizedException;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.h2.jdbcx.JdbcDataSource;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.config.InfrastructureManagementInterceptor;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.jeecg.common.exception.JeecgBootExceptionHandler;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.quartz.controller.QuartzJobController;
import org.jeecg.modules.quartz.entity.QuartzJob;
import org.jeecg.modules.quartz.job.SampleJob;
import org.jeecg.modules.quartz.mapper.QuartzJobMapper;
import org.jeecg.modules.quartz.service.impl.QuartzJobServiceImpl;
import org.jeecg.modules.system.controller.SysDataSourceController;
import org.jeecg.modules.system.entity.*;
import org.jeecg.modules.system.mapper.*;
import org.jeecg.modules.system.service.*;
import org.jeecgframework.poi.excel.ExcelExportUtil;
import org.jeecgframework.poi.excel.def.NormalExcelConstants;
import org.jeecgframework.poi.excel.entity.ExportParams;
import org.junit.*;
import org.mockito.ArgumentCaptor;
import org.quartz.*;
import org.quartz.impl.StdSchedulerFactory;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.context.annotation.ClassPathScanningCandidateComponentProvider;
import org.springframework.core.type.filter.AnnotationTypeFilter;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.web.method.HandlerMethod;
import org.springframework.beans.factory.config.BeanDefinition;
import java.lang.reflect.Method;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.servlet.ModelAndView;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

public class InfrastructureAdministrationTest {
    private SysUserMapper users;
    private SysUserRoleMapper roles;
    private SysDataSourceMapper sources;
    private QuartzJobMapper jobs;
    private Scheduler scheduler;
    private DataSourceCacheInvalidator cache;
    private InfrastructureAccessService access;
    private DataSourceAdministrationService data;
    private QuartzJobServiceImpl quartz;
    private SysDataSourceController dataController;
    private MockMvc http;
    private Subject subject;
    private SysUser actor;
    private SysDataSource stored;
    private QuartzJob scheduled;

    @Before public void setup() {
        users = mock(SysUserMapper.class); roles = mock(SysUserRoleMapper.class);
        sources = mock(SysDataSourceMapper.class); jobs = mock(QuartzJobMapper.class);
        scheduler = mock(Scheduler.class); cache = mock(DataSourceCacheInvalidator.class);
        access = new InfrastructureAccessService(users, roles);
        data = new DataSourceAdministrationService(access, sources, cache);
        quartz = new QuartzJobServiceImpl(access, jobs, scheduler);
        actor = new SysUser().setId("operator").setStatus(1).setDelFlag(0);
        LoginUser principal = new LoginUser(); principal.setId(actor.getId());
        subject = mock(Subject.class); when(subject.getPrincipal()).thenReturn(principal);
        // Even a stale cached dev grant must never be consulted by the boundary.
        when(subject.hasRole(anyString())).thenReturn(true); ThreadContext.bind(subject);
        when(users.selectById(actor.getId())).thenReturn(actor);
        when(roles.getRoleByUserId(actor.getId())).thenReturn(Collections.singletonList("dev"));
        stored = source().setId("source");
        when(sources.selectById("source")).thenReturn(stored);
        when(sources.selectList(any())).thenReturn(Collections.singletonList(stored));
        Page<SysDataSource> page = new Page<>(); page.setRecords(Collections.singletonList(stored)); page.setTotal(1);
        when(sources.selectPage(any(), any())).thenReturn(page);
        when(sources.insert(any())).thenReturn(1); when(sources.updateById(any())).thenReturn(1);
        when(sources.deleteBatchIds(anyCollection())).thenReturn(1);
        scheduled = job(); scheduled.setId("job"); scheduled.setJobClassName(SampleJob.class.getName());
        when(jobs.selectById("job")).thenReturn(scheduled); when(jobs.selectOne(any())).thenReturn(scheduled);
        when(jobs.insert(any())).thenReturn(1); when(jobs.updateById(any())).thenReturn(1);
        when(jobs.deleteBatchIds(anyCollection())).thenReturn(1);
        when(jobs.selectList(any())).thenReturn(Collections.singletonList(scheduled));
        Page<QuartzJob> jobsPage = new Page<>(); jobsPage.setRecords(Collections.singletonList(scheduled)); jobsPage.setTotal(1);
        when(jobs.selectPage(any(), any())).thenReturn(jobsPage);
        dataController = new SysDataSourceController(access, data);
        http = MockMvcBuilders.standaloneSetup(dataController, new QuartzJobController(access, quartz))
                .setControllerAdvice(new JeecgBootExceptionHandler()).addInterceptors(new InfrastructureManagementInterceptor(access)).build();
    }

    @After public void cleanup() { ThreadContext.remove(); RequestContextHolder.resetRequestAttributes(); }

    private SysDataSource source() {
        return new SysDataSource().setCode("fixture_source").setName("Synthetic source").setDbType("1")
                .setDbDriver("com.mysql.jdbc.Driver").setDbUrl("jdbc:mysql://127.0.0.1/synthetic")
                .setDbName("synthetic").setDbUsername("fixture").setDbPassword("synthetic-secret-only");
    }
    private QuartzJob job() {
        QuartzJob value = new QuartzJob(); value.setJobType("sample"); value.setStatus(0);
        value.setCronExpression("0 0 0 1 1 ? 2099"); value.setDescription("Synthetic dormant task");
        return value;
    }
    private List<Runnable> operations() {
        return Arrays.asList(() -> data.page(new Page<>(), null), () -> data.list(null), () -> data.get("source"),
                () -> data.add(source()), () -> data.edit(source().setId("source")),
                () -> data.delete(Collections.singletonList("source")), () -> data.importSources(Collections.singletonList(source())),
                () -> quartz.page(new Page<>(), null), () -> quartz.list(null), () -> quartz.getById("job"),
                () -> quartz.saveAndScheduleJob(job()), () -> quartz.editAndScheduleJob(scheduled),
                () -> quartz.deleteAndStopJobs(Collections.singletonList("job")),
                () -> quartz.pauseJob(SampleJob.class.getName()), () -> quartz.resumeJob(SampleJob.class.getName()),
                () -> quartz.importJobs(Collections.singletonList(job())));
    }
    private void deniedServices() {
        for (Runnable operation : operations()) {
            try { operation.run(); fail("Infrastructure operation accepted"); }
            catch (UnauthorizedException expected) { }
        }
        verifyZeroInteractions(sources, jobs, cache, scheduler);
    }
    private List<MockHttpServletRequestBuilder> requests() {
        return Arrays.asList(
                get("/sys/dataSource/list"), get("/sys/dataSource/options"), get("/sys/dataSource/queryById").param("id", "source"),
                get("/sys/dataSource/exportXls"), post("/sys/dataSource/exportXls"), post("/sys/dataSource/importExcel"),
                post("/sys/dataSource/add").contentType("application/json").content("{}"),
                put("/sys/dataSource/edit").contentType("application/json").content("{}"),
                delete("/sys/dataSource/delete").param("id", "source"), delete("/sys/dataSource/deleteBatch").param("ids", "source,missing"),
                get("/sys/quartzJob/list"), get("/sys/quartzJob/types"), get("/sys/quartzJob/queryById").param("id", "job"),
                get("/sys/quartzJob/exportXls"), post("/sys/quartzJob/exportXls"), post("/sys/quartzJob/importExcel"),
                post("/sys/quartzJob/add").contentType("application/json").content("{}"),
                put("/sys/quartzJob/edit").contentType("application/json").content("{}"),
                delete("/sys/quartzJob/delete").param("id", "job"), delete("/sys/quartzJob/deleteBatch").param("ids", "job,missing"),
                get("/sys/quartzJob/pause").param("jobClassName", SampleJob.class.getName()),
                get("/sys/quartzJob/resume").param("jobClassName", SampleJob.class.getName()));
    }

    @Test public void studentsTeachersAdminsAndStaleDevGrantsCannotReachServices() {
        for (String role : Arrays.asList("student", "teacher", "admin", "DEV", "dev ", "")) {
            when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList(role)); deniedServices();
        }
        when(roles.getRoleByUserId("operator")).thenReturn(null); deniedServices();
        verify(subject, never()).hasRole(anyString());
    }

    @Test public void absentFrozenDeletedAndMismatchedActorsCannotReachServices() {
        when(subject.getPrincipal()).thenReturn(null); deniedServices();
        LoginUser principal = new LoginUser(); when(subject.getPrincipal()).thenReturn(principal); deniedServices();
        principal.setId("operator"); when(users.selectById("operator")).thenReturn(null); deniedServices();
        when(users.selectById("operator")).thenReturn(actor); actor.setStatus(2); deniedServices();
        actor.setStatus(1).setDelFlag(1); deniedServices(); actor.setDelFlag(0).setId("other"); deniedServices();
    }

    @Test public void allControllerEntriesDenyBeforeDatabaseCacheSchedulerOrImportParsing() throws Exception {
        for (String role : Arrays.asList("student", "teacher", "admin")) {
            when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList(role));
            for (MockHttpServletRequestBuilder request : requests()) {
                http.perform(request).andExpect(status().isForbidden()).andExpect(jsonPath("$.success").value(false))
                        .andExpect(jsonPath("$.code").value(403));
            }
        }
        verifyZeroInteractions(sources, jobs, cache, scheduler);
    }

    @Test public void samePrincipalLosesEveryEntryImmediatelyAfterDatabaseRevocation() throws Exception {
        http.perform(get("/sys/dataSource/queryById").param("id", "source")).andExpect(jsonPath("$.success").value(true));
        http.perform(get("/sys/quartzJob/queryById").param("id", "job")).andExpect(jsonPath("$.success").value(true));
        clearInvocations(sources, jobs);
        when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList("student"));
        deniedServices();
        for (MockHttpServletRequestBuilder request : requests()) http.perform(request).andExpect(status().isForbidden());
        verifyZeroInteractions(sources, jobs, cache, scheduler);
    }

    @Test public void passwordIsWriteOnlyForJsonLogsAndExplicitExportSchema() throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        assertFalse(mapper.writeValueAsString(stored).contains("synthetic-secret-only"));
        assertFalse(JSON.toJSONString(stored).contains("synthetic-secret-only"));
        assertFalse(stored.toString().contains("synthetic-secret-only"));
        assertEquals("input-secret", mapper.readValue("{\"dbPassword\":\"input-secret\"}", SysDataSource.class).getDbPassword());
        http.perform(get("/sys/dataSource/queryById").param("id", "source"))
                .andExpect(jsonPath("$.result.code").value("fixture_source"))
                .andExpect(jsonPath("$.result.dbPassword").doesNotExist());
        http.perform(get("/sys/dataSource/list")).andExpect(jsonPath("$.result.records[0].dbPassword").doesNotExist());
        MockHttpServletRequest request = new MockHttpServletRequest();
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
        ModelAndView view = dataController.exportXls(request, new SysDataSource());
        assertEquals(SysDataSourceView.class, view.getModel().get(NormalExcelConstants.CLASS));
        Workbook workbook = ExcelExportUtil.exportExcel((ExportParams) view.getModel().get(NormalExcelConstants.PARAMS),
                SysDataSourceView.class, (Collection<?>) view.getModel().get(NormalExcelConstants.DATA_LIST));
        StringBuilder cells = new StringBuilder();
        for (Row row : workbook.getSheetAt(0)) for (Cell cell : row) cells.append(cell.toString());
        assertTrue(cells.toString().contains("Synthetic source"));
        assertFalse(cells.toString().contains("synthetic-secret-only"));
        assertFalse(cells.toString().contains("密码"));
    }

    @Test public void operatorCanCreateAndEditWhileOmittedPasswordAndAuditIdentityArePreserved() throws Exception {
        String body = "{\"code\":\"new_source\",\"name\":\"New\",\"dbType\":\"1\",\"dbDriver\":\"driver\",\"dbUrl\":\"jdbc:fixture\",\"dbName\":\"fixture\",\"dbUsername\":\"fixture\",\"dbPassword\":\"new-secret\",\"id\":\"forged\",\"createBy\":\"forged\"}";
        http.perform(post("/sys/dataSource/add").contentType("application/json").content(body)).andExpect(jsonPath("$.success").value(true));
        ArgumentCaptor<SysDataSource> created = ArgumentCaptor.forClass(SysDataSource.class);
        verify(sources).insert(created.capture());
        assertNull(created.getValue().getId()); assertNull(created.getValue().getCreateBy());
        for (String password : Arrays.asList(null, "")) data.edit(source().setId("source").setDbPassword(password));
        ArgumentCaptor<SysDataSource> edited = ArgumentCaptor.forClass(SysDataSource.class);
        verify(sources, times(2)).updateById(edited.capture());
        for (SysDataSource value : edited.getAllValues()) assertEquals("synthetic-secret-only", value.getDbPassword());
        verify(cache, times(2)).invalidate("fixture_source");
    }

    @Test public void dataSourceInvalidBatchOrDatabaseFailureCannotInvalidateCache() {
        try { data.delete(Arrays.asList("source", "missing")); fail("Missing member accepted"); } catch (JeecgBootException expected) { }
        verify(sources, never()).deleteBatchIds(anyCollection()); verifyZeroInteractions(cache);
        when(sources.updateById(any())).thenThrow(new IllegalStateException("synthetic SQL failure"));
        try { data.edit(source().setId("source")); fail("Failure swallowed"); } catch (IllegalStateException expected) { }
        verifyZeroInteractions(cache);
        try { data.importSources(Arrays.asList(source(), source().setCode("invalid code"))); fail("Invalid import accepted"); }
        catch (JeecgBootException expected) { }
        verify(sources, never()).insert(any());
    }

    @Test public void dataSourceCacheChangesOnlyAfterCommitAndNotOnRollback() {
        JdbcDataSource database = new JdbcDataSource(); database.setURL("jdbc:h2:mem:ops_commit;DB_CLOSE_DELAY=-1");
        TransactionTemplate transaction = new TransactionTemplate(new DataSourceTransactionManager(database));
        transaction.execute(status -> { data.edit(source().setId("source")); verifyZeroInteractions(cache); status.setRollbackOnly(); return null; });
        verifyZeroInteractions(cache);
        transaction.execute(status -> { data.edit(source().setId("source")); verifyZeroInteractions(cache); return null; });
        verify(cache).invalidate("fixture_source");
        doThrow(new IllegalStateException("synthetic Redis failure")).when(cache).invalidate(anyString());
        // Once SQL has committed, cache failure must not return a false business rollback.
        transaction.execute(status -> { data.edit(source().setId("source")); return null; });
    }

    @Test public void importsUseAuthorizedValidatedCommandsAndNeverGenericSave() throws Exception {
        Workbook workbook = ExcelExportUtil.exportExcel(new ExportParams("数据源", "导入", "数据源"),
                SysDataSource.class, new ArrayList<>(Collections.singletonList(source())));
        ByteArrayOutputStream bytes = new ByteArrayOutputStream(); workbook.write(bytes);
        http.perform(multipart("/sys/dataSource/importExcel").file(new MockMultipartFile("file", "sources.xls", "application/vnd.ms-excel", bytes.toByteArray())))
                .andExpect(jsonPath("$.success").value(true));
        verify(sources).insert(any(SysDataSource.class));
        Workbook jobsWorkbook = ExcelExportUtil.exportExcel(new ExportParams("任务", "导入", "任务"), QuartzJob.class, new ArrayList<>(Collections.singletonList(job())));
        bytes.reset(); jobsWorkbook.write(bytes);
        http.perform(multipart("/sys/quartzJob/importExcel").file(new MockMultipartFile("file", "jobs.xls", "application/vnd.ms-excel", bytes.toByteArray())))
                .andExpect(jsonPath("$.success").value(true));
        verify(jobs).insert(any(QuartzJob.class)); verify(scheduler).scheduleJob(any(JobDetail.class), any(Trigger.class));
    }

    @Test public void unregisteredTaskTypesClassesCronAndBatchMembersFailBeforeSideEffects() throws Exception {
        QuartzJob bad = job(); bad.setJobType("java.lang.Runtime");
        try { quartz.saveAndScheduleJob(bad); fail("Arbitrary task type accepted"); } catch (JeecgBootException expected) { }
        bad = job(); bad.setJobClassName("java.lang.Runtime");
        try { quartz.saveAndScheduleJob(bad); fail("Class override accepted"); } catch (JeecgBootException expected) { }
        bad = job(); bad.setCronExpression("not-a-cron");
        try { quartz.saveAndScheduleJob(bad); fail("Invalid cron accepted"); } catch (JeecgBootException expected) { }
        bad = job(); bad.setJobType("unknown");
        try { quartz.importJobs(Arrays.asList(job(), bad)); fail("Mixed import accepted"); } catch (JeecgBootException expected) { }
        try { quartz.deleteAndStopJobs(Arrays.asList("job", "missing")); fail("Missing member accepted"); } catch (JeecgBootException expected) { }
        verify(jobs, never()).insert(any()); verify(jobs, never()).updateById(any()); verify(jobs, never()).deleteBatchIds(anyCollection());
        verifyZeroInteractions(scheduler);
    }

    @Test public void denialPreservesAnInitializedConnectionPoolAndItsRedisEntry() throws Exception {
        DruidDataSource pool = new DruidDataSource(); pool.setUrl("jdbc:h2:mem:ops_connection_pool");
        pool.setDriverClassName("org.h2.Driver"); pool.init();
        RedisTemplate<String, Object> redis = mock(RedisTemplate.class);
        Object previous = ReflectionTestUtils.getField(DataSourceCachePool.class, "redisTemplate");
        ReflectionTestUtils.setField(DataSourceCachePool.class, "redisTemplate", redis);
        DataSourceCachePool.putCacheBasicDataSource(stored.getCode(), pool);
        DataSourceAdministrationService service = new DataSourceAdministrationService(access, sources, new DataSourceCacheInvalidator());
        try {
            when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList("student"));
            try { service.edit(source().setId("source")); fail("Unauthorized edit accepted"); } catch (UnauthorizedException expected) { }
            try { service.delete(Collections.singletonList("source")); fail("Unauthorized delete accepted"); } catch (UnauthorizedException expected) { }
            assertSame(pool, DataSourceCachePool.getCacheBasicDataSource(stored.getCode())); assertFalse(pool.isClosed());
            verifyZeroInteractions(redis, sources);
            when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList("dev"));
            service.edit(source().setId("source"));
            assertTrue(pool.isClosed()); assertNull(DataSourceCachePool.getCacheBasicDataSource(stored.getCode()));
            verify(redis).delete("sys:cache:dbconnect:dynamic:" + stored.getCode());
        } finally {
            pool.close();
            ((Map<?, ?>) ReflectionTestUtils.getField(DataSourceCachePool.class, "dbSources")).remove(stored.getCode());
            ReflectionTestUtils.setField(DataSourceCachePool.class, "redisTemplate", previous);
        }
    }

    public static class SyntheticDriver implements Driver {
        static final AtomicInteger connections = new AtomicInteger();
        public Connection connect(String url, Properties info) { if (acceptsURL(url)) connections.incrementAndGet(); return null; }
        public boolean acceptsURL(String url) { return "jdbc:synthetic-no-driver".equals(url); }
        public DriverPropertyInfo[] getPropertyInfo(String url, Properties info) { return new DriverPropertyInfo[0]; }
        public int getMajorVersion() { return 1; }
        public int getMinorVersion() { return 0; }
        public boolean jdbcCompliant() { return false; }
        public Logger getParentLogger() { return Logger.getGlobal(); }
    }

    @Test public void compiledOnlineJdbcHandlerAndSpringAliasesUseTheSameLiveBoundary() throws Exception {
        Object online = Class.forName("org.jeecg.modules.online.cgreport.a.a").newInstance();
        MockMvc onlineHttp = MockMvcBuilders.standaloneSetup(online)
                .setControllerAdvice(new JeecgBootExceptionHandler())
                .addInterceptors(new InfrastructureManagementInterceptor(access)).build();
        SyntheticDriver driver = new SyntheticDriver(); SyntheticDriver.connections.set(0); DriverManager.registerDriver(driver);
        String payload = "{\"dbDriver\":\"" + SyntheticDriver.class.getName() + "\",\"dbUrl\":\"jdbc:synthetic-no-driver\"}";
        for (String role : Arrays.asList("student", "teacher", "admin")) {
            when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList(role));
            for (String path : Arrays.asList("/online/cgreport/api/testConnection", "/online/cgreport/api/testConnection/",
                    "/online/cgreport/api/testConnection.json", "/online/cgreport/api/testConnection.js", "/online/cgreport/api/testConnection;fixture=1",
                    "/%6fnline/cgreport/api/testConnection")) {
                onlineHttp.perform(post(java.net.URI.create(path)).contentType("application/json").content(payload))
                        .andExpect(jsonPath("$.success").value(false)).andExpect(jsonPath("$.code").value(403));
            }
        }
        assertEquals(0, SyntheticDriver.connections.get());
        when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList("dev"));
        // The real dependency controller handles the request, but the synthetic URL has no network driver.
        onlineHttp.perform(post("/online/cgreport/api/testConnection").contentType("application/json").content(payload))
                .andExpect(jsonPath("$.code").value(500)).andExpect(jsonPath("$.message").value(org.hamcrest.Matchers.containsString("No suitable driver")));
        when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList("student"));
        onlineHttp.perform(post("/online/cgreport/api/testConnection").contentType("application/json").content(payload))
                .andExpect(jsonPath("$.code").value(403));
        assertEquals(1, SyntheticDriver.connections.get()); DriverManager.deregisterDriver(driver);
        verifyZeroInteractions(sources, jobs, cache, scheduler);
    }

    @Test public void everyPackagedOnlineControllerIsCoveredWithoutTrustingUriPrefixes() throws Exception {
        ClassPathScanningCandidateComponentProvider scanner = new ClassPathScanningCandidateComponentProvider(false);
        scanner.addIncludeFilter(new AnnotationTypeFilter(RestController.class));
        InfrastructureManagementInterceptor interceptor = new InfrastructureManagementInterceptor(access);
        int controllers = 0, handlers = 0;
        for (BeanDefinition definition : scanner.findCandidateComponents("org.jeecg.modules.online")) {
            Class<?> type = Class.forName(definition.getBeanClassName()); Object controller = type.newInstance(); controllers++;
            for (Method method : type.getMethods()) {
                if (AnnotatedElementUtils.findMergedAnnotation(method, RequestMapping.class) == null) continue;
                handlers++;
                // The real handler identity is authoritative even if an upstream layer saw a different encoded path.
                MockHttpServletRequest request = new MockHttpServletRequest("GET", "/%6fnline%2fcgform/fixture.js");
                MockHttpServletResponse response = new MockHttpServletResponse();
                when(subject.getPrincipal()).thenReturn(null);
                assertFalse(interceptor.preHandle(request, response, new HandlerMethod(controller, method)));
                assertEquals(403, response.getStatus()); assertTrue(response.getContentAsString().contains("没有运维管理权限"));
            }
        }
        assertTrue("The packaged Online controller set was not exercised", controllers >= 9 && handlers >= 30);
        verifyZeroInteractions(sources, jobs, cache, scheduler);
    }

    @Test public void realQuartzStateSurvivesDenialsAndSupportsOperatorLifecycle() throws Exception {
        Properties properties = new Properties(); properties.setProperty("org.quartz.scheduler.instanceName", "ops-" + UUID.randomUUID());
        properties.setProperty("org.quartz.threadPool.threadCount", "1");
        properties.setProperty("org.quartz.threadPool.makeThreadsDaemons", "true");
        Scheduler real = new StdSchedulerFactory(properties).getScheduler();
        try {
            QuartzJobServiceImpl service = new QuartzJobServiceImpl(access, jobs, real);
            service.saveAndScheduleJob(job());
            JobKey key = JobKey.jobKey(SampleJob.class.getName()); TriggerKey trigger = TriggerKey.triggerKey(SampleJob.class.getName());
            assertTrue(real.checkExists(key)); assertEquals(Trigger.TriggerState.NORMAL, real.getTriggerState(trigger));
            String initial = real.getJobDetail(key).toString(); clearInvocations(jobs);
            when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList("student"));
            try { service.pauseJob(SampleJob.class.getName()); fail("Revoked operator paused task"); } catch (UnauthorizedException expected) { }
            try { service.deleteAndStopJobs(Collections.singletonList("job")); fail("Revoked operator deleted task"); } catch (UnauthorizedException expected) { }
            assertEquals(initial, real.getJobDetail(key).toString()); assertEquals(Trigger.TriggerState.NORMAL, real.getTriggerState(trigger));
            verifyZeroInteractions(jobs);
            when(roles.getRoleByUserId("operator")).thenReturn(Collections.singletonList("dev"));
            service.pauseJob(SampleJob.class.getName()); assertEquals(Trigger.TriggerState.PAUSED, real.getTriggerState(trigger));
            service.resumeJob(SampleJob.class.getName()); assertEquals(Trigger.TriggerState.NORMAL, real.getTriggerState(trigger));
            service.editAndScheduleJob(scheduled); assertTrue(real.checkExists(key));
            service.deleteAndStopJobs(Collections.singletonList("job")); assertFalse(real.checkExists(key));
        } finally { real.shutdown(true); }
    }
}
