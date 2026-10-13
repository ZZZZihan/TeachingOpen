package org.jeecg.authorization;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.shiro.authz.UnauthorizedException;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.*;
import org.jeecg.modules.system.mapper.*;
import org.jeecg.modules.system.model.UserProfileView;
import org.jeecg.modules.system.service.*;
import org.junit.*;
import java.util.*;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

public class UserReadAuthorizationTest {
    private SysUserMapper users; private SysUserRoleMapper roles; private SysUserDepartMapper memberships;
    private ISysDepartService departments; private UserQueryAccessService access; private UserProfileReadService service;
    private SysUser actor, target; private LoginUser principal;
    @Before public void setup() {
        users=mock(SysUserMapper.class); roles=mock(SysUserRoleMapper.class); memberships=mock(SysUserDepartMapper.class);
        departments=mock(ISysDepartService.class);
        access=new UserQueryAccessService(users,roles,mock(SysDepartMapper.class),departments);
        service=new UserProfileReadService(access,users,memberships);
        actor=populated("actor"); target=populated("target");
        principal=new LoginUser(); principal.setId("actor"); principal.setUsername("actor"); principal.setDepartIds("stale");
        Subject subject=mock(Subject.class); when(subject.getPrincipal()).thenReturn(principal); ThreadContext.bind(subject);
        when(users.selectById("actor")).thenReturn(actor);
        when(users.selectBatchIds(anyCollection())).thenAnswer(call -> {
            Collection<String> ids=call.getArgument(0); List<SysUser> results=new ArrayList<>();
            if(ids.contains("actor")) results.add(actor); if(ids.contains("target")) results.add(target); return results;
        });
        when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("student"));
        when(departments.getMySubDepIdsByDepId("class-a")).thenReturn(Arrays.asList("class-a"));
        when(memberships.selectList(any())).thenReturn(Arrays.asList(new SysUserDepart("m","target","class-a")));
    }
    @After public void cleanup() { ThreadContext.unbindSubject(); }
    private SysUser populated(String id) {
        return new SysUser().setId(id).setUsername(id).setRealname("name").setAvatar("avatar")
            .setPassword("sensitive-password").setSalt("sensitive-salt").setEmail("private@example.test").setPhone("12345678901")
            .setBirthday(new Date(0)).setSex(1).setSchool("school").setTelephone("landline").setPost("post").setWorkNo("staff")
            .setStatus(1).setDelFlag(0).setUserIdentity(2).setDepartIds("class-a").setOrgCode("A01")
            .setCreateTime(new Date(0)).setUpdateTime(new Date(0)).setThirdId("provider-secret").setThirdType("test");
    }
    private Set<String> fields(UserProfileView view) {
        return new ObjectMapper().convertValue(view,Map.class).keySet();
    }
    private void denied(Runnable call) { try { call.run(); fail("authorization denial required"); } catch(UnauthorizedException expected) { } }
    @Test public void ordinaryUserCannotReadPeerEvenIfSameClass() {
        denied(()->service.read("target"));
        denied(()->service.readAll(Arrays.asList("actor","target")));
        verify(memberships,never()).selectList(any());
    }
    @Test public void selfHasExactProfileFieldsAndNoCredentialsOrAdministrativeFields() {
        assertEquals(new HashSet<>(Arrays.asList("id","username","realname","avatar","sex","birthday","email","phone","telephone","school","workNo","post","orgCode")), fields(service.read("actor")));
    }
    @Test public void assignedTeacherHasOnlyMinimalStudentFields() {
        when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("teacher"));
        assertEquals(new HashSet<>(Arrays.asList("id","username","realname","avatar")), fields(service.read("target")));
        verify(departments).getMySubDepIdsByDepId("class-a");
        verify(departments,never()).getMySubDepIdsByDepId("stale");
    }
    @Test public void crossClassOrRevokedTeacherDoesNotGetPartialBatch() {
        when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("teacher"));
        when(memberships.selectList(any())).thenReturn(Collections.emptyList());
        denied(()->service.readAll(Arrays.asList("actor","target")));
        when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("student"));
        denied(()->service.read("target"));
    }
    @Test public void administratorHasExplicitManagementFieldsWithoutSecrets() {
        when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("admin"));
        Set<String> expected=new HashSet<>(Arrays.asList("id","username","realname","avatar","sex","birthday","email","phone","telephone","school","workNo","post","orgCode",
            "status","delFlag","userIdentity","departIds","createTime","updateTime"));
        assertEquals(expected, fields(service.read("target")));
        verify(memberships,never()).selectList(any());
    }
    @Test public void missingAliasAndOversizedBatchesFailAsAWhole() {
        when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("admin"));
        denied(()->service.readAll(Arrays.asList("actor","missing")));
        denied(()->service.read("TARGET"));
        clearInvocations(users);
        try { service.readAll(Collections.nCopies(101,"actor")); fail("oversized"); } catch(JeecgBootException expected) { }
        verify(users,never()).selectBatchIds(anyCollection());
    }
    @Test public void retiredTokenCannotRelyOnCachedAdministratorRole() {
        when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("admin")); assertNotNull(service.read("target").getEmail());
        when(roles.getRoleByUserId("actor")).thenReturn(Arrays.asList("student")); denied(()->service.read("target"));
    }
}
