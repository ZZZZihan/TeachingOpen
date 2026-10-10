package org.jeecg.additionalwork;

import org.apache.shiro.authz.UnauthorizedException;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.RedisUtil;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.service.ISysDepartService;
import org.jeecg.modules.system.service.ISysUserService;
import org.jeecg.modules.teaching.entity.TeachingAdditionalWork;
import org.jeecg.modules.teaching.mapper.TeachingAdditionalWorkMapper;
import org.jeecg.modules.teaching.service.ITeachingDepartDayLogService;
import org.jeecg.modules.teaching.service.impl.TeachingAdditionalWorkServiceImpl;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.util.*;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class AdditionalWorkAuthorizationTest {
    private TeachingAdditionalWorkServiceImpl service;
    private TeachingAdditionalWorkMapper works;
    private ISysUserService users;
    private ISysDepartService departments;
    private ITeachingDepartDayLogService logs;
    private RedisUtil redis;
    private Subject subject;
    private SysUser teacher;

    @Before public void setup() {
        service = new TeachingAdditionalWorkServiceImpl();
        works = mock(TeachingAdditionalWorkMapper.class);
        users = mock(ISysUserService.class);
        departments = mock(ISysDepartService.class);
        logs = mock(ITeachingDepartDayLogService.class);
        redis = mock(RedisUtil.class);
        subject = mock(Subject.class);
        ReflectionTestUtils.setField(service, "baseMapper", works);
        ReflectionTestUtils.setField(service, "sysUserService", users);
        ReflectionTestUtils.setField(service, "sysDepartService", departments);
        ReflectionTestUtils.setField(service, "teachingDepartDayLogService", logs);
        ReflectionTestUtils.setField(service, "redisUtil", redis);
        LoginUser principal = new LoginUser();
        principal.setId("teacher-a"); principal.setUsername("teacher_a"); principal.setDepartIds("stale-other-class");
        when(subject.getPrincipal()).thenReturn(principal);
        ThreadContext.bind(subject);
        teacher = new SysUser().setId("teacher-a").setUsername("teacher_a").setStatus(1)
                .setDepartIds("managed-root").setOrgCode("school-code");
        when(users.getOne(any())).thenReturn(teacher);
        when(users.getRoleById("teacher-a")).thenReturn(Collections.singletonList("teacher"));
        when(departments.getMySubDepIdsByDepId("managed-root")).thenReturn(Arrays.asList("class-a", "class-c"));
        when(departments.list(any())).thenReturn(Collections.singletonList(department("class-a")));
        when(works.selectList(any())).thenReturn(Collections.singletonList(existing("work-a", "teacher_a", "class-a")));
        when(works.insert(any())).thenAnswer(call -> {
            ((TeachingAdditionalWork) call.getArgument(0)).setId("generated-work"); return 1;
        });
        when(works.updateById(any())).thenReturn(1);
        when(works.deleteBatchIds(anyCollection())).thenAnswer(call -> ((Collection<?>) call.getArgument(0)).size());
        TransactionSynchronizationManager.initSynchronization();
    }

    @After public void teardown() {
        if (TransactionSynchronizationManager.isSynchronizationActive()) TransactionSynchronizationManager.clearSynchronization();
        ThreadContext.unbindSubject();
    }

    private SysDepart department(String id) {
        SysDepart d = new SysDepart(); d.setId(id); d.setDelFlag("0"); return d;
    }

    private TeachingAdditionalWork request() {
        return new TeachingAdditionalWork().setId("work-a").setWorkName(" 合成任务 ")
                .setWorkDept("class-a").setStatus(1).setCodeType(0).setWorkDesc("description");
    }

    private TeachingAdditionalWork existing(String id, String owner, String classes) {
        return new TeachingAdditionalWork().setId(id).setCreateBy(owner).setWorkDept(classes)
                .setWorkName("old-name").setStatus(1);
    }

    private void denied(Runnable action) {
        try { action.run(); fail("Operation must fail before writing"); }
        catch (UnauthorizedException | JeecgBootException expected) { }
        verify(works, never()).insert(any());
        verify(works, never()).updateById(any());
        verify(works, never()).deleteBatchIds(anyCollection());
        verifyZeroInteractions(logs, redis);
    }

    @Test public void everyWriteRejectsStudentEvenWithCachedTeacherRole() {
        when(subject.hasRole("teacher")).thenReturn(true);
        when(users.getRoleById("teacher-a")).thenReturn(Collections.singletonList("student"));
        denied(() -> service.addNewAdditionalWork(request()));
        denied(() -> service.editAdditionalWork(request()));
        denied(() -> service.deleteAdditionalWorks(Collections.singletonList("work-a")));
    }

    @Test public void missingPrincipalAndFrozenAccountCannotWrite() {
        when(subject.getPrincipal()).thenReturn(null);
        denied(() -> service.addNewAdditionalWork(request()));
        LoginUser p = new LoginUser(); p.setId("teacher-a"); when(subject.getPrincipal()).thenReturn(p);
        teacher.setStatus(2);
        denied(() -> service.editAdditionalWork(request()));
    }

    @Test public void addUsesLiveManagedDepartmentsAndIgnoresForgedIdentityFields() {
        TeachingAdditionalWork request = request().setId("existing-other-task").setCreateBy("admin")
                .setCreateTime(new Date(1)).setSysOrgCode("other-org").setUpdateBy("admin");
        assertTrue(service.addNewAdditionalWork(request).isSuccess());
        ArgumentCaptor<TeachingAdditionalWork> capture = ArgumentCaptor.forClass(TeachingAdditionalWork.class);
        verify(works).insert(capture.capture());
        TeachingAdditionalWork inserted = capture.getValue();
        assertEquals("generated-work", inserted.getId()); assertEquals("teacher_a", inserted.getCreateBy());
        assertEquals("school-code", inserted.getSysOrgCode()); assertNull(inserted.getUpdateBy());
        assertNotEquals(new Date(1), inserted.getCreateTime()); assertEquals("合成任务", inserted.getWorkName());
        verify(departments).getMySubDepIdsByDepId("managed-root");
        verify(logs).recordAdditionalWorkAssignment("class-a");
        verify(redis, never()).sSet(anyString(), any());
        for (TransactionSynchronization synchronization : TransactionSynchronizationManager.getSynchronizations()) synchronization.afterCommit();
        verify(redis).sSet("departLog:addiWorkAssign:class-a", "generated-work");
    }

    @Test public void teacherCannotCreateOrMoveTaskOutsideManagedClasses() {
        when(departments.list(any())).thenReturn(Collections.singletonList(department("class-b")));
        denied(() -> service.addNewAdditionalWork(request().setWorkDept("class-b")));
        denied(() -> service.editAdditionalWork(request().setWorkDept("class-b")));
    }

    @Test public void ownTaskWithAnyOldOutOfScopeClassCannotBeEditedOrDeleted() {
        when(works.selectList(any())).thenReturn(Collections.singletonList(existing("work-a", "teacher_a", "class-a,class-b")));
        denied(() -> service.editAdditionalWork(request()));
        denied(() -> service.deleteAdditionalWorks(Collections.singletonList("work-a")));
    }

    @Test public void teacherCannotEditOrDeleteAnotherTeachersTaskInSameClass() {
        when(works.selectList(any())).thenReturn(Collections.singletonList(existing("work-a", "teacher_b", "class-a")));
        denied(() -> service.editAdditionalWork(request().setCreateBy("teacher_a")));
        denied(() -> service.deleteAdditionalWorks(Collections.singletonList("work-a")));
    }

    @Test public void mixedBatchIsValidatedCompletelyBeforeDeletion() {
        when(works.selectList(any())).thenReturn(Arrays.asList(existing("work-a", "teacher_a", "class-a"),
                existing("work-b", "teacher_b", "class-a")));
        denied(() -> service.deleteAdditionalWorks(Arrays.asList("work-a", "work-b")));
    }

    @Test public void unknownOrCollationAliasIdsRejectWholeBatch() {
        denied(() -> service.deleteAdditionalWorks(Arrays.asList("work-a", "missing")));
        denied(() -> service.deleteAdditionalWorks(Collections.singletonList("WORK-A")));
        when(departments.list(any())).thenReturn(Collections.singletonList(department("CLASS-A")));
        denied(() -> service.addNewAdditionalWork(request()));
    }

    @Test public void editKeepsIdentityAndExistingAssignmentDoesNotRepeatLogs() {
        TeachingAdditionalWork request = request().setCreateBy("admin").setCreateTime(new Date(1))
                .setSysOrgCode("other-org").setUpdateBy("admin");
        assertTrue(service.editAdditionalWork(request).isSuccess());
        ArgumentCaptor<TeachingAdditionalWork> capture = ArgumentCaptor.forClass(TeachingAdditionalWork.class);
        verify(works).updateById(capture.capture());
        TeachingAdditionalWork updated = capture.getValue();
        assertNull(updated.getCreateBy()); assertNull(updated.getCreateTime()); assertNull(updated.getSysOrgCode());
        assertEquals("teacher_a", updated.getUpdateBy());
        verifyZeroInteractions(logs, redis);
    }

    @Test public void addingManagedClassCreatesOnlyItsAssignmentLogAfterValidation() {
        when(departments.list(any())).thenReturn(Arrays.asList(department("class-a"), department("class-c")));
        assertTrue(service.editAdditionalWork(request().setWorkDept("class-c,class-a,class-c")).isSuccess());
        verify(logs).recordAdditionalWorkAssignment("class-c");
        verify(logs, never()).recordAdditionalWorkAssignment("class-a");
        verify(redis, never()).sSet(anyString(), any());
    }

    @Test public void administratorsCanManageForeignTasksAndBatchDeduplicatesIds() {
        when(users.getRoleById("teacher-a")).thenReturn(Collections.singletonList("admin"));
        when(works.selectList(any())).thenReturn(Collections.singletonList(existing("work-a", "teacher_b", "class-b")));
        assertTrue(service.deleteAdditionalWorks(Arrays.asList("work-a", "work-a")).isSuccess());
        verify(works).deleteBatchIds(Collections.singletonList("work-a"));
    }

    @Test public void invalidFieldsAndMissingTargetsNeverWriteOrLog() {
        denied(() -> service.addNewAdditionalWork(request().setWorkDept("class-a,,class-c")));
        denied(() -> service.addNewAdditionalWork(request().setStatus(2)));
        denied(() -> service.addNewAdditionalWork(request().setWorkName(" ")));
        denied(() -> service.deleteAdditionalWorks(Collections.emptyList()));
    }

    @Test public void failedPersistenceCannotCreateAssignmentLogsOrRedisMarkers() {
        doReturn(0).when(works).insert(any());
        try { service.addNewAdditionalWork(request()); fail("save must fail"); }
        catch (JeecgBootException expected) { }
        verifyZeroInteractions(logs, redis);
        assertTrue(TransactionSynchronizationManager.getSynchronizations().isEmpty());
    }

    @Test public void logFailureAbortsTransactionAndDoesNotEmitRedisMarker() {
        doThrow(new IllegalStateException("synthetic log failure")).when(logs).recordAdditionalWorkAssignment(anyString());
        try { service.addNewAdditionalWork(request()); fail("log failure must propagate for rollback"); }
        catch (IllegalStateException expected) { }
        verify(redis, never()).sSet(anyString(), any());
        assertTrue(TransactionSynchronizationManager.getSynchronizations().isEmpty());
    }
}
