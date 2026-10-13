package org.jeecg.additionalwork;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
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
import org.mockito.ArgumentCaptor;
import org.springframework.beans.BeanUtils;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.util.ReflectionUtils;

import java.util.Arrays;
import java.util.Collections;
import java.util.regex.Pattern;

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
        ReflectionTestUtils.setField(controller, "teachingAccess", access);
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

    private void deniedList() {
        try { controller.queryPageList(new TeachingAdditionalWork(), 1, 10, new MockHttpServletRequest());
            fail("management list must authorize before enumerating assignments"); }
        catch (UnauthorizedException expected) { }
        verify(assignments, never()).selectPage(any(), any());
        verify(assignments, never()).insert(any()); verify(assignments, never()).updateById(any());
    }

    @SuppressWarnings("unchecked")
    private QueryWrapper<TeachingAdditionalWork> managementQuery(TeachingAdditionalWork filter, int pageNo,
                                                                int pageSize, MockHttpServletRequest request) {
        when(assignments.selectPage(any(Page.class), any(QueryWrapper.class))).thenAnswer(call -> call.getArgument(0));
        Result<?> result;
        // QueryGenerator reads data rules from the request bound by Spring MVC.
        // Exercise the real query builder with that same request context.
        RequestContextHolder.setRequestAttributes(new ServletRequestAttributes(request));
        try {
            result = controller.queryPageList(filter, pageNo, pageSize, request);
        } finally {
            RequestContextHolder.resetRequestAttributes();
        }
        assertTrue(result.isSuccess());
        Page<TeachingAdditionalWork> page = (Page<TeachingAdditionalWork>) result.getResult();
        assertEquals(pageNo, page.getCurrent()); assertEquals(pageSize, page.getSize());
        ArgumentCaptor<QueryWrapper> query = ArgumentCaptor.forClass(QueryWrapper.class);
        verify(assignments, atLeastOnce()).selectPage(any(Page.class), query.capture());
        return query.getValue();
    }

    private Pattern classPredicate(QueryWrapper<TeachingAdditionalWork> query) {
        String sql = query.getSqlSegment();
        assertTrue("class restriction must precede database pagination", sql.contains("REGEXP_LIKE(work_dept,"));
        assertTrue("database collation must not introduce case aliases", sql.contains("'c'"));
        assertFalse("class IDs must be bound values", sql.contains("class-a"));
        String pattern = query.getParamNameValuePairs().values().stream().filter(String.class::isInstance)
                .map(String.class::cast).filter(value -> value.startsWith("(\\A|,)")).findFirst()
                .orElseThrow(() -> new AssertionError("missing bound exact CSV predicate"));
        return Pattern.compile(pattern);
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

    @Test public void detailTrimsOnlyTokenEdgesAndPreservesUnicodeSeparators() {
        work.setWorkDept(" \tclass-a\r\n ,class-b"); allowedBoth();
        for (String token : Arrays.asList("cl ass-a", "class-a\u0085", "class-a\u2028", "\u00a0class-a\u00a0")) {
            work.setWorkDept(token); deniedBoth();
        }
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

    @Test public void managementListRejectsStudentEvenWithManagedClassesAndStalePrivilegedRoles() {
        user.setDepartIds("managed-a"); when(subject.hasRole(anyString())).thenReturn(true); deniedList();
        verify(departments, never()).getMySubDepIdsByDepId(anyString());
    }

    @Test public void managementListUsesLiveTeacherRootAndDescendantsWithExactCsvTokens() {
        when(users.getRoleById("student-a")).thenReturn(Collections.singletonList("teacher"));
        user.setDepartIds("managed-a");
        when(departments.getMySubDepIdsByDepId("managed-a")).thenReturn(Arrays.asList("class-a", "class-child"));
        Pattern predicate = classPredicate(managementQuery(new TeachingAdditionalWork(), 1, 10, new MockHttpServletRequest()));
        for (String value : Arrays.asList("class-a", "class-child", "class-b, class-a ,class-c", " \tclass-a\r\n"))
            assertTrue(value, predicate.matcher(value).find());
        for (String value : Arrays.asList("class-a-extra", "CLASS-A", "cl ass-a", "class-a\u0085", "class-a\u2028",
                "\u00a0class-a\u00a0", "class-b")) assertFalse(value, predicate.matcher(value).find());
        verify(departments, never()).getMySubDepIdsByDepId("stale-class");
    }

    @Test public void managementListRetainsEntityFiltersSortingAndRequestedPage() {
        when(users.getRoleById("student-a")).thenReturn(Collections.singletonList("teacher"));
        user.setDepartIds("managed-a");
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addParameter("column", "workName"); request.addParameter("order", "desc");
        QueryWrapper<TeachingAdditionalWork> query = managementQuery(
                new TeachingAdditionalWork().setWorkName("Selected task").setStatus(0), 3, 7, request);
        classPredicate(query);
        assertTrue(query.getSqlSegment().contains("work_name ="));
        assertTrue(query.getSqlSegment().contains("status ="));
        assertTrue(query.getSqlSegment().contains("ORDER BY work_name DESC"));
        assertTrue(query.getParamNameValuePairs().containsValue("Selected task"));
        assertTrue(query.getParamNameValuePairs().containsValue(0));
    }

    @Test public void managementListEscapesRegexMetacharactersInCurrentClassIds() {
        when(users.getRoleById("student-a")).thenReturn(Collections.singletonList("teacher"));
        user.setDepartIds("managed-a");
        String id = "class-a.(x)[0]{1}+?^$|\\E";
        when(departments.getMySubDepIdsByDepId("managed-a")).thenReturn(Collections.singletonList(id));
        Pattern predicate = classPredicate(managementQuery(new TeachingAdditionalWork(), 1, 10, new MockHttpServletRequest()));
        assertTrue(predicate.matcher("other," + id + ",last").find());
        assertFalse(predicate.matcher("class-aXx0").find());
        assertFalse(predicate.matcher("class-a").find());
    }

    @Test public void managementListImmediatelyReflectsClassTransferAndRoleRevocation() {
        when(users.getRoleById("student-a")).thenReturn(Collections.singletonList("teacher"));
        user.setDepartIds("managed-b");
        when(departments.getMySubDepIdsByDepId("managed-b")).thenReturn(Collections.singletonList("class-b"));
        Pattern predicate = classPredicate(managementQuery(new TeachingAdditionalWork(), 1, 10, new MockHttpServletRequest()));
        assertTrue(predicate.matcher("class-b").find()); assertFalse(predicate.matcher("class-a").find());
        clearInvocations(assignments);
        when(users.getRoleById("student-a")).thenReturn(Collections.singletonList("student")); deniedList();
    }

    @Test public void managementListRejectsTeacherWithoutCurrentClasses() {
        when(users.getRoleById("student-a")).thenReturn(Collections.singletonList("teacher"));
        user.setDepartIds(null); deniedList();
        user.setDepartIds("managed-missing"); deniedList();
    }

    @Test public void liveAdministratorsAndDevelopersKeepUnrestrictedFilteredManagementList() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addParameter("column", "workName"); request.addParameter("order", "asc");
        for (String role : Arrays.asList("admin", "dev")) {
            when(users.getRoleById("student-a")).thenReturn(Collections.singletonList(role));
            QueryWrapper<TeachingAdditionalWork> query = managementQuery(
                    new TeachingAdditionalWork().setWorkName("Selected task"), 2, 5, request);
            assertFalse(query.getSqlSegment().contains("REGEXP_LIKE"));
            assertTrue(query.getSqlSegment().contains("work_name ="));
            assertTrue(query.getSqlSegment().contains("ORDER BY work_name ASC"));
            assertTrue(query.getParamNameValuePairs().containsValue("Selected task"));
        }
        verify(departments, never()).getMySubDepIdsByDepId(anyString());
    }

    @Test public void anonymousFrozenDeletedAndMissingUsersCannotEnumerateManagementList() {
        when(subject.getPrincipal()).thenReturn(null); deniedList();
        LoginUser principal = new LoginUser(); principal.setId("student-a"); when(subject.getPrincipal()).thenReturn(principal);
        when(users.getRoleById("student-a")).thenReturn(Collections.singletonList("admin"));
        user.setStatus(2); deniedList(); user.setStatus(1).setDelFlag(1); deniedList();
        when(users.getById("student-a")).thenReturn(null); deniedList();
    }
}
