package org.jeecg.workintegrity;

import org.jeecg.common.exception.JeecgBootException;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.mapper.SysDepartMapper;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.teaching.entity.TeachingCourse;
import org.jeecg.modules.teaching.entity.TeachingCourseUnit;
import org.jeecg.modules.teaching.entity.TeachingCourseDept;
import org.jeecg.modules.teaching.entity.TeachingAdditionalWork;
import org.jeecg.modules.teaching.mapper.TeachingCourseMapper;
import org.jeecg.modules.teaching.mapper.TeachingCourseUnitMapper;
import org.jeecg.modules.teaching.mapper.TeachingCourseDeptMapper;
import org.jeecg.modules.teaching.mapper.TeachingAdditionalWorkMapper;
import org.jeecg.modules.teaching.entity.TeachingWork;
import org.jeecg.modules.teaching.mapper.TeachingWorkCommentMapper;
import org.jeecg.modules.teaching.mapper.TeachingWorkCorrectMapper;
import org.jeecg.modules.teaching.mapper.TeachingWorkMapper;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.jeecg.modules.teaching.service.impl.TeachingWorkServiceImpl;
import org.jeecg.modules.teaching.vo.StudentWorkSendVO;
import org.junit.Before;
import org.junit.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Arrays;
import java.util.Collections;
import java.util.Date;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class WorkCloneServiceTest {
    private TeachingWorkServiceImpl service;
    private TeachingWorkMapper works;
    private SysUserMapper users;
    private TeachingAccessService access;
    private TeachingWorkCorrectMapper correct;
    private TeachingWorkCommentMapper comments;
    private TeachingWork source;
    private SysDepartMapper departments;
    private TeachingCourseMapper courses;
    private TeachingCourseUnitMapper units;
    private TeachingCourseDeptMapper assignments;
    private TeachingAdditionalWorkMapper additional;
    private TeachingCourse course;
    private TeachingCourseUnit unit;
    private TeachingAdditionalWork task;

    @Before public void setup() {
        works = mock(TeachingWorkMapper.class); users = mock(SysUserMapper.class);
        access = mock(TeachingAccessService.class);
        correct = mock(TeachingWorkCorrectMapper.class); comments = mock(TeachingWorkCommentMapper.class);
        service = new TeachingWorkServiceImpl();
        ReflectionTestUtils.setField(service, "teachingWorkMapper", works);
        ReflectionTestUtils.setField(service, "sysUserMapper", users);
        ReflectionTestUtils.setField(service, "teachingAccessService", access);
        ReflectionTestUtils.setField(service, "teachingWorkCorrectMapper", correct);
        ReflectionTestUtils.setField(service, "teachingWorkCommentMapper", comments);
        departments = mock(SysDepartMapper.class); courses = mock(TeachingCourseMapper.class);
        units = mock(TeachingCourseUnitMapper.class); assignments = mock(TeachingCourseDeptMapper.class);
        additional = mock(TeachingAdditionalWorkMapper.class);
        ReflectionTestUtils.setField(service, "sysDepartMapper", departments);
        ReflectionTestUtils.setField(service, "teachingCourseMapper", courses);
        ReflectionTestUtils.setField(service, "teachingCourseUnitMapper", units);
        ReflectionTestUtils.setField(service, "teachingCourseDeptMapper", assignments);
        ReflectionTestUtils.setField(service, "teachingAdditionalWorkMapper", additional);
        course = new TeachingCourse().setId("course").setDelFlag(0).setIsShared(false);
        unit = new TeachingCourseUnit().setId("unit").setCourseId("course").setDelFlag(0);
        task = new TeachingAdditionalWork().setId("task").setStatus(1).setWorkDept("class-a,class-b");
        when(courses.selectOne(any())).thenReturn(course);
        when(units.selectOne(any())).thenReturn(unit);
        when(additional.selectOne(any())).thenReturn(task);
        when(assignments.selectList(any())).thenReturn(Arrays.asList(
                new TeachingCourseDept().setDeptId("class-a"), new TeachingCourseDept().setDeptId("class-b")));
        when(departments.queryUserDeparts(anyString())).thenReturn(Arrays.asList(depart("class-a"), depart("class-b")));
        source = new TeachingWork(); source.setId("source"); source.setUserId("teacher");
        source.setDepartId("class-a"); source.setWorkName("同名作品"); source.setWorkFile("teacher-file");
        source.setWorkCover("teacher-cover"); source.setWorkType("1"); source.setDelFlag(0);
        source.setWorkStatus("4"); source.setHasCloudData(true); source.setStarNum(30); source.setCollectNum(20);
        source.setViewNum(50); source.setCreateBy("old-author"); source.setUpdateBy("old-editor");
        source.setUpdateTime(new Date(0)); source.setSysOrgCode("old-org");
        when(works.selectOne(any())).thenReturn(source);
        when(users.selectOne(any())).thenAnswer(invocation -> {
            QueryWrapper<SysUser> query = invocation.getArgument(0);
            query.getSqlSegment();
            String id = String.valueOf(query.getParamNameValuePairs().values().iterator().next());
            return new SysUser().setId(id).setUsername("student").setDelFlag(0).setStatus(1);
        });
        when(works.selectList(any())).thenReturn(Collections.emptyList());
        when(works.insert(any(TeachingWork.class))).thenReturn(1);
    }

    private StudentWorkSendVO request(String... ids) {
        StudentWorkSendVO request = new StudentWorkSendVO(); request.setSendWorkId("source");
        request.setUserIdList(Arrays.asList(ids)); return request;
    }

    private SysDepart depart(String id) {
        SysDepart depart = new SysDepart(); depart.setId(id); depart.setDelFlag("0"); return depart;
    }

    private void rejectsTaskBeforeInsert(String... recipients) {
        try { service.sendWork(request(recipients)); fail("Recipient task eligibility must be checked before INSERT"); }
        catch (JeecgBootException expected) { assertTrue(expected.getMessage().contains("任务")); }
        verify(works, never()).insert(any());
    }

    @Test public void cloneInsertsANewDraftAndNeverLooksUpByNameOrCopiesFeedback() {
        assertEquals(1, service.sendWork(request("a")));
        ArgumentCaptor<TeachingWork> capture = ArgumentCaptor.forClass(TeachingWork.class);
        verify(works).insert(capture.capture()); TeachingWork copy = capture.getValue();
        assertNull(copy.getId()); assertEquals("a", copy.getUserId());
        assertEquals("同名作品", copy.getWorkName()); assertEquals("teacher-file", copy.getWorkFile());
        assertEquals("teacher-cover", copy.getWorkCover()); assertEquals("class-a", copy.getDepartId());
        assertEquals("0", copy.getWorkStatus()); assertEquals(Boolean.FALSE, copy.getHasCloudData());
        assertEquals(Integer.valueOf(0), copy.getStarNum()); assertEquals(Integer.valueOf(0), copy.getCollectNum());
        assertEquals(Integer.valueOf(0), copy.getViewNum());
        assertNull(copy.getCreateBy()); assertNull(copy.getUpdateBy()); assertNull(copy.getUpdateTime()); assertNull(copy.getSysOrgCode());
        verify(works, never()).selectByMap(anyMap()); verify(works, never()).selectList(any());
        verify(works, never()).updateById(any()); verifyZeroInteractions(correct, comments);
        assertEquals("4", source.getWorkStatus()); assertEquals(Integer.valueOf(30), source.getStarNum());
    }

    @Test public void sameTaskConflictFailsBeforeTheFirstInsert() {
        for (boolean additional : new boolean[]{false, true}) {
            source.setCourseId(additional ? null : "unit-b"); source.setAdditionalId(additional ? "task-b" : null);
            when(works.selectList(any())).thenReturn(Collections.emptyList(), Collections.singletonList(new TeachingWork()));
            try { service.sendWork(request("a", "b")); fail("Must reject task conflict"); }
            catch (JeecgBootException expected) { assertTrue(expected.getMessage().contains("已有该任务")); }
        }
        verify(works, never()).insert(any());
    }

    @Test public void invalidRecipientOrDuplicateBatchDoesNotSkipOrPartiallyWrite() {
        doReturn(new SysUser().setId("a").setDelFlag(0).setStatus(1), null).when(users).selectOne(any());
        try { service.sendWork(request("a", "z-missing")); fail("Missing recipient must fail"); }
        catch (JeecgBootException expected) { assertTrue(expected.getMessage().contains("不可用")); }
        try { service.sendWork(request("a", "a")); fail("Duplicate recipient must fail"); }
        catch (JeecgBootException expected) { assertTrue(expected.getMessage().contains("重复")); }
        verify(works, never()).insert(any());
    }

    @Test public void noncanonicalRecipientIdentityRejectsTheEntireBatchBeforeInsert() {
        doReturn(new SysUser().setId("a").setDelFlag(0).setStatus(1)).when(users).selectOne(any());
        for (String alias : new String[]{"A", "a "}) {
            try { service.sendWork(request(alias)); fail("Collation alias must not become the owner ID"); }
            catch (JeecgBootException expected) { assertTrue(expected.getMessage().contains("不可用")); }
        }
        verify(works, never()).insert(any());
    }

    @Test public void insertFailurePropagatesToTheTransactionRatherThanReportingPartialSuccess() {
        when(works.insert(any(TeachingWork.class))).thenReturn(1, 0);
        try { service.sendWork(request("a", "b")); fail("Second insert failure must propagate"); }
        catch (JeecgBootException expected) { assertTrue(expected.getMessage().contains("克隆失败")); }
        verify(works, times(2)).insert(any());
    }

    @Test public void deletedSourceAndAmbiguousTaskIdentityFailBeforeAnyInsert() {
        source.setDelFlag(1);
        try { service.sendWork(request("a")); fail("Deleted source must fail"); }
        catch (JeecgBootException expected) { assertTrue(expected.getMessage().contains("已删除")); }
        source.setDelFlag(0); source.setCourseId("unit"); source.setAdditionalId("assignment");
        try { service.sendWork(request("a")); fail("Ambiguous task identity must fail"); }
        catch (JeecgBootException expected) { assertTrue(expected.getMessage().contains("任务归属异常")); }
        verify(works, never()).insert(any()); verifyZeroInteractions(users);
    }

    @Test public void managementPermissionDoesNotAuthorizeRecipientsOutsideTheSourcesClass() {
        when(departments.queryUserDeparts("b")).thenReturn(Collections.singletonList(depart("class-b")));
        for (boolean isAdditional : new boolean[]{false, true}) {
            source.setCourseId(isAdditional ? null : "unit"); source.setAdditionalId(isAdditional ? "task" : null);
            // Both classes have this task and the actor's manage check permits it.
            // The source's class must nevertheless be the recipient's own class.
            rejectsTaskBeforeInsert("a", "b");
        }
    }

    @Test public void removedSourceClassAssignmentRejectsEvenAMemberOrSharedCourse() {
        source.setCourseId("unit"); course.setIsShared(true);
        when(assignments.selectList(any())).thenReturn(Collections.singletonList(new TeachingCourseDept().setDeptId("class-b")));
        rejectsTaskBeforeInsert("a");
        source.setCourseId(null); source.setAdditionalId("task"); task.setWorkDept("class-b");
        rejectsTaskBeforeInsert("a");
    }

    @Test public void missingOrDeletedTasksAndInactiveAdditionalAssignmentsRejectBeforeWrites() {
        source.setCourseId("unit");
        unit.setDelFlag(1); rejectsTaskBeforeInsert("a"); unit.setDelFlag(0);
        course.setDelFlag(1); rejectsTaskBeforeInsert("a"); course.setDelFlag(0);
        when(units.selectOne(any())).thenReturn(null); rejectsTaskBeforeInsert("a");
        when(units.selectOne(any())).thenReturn(unit);
        when(courses.selectOne(any())).thenReturn(null); rejectsTaskBeforeInsert("a");
        source.setCourseId(null); source.setAdditionalId("task");
        task.setStatus(0); rejectsTaskBeforeInsert("a"); task.setStatus(1);
        when(additional.selectOne(any())).thenReturn(null); rejectsTaskBeforeInsert("a");
    }

    @Test public void unboundCourseDerivesRecipientClassAndDoesNotUseActorAdminAsAnEligibilityBypass() {
        source.setCourseId("unit"); source.setDepartId("");
        when(departments.queryUserDeparts("a")).thenReturn(Collections.singletonList(depart("class-b")));
        assertEquals(1, service.sendWork(request("a")));
        ArgumentCaptor<TeachingWork> saved = ArgumentCaptor.forClass(TeachingWork.class);
        verify(works).insert(saved.capture()); assertEquals("class-b", saved.getValue().getDepartId());
        clearInvocations(works);
        when(departments.queryUserDeparts("a")).thenReturn(Collections.emptyList());
        when(access.isAdministrator()).thenReturn(true);
        rejectsTaskBeforeInsert("a");
        course.setIsShared(true);
        assertEquals(1, service.sendWork(request("a")));
        verify(works).insert(saved.capture()); assertEquals("", saved.getValue().getDepartId());
    }

    @Test public void unboundAdditionalRequiresAnActiveMembershipAndDerivesItsClass() {
        source.setAdditionalId("task"); source.setDepartId(null);
        SysDepart deleted = depart("class-a"); deleted.setDelFlag("1");
        when(departments.queryUserDeparts("a")).thenReturn(Collections.singletonList(deleted));
        rejectsTaskBeforeInsert("a");
        when(departments.queryUserDeparts("a")).thenReturn(Collections.singletonList(depart("class-b")));
        assertEquals(1, service.sendWork(request("a")));
        ArgumentCaptor<TeachingWork> saved = ArgumentCaptor.forClass(TeachingWork.class);
        verify(works).insert(saved.capture()); assertEquals("class-b", saved.getValue().getDepartId());
    }
}
