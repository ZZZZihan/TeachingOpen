package org.jeecg.audit;

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
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
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
        when(mapper.insert(any(SysDataLog.class))).thenReturn(1);
        SysDataLogServiceImpl service = new SysDataLogServiceImpl();
        ReflectionTestUtils.setField(service,"logMapper",mapper); ReflectionTestUtils.setField(service,"baseMapper",mapper);
        service.addDataLog("teaching_work","own-work",SECRET);
        ArgumentCaptor<SysDataLog> saved = ArgumentCaptor.forClass(SysDataLog.class); verify(mapper).insert(saved.capture());
        assertEquals("3",saved.getValue().getDataVersion()); assertEquals(SECRET,saved.getValue().getDataContent());
        assertEquals("own-work",saved.getValue().getDataId());
    }
}
