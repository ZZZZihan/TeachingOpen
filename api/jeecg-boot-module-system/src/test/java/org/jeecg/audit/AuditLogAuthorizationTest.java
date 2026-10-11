package org.jeecg.audit;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.exception.JeecgBootExceptionHandler;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.controller.SysDataLogController;
import org.jeecg.modules.system.controller.SysLogController;
import org.jeecg.modules.system.entity.*;
import org.jeecg.modules.system.mapper.*;
import org.jeecg.modules.system.service.*;
import org.jeecg.modules.system.service.impl.SysDataLogServiceImpl;
import org.junit.*;
import org.mockito.ArgumentCaptor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.util.*;
import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

public class AuditLogAuthorizationTest {
    private ISysLogService logs;
    private ISysDataLogService history;
    private SysUserMapper users;
    private SysUserRoleMapper roles;
    private SysUser actor;
    private MockMvc http;
    private static final String SECRET = "fixture-private-feedback-8317";
    private final String[] reads = {"/sys/log/list", "/sys/dataLog/list",
            "/sys/dataLog/queryCompareList?dataId1=history&dataId2=other",
            "/sys/dataLog/queryDataVerList?dataTable=teaching_work&dataId=private-work"};

    @Before public void setup() {
        for (Class<?> type : Arrays.asList(SysLog.class, SysDataLog.class))
            TableInfoHelper.initTableInfo(new MapperBuilderAssistant(new MybatisConfiguration(), "audit-test"), type);
        users = mock(SysUserMapper.class); roles = mock(SysUserRoleMapper.class);
        logs = mock(ISysLogService.class); history = mock(ISysDataLogService.class);
        actor = new SysUser().setId("actor").setUsername("fixture_admin").setStatus(1).setDelFlag(0);
        LoginUser identity = new LoginUser(); identity.setId("actor"); identity.setUsername("stale-principal");
        Subject subject = mock(Subject.class); when(subject.getPrincipal()).thenReturn(identity); ThreadContext.bind(subject);
        when(users.selectById("actor")).thenReturn(actor);
        when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList("admin"));
        SysLog log = new SysLog().setId("audit").setRequestParam(SECRET);
        SysDataLog version = new SysDataLog().setId("history").setDataContent(SECRET);
        when(logs.page(any(Page.class), any())).thenReturn(new Page<SysLog>(1,10).setRecords(Collections.singletonList(log)));
        when(history.page(any(Page.class), any())).thenReturn(new Page<SysDataLog>(1,10).setRecords(Collections.singletonList(version)));
        when(history.listByIds(anyCollection())).thenReturn(Collections.singletonList(version));
        when(history.list(any())).thenReturn(Collections.singletonList(version));
        when(logs.getById("audit")).thenReturn(log); when(logs.removeById("audit")).thenReturn(true);
        when(logs.removeByIds(anyCollection())).thenReturn(true);
        SysLogController controller = new SysLogController(); SysDataLogController data = new SysDataLogController();
        AuditLogAccessService access = new AuditLogAccessService(users, roles);
        ReflectionTestUtils.setField(controller, "sysLogService", logs); ReflectionTestUtils.setField(controller, "auditLogAccess", access);
        ReflectionTestUtils.setField(data, "service", history); ReflectionTestUtils.setField(data, "auditLogAccess", access);
        http = MockMvcBuilders.standaloneSetup(controller,data).setControllerAdvice(new JeecgBootExceptionHandler()).build();
    }

    @After public void cleanup() { ThreadContext.unbindSubject(); }
    private void ordinary(String role) { when(roles.getRoleByUserId("actor")).thenReturn(Collections.singletonList(role)); }

    @Test public void ordinaryUsersCannotReadRawAuditRequests() throws Exception {
        for (String role : Arrays.asList("student", "teacher", "unassigned")) {
            ordinary(role);
            http.perform(get(reads[0])).andExpect(jsonPath("$.code").value(510)).andExpect(jsonPath("$.success").value(false))
                    .andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString(SECRET))));
        }
        verifyZeroInteractions(logs, history);
    }

    @Test public void ordinaryUsersCannotReadListCompareOrVersions() throws Exception {
        for (String role : Arrays.asList("student", "teacher", "unassigned")) {
            ordinary(role);
            for (int i=1; i<reads.length; i++) http.perform(get(reads[i])).andExpect(jsonPath("$.code").value(510))
                    .andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString(SECRET))));
        }
        verifyZeroInteractions(logs, history);
    }

    @Test public void ordinarySingleDeleteBatchDeleteAndAllClearDoNotReachPersistence() throws Exception {
        for (String role : Arrays.asList("student", "teacher", "unassigned")) {
            ordinary(role);
            for (String path : Arrays.asList("/sys/log/delete?id=audit", "/sys/log/deleteBatch?ids=audit,other", "/sys/log/deleteBatch?ids=allclear"))
                http.perform(delete(path)).andExpect(jsonPath("$.code").value(510)).andExpect(jsonPath("$.success").value(false));
        }
        verifyZeroInteractions(logs, history);
    }

    @Test public void activeAdminAndDeveloperRetainManagementReadsAndDeletes() throws Exception {
        for (String role : Arrays.asList("admin", "dev")) {
            ordinary(role);
            for (String path : reads) http.perform(get(path)).andExpect(jsonPath("$.success").value(true))
                    .andExpect(content().string(org.hamcrest.Matchers.containsString(SECRET)));
            http.perform(delete("/sys/log/delete?id=audit")).andExpect(jsonPath("$.success").value(true));
            http.perform(delete("/sys/log/deleteBatch?ids=audit,other")).andExpect(jsonPath("$.success").value(true));
            http.perform(delete("/sys/log/deleteBatch?ids=allclear")).andExpect(jsonPath("$.success").value(true));
        }
        verify(logs,times(2)).removeAll(); verify(logs,times(2)).removeById("audit");
    }

    @Test public void samePrincipalLosesReadsAndDestructiveActionsAfterLiveRoleRemoval() throws Exception {
        http.perform(get(reads[0])).andExpect(jsonPath("$.success").value(true));
        clearInvocations(logs, history); ordinary("teacher");
        for (String path : reads) http.perform(get(path)).andExpect(jsonPath("$.code").value(510));
        http.perform(delete("/sys/log/deleteBatch?ids=allclear")).andExpect(jsonPath("$.code").value(510));
        verifyZeroInteractions(logs, history);
    }

    @Test public void disabledDeletedAndMissingAccountsCannotUseAnOldAdministratorPrincipal() throws Exception {
        actor.setStatus(2); http.perform(get(reads[0])).andExpect(jsonPath("$.code").value(510));
        actor.setStatus(1).setDelFlag(1); http.perform(delete("/sys/log/delete?id=audit")).andExpect(jsonPath("$.code").value(510));
        when(users.selectById("actor")).thenReturn(null); http.perform(get(reads[1])).andExpect(jsonPath("$.code").value(510));
        verifyZeroInteractions(logs, history);
    }

    @Test public void trustedStudentSubmissionStillWritesVersionHistory() {
        ordinary("student"); SysDataLogMapper mapper = mock(SysDataLogMapper.class);
        when(mapper.queryMaxDataVer("teaching_work","own-work")).thenReturn("2");
        String content = "{\"workFile\":\"previous-private-file\",\"comment\":\"" + SECRET + "\"}";
        when(mapper.insert(any(SysDataLog.class))).thenAnswer(call -> {
            assertTrue(TransactionSynchronizationManager.isActualTransactionActive());
            ((SysDataLog) call.getArgument(0)).setId("own-history");
            return 1;
        });
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        Map<String,Object> state = new HashMap<>();
        state.put("version",1); state.put("static_domain","/api/sys/common/static");
        when(jdbc.queryForMap("SELECT version,static_domain FROM sys_local_file_reference_state WHERE id=1 LOCK IN SHARE MODE"))
                .thenAnswer(call -> {
                    assertTrue(TransactionSynchronizationManager.isActualTransactionActive());
                    return state;
                });
        Map<String,Object> persisted = new HashMap<>();
        persisted.put("id","own-history"); persisted.put("data_table","teaching_work"); persisted.put("data_content",content);
        when(jdbc.queryForList("SELECT * FROM sys_data_log WHERE id=? FOR UPDATE","own-history"))
                .thenReturn(Collections.singletonList(persisted));
        LocalMediaReferenceIndex index = new LocalMediaReferenceIndex();
        HistoryTransactions transactions = new HistoryTransactions();
        ReflectionTestUtils.setField(index,"jdbc",jdbc); ReflectionTestUtils.setField(index,"json",new ObjectMapper());
        ReflectionTestUtils.setField(index,"transactionManager",transactions);
        ReflectionTestUtils.setField(index,"staticDomain","/api/sys/common/static");
        SysDataLogServiceImpl service = new SysDataLogServiceImpl();
        ReflectionTestUtils.setField(service,"logMapper",mapper); ReflectionTestUtils.setField(service,"baseMapper",mapper);
        ReflectionTestUtils.setField(service,"mediaIndex",index);
        service.addDataLog("teaching_work","own-work",content);
        ArgumentCaptor<SysDataLog> saved = ArgumentCaptor.forClass(SysDataLog.class); verify(mapper).insert(saved.capture());
        assertEquals("3",saved.getValue().getDataVersion()); assertEquals(content,saved.getValue().getDataContent());
        assertEquals("own-work",saved.getValue().getDataId());
        assertEquals("teaching_work",saved.getValue().getDataTable());
        verify(jdbc).update(startsWith("INSERT INTO sys_local_file_reference "),eq("sys_data_log"),eq("own-history"),
                eq("workFile"),eq("file"),eq(LocalMediaReferenceIndex.hash("previous-private-file")),eq("previous-private-file"));
        assertEquals(1,transactions.commits); assertEquals(0,transactions.rollbacks);
        assertFalse(TransactionSynchronizationManager.isActualTransactionActive());
    }

    private static class HistoryTransactions extends AbstractPlatformTransactionManager {
        int commits, rollbacks;
        protected Object doGetTransaction() { return new Object(); }
        protected boolean isExistingTransaction(Object transaction) { return TransactionSynchronizationManager.isActualTransactionActive(); }
        protected void doBegin(Object transaction, TransactionDefinition definition) { }
        protected void doCommit(DefaultTransactionStatus status) { commits++; }
        protected void doRollback(DefaultTransactionStatus status) { rollbacks++; }
    }
}
