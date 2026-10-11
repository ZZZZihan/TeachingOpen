package org.jeecg.additionalwork;

import org.apache.shiro.authz.UnauthorizedException;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.service.ISysDepartService;
import org.jeecg.modules.system.service.ISysUserDepartService;
import org.jeecg.modules.system.service.ISysUserService;
import org.jeecg.modules.teaching.controller.TeachingAdditionalWorkController;
import org.jeecg.modules.teaching.entity.TeachingAdditionalWork;
import org.jeecg.modules.teaching.mapper.TeachingAdditionalWorkMapper;
import org.jeecg.modules.teaching.model.MineAdditionalWorkModel;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.jeecg.modules.teaching.service.impl.TeachingAdditionalWorkServiceImpl;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.springframework.beans.BeanUtils;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.util.ReflectionUtils;

import java.util.Arrays;
import java.util.Collections;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class AdditionalWorkReadAuthorizationTest {
    private TeachingAdditionalWorkController controller;
    private TeachingAdditionalWorkServiceImpl service;
    private TeachingAdditionalWorkMapper assignments;
    private ISysUserService users;
    private ISysUserDepartService memberships;
    private ISysDepartService departments;
    private Subject subject;
    private SysUser user;
    private TeachingAdditionalWork work;

    @Before public void setup() {
        controller = new TeachingAdditionalWorkController(); service = new TeachingAdditionalWorkServiceImpl();
        TeachingAccessService access = new TeachingAccessService();
        assignments = mock(TeachingAdditionalWorkMapper.class); users = mock(ISysUserService.class);
        memberships = mock(ISysUserDepartService.class); departments = mock(ISysDepartService.class);
        subject = mock(Subject.class); ThreadContext.bind(subject);
        LoginUser principal = new LoginUser(); principal.setId("student-a"); principal.setUsername("student_a");
        principal.setDepartIds("stale-class");
        when(subject.getPrincipal()).thenReturn(principal);
        user = new SysUser().setId("student-a").setUsername("student_a").setStatus(1).setDelFlag(0);
        when(users.getById("student-a")).thenReturn(user);
        when(users.getRoleById("student-a")).thenReturn(Collections.singletonList("student"));
        when(memberships.userDepartIds("student-a")).thenReturn(Collections.singletonList("class-a"));
        when(departments.getMySubDepIdsByDepId("managed-a")).thenReturn(Collections.singletonList("class-a"));
        ReflectionTestUtils.setField(access, "userService", users);
        ReflectionTestUtils.setField(access, "userDepartService", memberships);
        ReflectionTestUtils.setField(access, "departService", departments);
        ReflectionTestUtils.setField(service, "baseMapper", assignments);
        if (ReflectionUtils.findField(TeachingAdditionalWorkServiceImpl.class, "teachingAccess") != null)
            ReflectionTestUtils.setField(service, "teachingAccess", access);
        ReflectionTestUtils.setField(controller, "teachingAdditionalWorkService", service);
        work = new TeachingAdditionalWork().setId("assignment-a").setWorkDept("class-a").setStatus(1)
                .setCreateBy("teacher_a").setWorkName("Private assigned task").setWorkDesc("private task body");
        when(assignments.selectById(any())).thenAnswer(call -> work);
        when(assignments.getWorkInfo(anyString())).thenAnswer(call -> {
            MineAdditionalWorkModel model = new MineAdditionalWorkModel(); BeanUtils.copyProperties(work, model); return model;
        });
    }

    @After public void cleanup() { ThreadContext.unbindSubject(); }

    private void deniedBoth() {
        try { controller.queryById("assignment-a"); fail("queryById must apply object authorization"); }
        catch (UnauthorizedException expected) { }
        try { controller.getWorkInfo("assignment-a"); fail("getWorkInfo must apply object authorization"); }
        catch (UnauthorizedException expected) { }
        verify(assignments, never()).insert(any()); verify(assignments, never()).updateById(any());
    }

    private void allowedBoth() {
        Result<?> result = controller.queryById("assignment-a");
        assertTrue(result.isSuccess()); assertEquals("private task body", ((TeachingAdditionalWork) result.getResult()).getWorkDesc());
        assertEquals("private task body", controller.getWorkInfo("assignment-a").getResult().getWorkDesc());
    }

    @Test public void studentCannotReadAnotherClassThroughEitherDetailRoute() {
        work.setWorkDept("class-b"); deniedBoth();
    }

    @Test public void assignedStudentCanReadPublishedTaskIncludingMultiClassAssignment() {
        allowedBoth(); work.setWorkDept("class-b, class-a ,class-c"); allowedBoth();
    }

    @Test public void draftTaskRemainsPrivateFromAssignedStudents() {
        work.setStatus(0); deniedBoth();
    }

    @Test public void departmentMatchingMustBeExactNotASubstringOrCollationAlias() {
        work.setWorkDept("class-a-extra"); deniedBoth();
        work.setWorkDept("CLASS-A"); deniedBoth();
    }

    @Test public void teacherReadsAssignedManagedClassUsingLiveScope() {
        when(users.getRoleById("student-a")).thenReturn(Collections.singletonList("teacher"));
        user.setDepartIds("managed-a"); work.setStatus(0); allowedBoth();
        work.setWorkDept("class-a,class-b"); allowedBoth();
        work.setWorkDept("class-b"); deniedBoth();
    }

    @Test public void staleTeacherAndAdministratorRolesCannotAuthorizeRead() {
        when(subject.hasRole(anyString())).thenReturn(true);
        when(users.getRoleById("student-a")).thenReturn(Collections.singletonList("student"));
        user.setDepartIds("managed-a"); work.setStatus(0); deniedBoth();
    }

    @Test public void administratorsAndDevelopersCanReadForeignDrafts() {
        work.setWorkDept("class-b").setStatus(0);
        for (String role : Arrays.asList("admin", "dev")) {
            when(users.getRoleById("student-a")).thenReturn(Collections.singletonList(role)); allowedBoth();
        }
    }

    @Test public void anonymousFrozenDeletedAndMissingUsersCannotRead() {
        when(subject.getPrincipal()).thenReturn(null); deniedBoth();
        LoginUser principal = new LoginUser(); principal.setId("student-a"); when(subject.getPrincipal()).thenReturn(principal);
        user.setStatus(2); deniedBoth(); user.setStatus(1).setDelFlag(1); deniedBoth();
        when(users.getById("student-a")).thenReturn(null); deniedBoth();
    }

    @Test public void missingAssignmentAndCaseAliasCannotDiscloseContent() {
        work.setId("ASSIGNMENT-A"); deniedBoth();
        when(assignments.selectById(any())).thenReturn(null); deniedBoth();
    }
}
