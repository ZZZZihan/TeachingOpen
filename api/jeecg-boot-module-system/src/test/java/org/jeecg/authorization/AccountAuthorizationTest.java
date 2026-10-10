package org.jeecg.authorization;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.apache.shiro.authz.UnauthorizedException;
import org.apache.shiro.authz.AuthorizationInfo;
import org.apache.shiro.authz.SimpleAuthorizationInfo;
import org.apache.shiro.cache.Cache;
import org.apache.shiro.cache.CacheException;
import org.apache.shiro.cache.CacheManager;
import org.apache.shiro.cache.MapCache;
import org.apache.shiro.subject.PrincipalCollection;
import org.apache.shiro.subject.SimplePrincipalCollection;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.config.ShiroConfig;
import org.jeecg.modules.shiro.authc.ShiroRealm;
import org.jeecg.modules.system.entity.*;
import org.jeecg.modules.system.mapper.*;
import org.jeecg.modules.system.model.UserProfileRequest;
import org.jeecg.modules.system.service.*;
import org.junit.*;
import org.mockito.ArgumentCaptor;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.test.util.ReflectionTestUtils;
import org.crazycake.shiro.RedisCacheManager;
import java.util.*;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

public class AccountAuthorizationTest {
    private SysUserMapper users;
    private SysRoleMapper roles;
    private SysUserRoleMapper assignments;
    private SysUserDepartMapper departments;
    private SysDepartRoleUserMapper departmentRoles;
    private PasswordResetCodeStore caches;
    private AccountAdministrationService service;
    private SysUser operator, target;

    @Before public void setup() {
        for (Class<?> type : Arrays.asList(SysUser.class, SysUserRole.class, SysUserDepart.class, SysDepartRoleUser.class, SysRole.class)) {
            TableInfoHelper.initTableInfo(new MapperBuilderAssistant(new MybatisConfiguration(), "authorization-test"), type);
        }
        users=mock(SysUserMapper.class); roles=mock(SysRoleMapper.class); assignments=mock(SysUserRoleMapper.class);
        departments=mock(SysUserDepartMapper.class); departmentRoles=mock(SysDepartRoleUserMapper.class);
        caches=mock(PasswordResetCodeStore.class);
        service=new AccountAdministrationService(users,roles,assignments,departments,departmentRoles,mock(SysDepartMapper.class),caches);
        operator=new SysUser().setId("admin-id").setUsername("administrator").setDelFlag(0).setStatus(1);
        target=new SysUser().setId("student-id").setUsername("student").setDelFlag(0).setStatus(1);
        LoginUser principal=new LoginUser(); principal.setId(operator.getId()); principal.setUsername(operator.getUsername());
        Subject subject=mock(Subject.class); when(subject.getPrincipal()).thenReturn(principal); ThreadContext.bind(subject);
        when(assignments.getRoleByUserId(operator.getId())).thenReturn(Arrays.asList("admin"));
        when(assignments.getUserRoleLevel(operator.getId())).thenReturn(9);
        when(assignments.getUserRoleLevel(target.getId())).thenReturn(1);
        when(users.lockAdministrationUsers(anyList())).thenReturn(Arrays.asList(operator,target));
        when(roles.selectById("student-role")).thenReturn(new SysRole().setId("student-role").setRoleCode("student").setRoleLevel(1));
        when(assignments.selectCount(any())).thenReturn(0); when(assignments.insert(any())).thenReturn(1);
    }
    @After public void cleanup() {
        if(TransactionSynchronizationManager.isSynchronizationActive()) TransactionSynchronizationManager.clearSynchronization();
        ThreadContext.unbindSubject();
    }
    private void denied(Runnable operation) {
        try { operation.run(); fail("request must be rejected"); } catch (RuntimeException expected) { }
    }
    @Test public void studentCannotGrantAnyRoleEvenToSelf() {
        when(assignments.getRoleByUserId(operator.getId())).thenReturn(Arrays.asList("student"));
        denied(()->service.changeRole("student-role",Arrays.asList(operator.getId()),true));
        verify(assignments,never()).insert(any()); verify(users,never()).lockAdministrationUsers(anyList());
    }
    @Test public void teacherCannotGrantRoles() {
        when(assignments.getRoleByUserId(operator.getId())).thenReturn(Arrays.asList("teacher"));
        denied(()->service.changeRole("student-role",Arrays.asList(target.getId()),true));
        verify(assignments,never()).insert(any());
    }
    @Test public void missingOrCaseAliasedBatchHasNoWrites() {
        denied(()->service.changeRole("student-role",Arrays.asList(target.getId(),"missing"),true));
        denied(()->service.changeRole("student-role",Arrays.asList("STUDENT-ID"),true));
        verify(assignments,never()).insert(any());
    }
    @Test public void roleAboveOperatorIsRejected() {
        when(roles.selectById("high-role")).thenReturn(new SysRole().setId("high-role").setRoleCode("dev").setRoleLevel(99));
        denied(()->service.changeRole("high-role",Arrays.asList(target.getId()),true));
        verify(assignments,never()).insert(any());
    }
    @Test public void excelImportCannotBypassGrantLevel() {
        SysRole developer = new SysRole().setId("developer-role").setRoleCode("dev").setRoleLevel(10);
        when(roles.selectList(any())).thenReturn(Collections.singletonList(developer));
        when(roles.selectById("developer-role")).thenReturn(developer);
        denied(() -> service.importAccount(new SysUser().setUsername("newuser").setPassword("SecurePassword9!"), "dev", null, false));
        verify(users, never()).insert(any()); verify(assignments, never()).insert(any());
    }
    @Test public void importRejectsMissingRoleBeforeCreatingAnAccount() {
        when(roles.selectList(any())).thenReturn(Collections.emptyList());
        denied(() -> service.importAccount(new SysUser().setUsername("newuser"), "missing", null, false));
        verify(users, never()).insert(any()); verify(assignments, never()).insert(any());
    }
    @Test public void importNeverSuppliesAPredictableDefaultPassword() {
        SysRole student = new SysRole().setId("student-role").setRoleCode("student").setRoleLevel(1);
        when(roles.selectList(any())).thenReturn(Collections.singletonList(student));
        denied(() -> service.importAccount(new SysUser().setUsername("newuser"), "student", null, false));
        verify(users, never()).insert(any());
    }
    @Test public void roleGrantClearsCachesOnlyAfterCommit() {
        TransactionSynchronizationManager.initSynchronization();
        service.changeRole("student-role",Arrays.asList(target.getId()),true);
        verify(assignments).insert(any()); verifyZeroInteractions(caches);
        for(TransactionSynchronization callback:TransactionSynchronizationManager.getSynchronizations()) callback.afterCommit();
        verify(caches).clearUserCaches(target.getId(),target.getUsername());
    }
    @Test public void normalAccountCannotBePurgedOrRestored() {
        denied(()->service.recycle(Arrays.asList(target.getId()),false));
        denied(()->service.recycle(Arrays.asList(target.getId()),true));
        verify(users,never()).deleteLogicDeleted(anyList()); verify(departments,never()).delete(any());
        verify(assignments,never()).delete(any()); verify(users,never()).revertLogicDeleted(anyList(),any());
    }
    @Test public void recyclePassesBoundIdsAndCleansOnlyConfirmedUsers() {
        target.setDelFlag(1); when(users.deleteLogicDeleted(Arrays.asList(target.getId()))).thenReturn(1);
        service.recycle(Arrays.asList(target.getId()),false);
        verify(users).deleteLogicDeleted(Arrays.asList(target.getId())); verify(departmentRoles).delete(any());
        verify(caches).clearUserCaches(target.getId(),target.getUsername());
    }
    @Test public void resetUsesCanonicalUsernameAndCredentialOnlyPatch() {
        when(users.update(any(),any())).thenReturn(1);
        service.resetPassword(target.getId(),"NewSecure9!");
        ArgumentCaptor<SysUser> patch=ArgumentCaptor.forClass(SysUser.class); verify(users).update(patch.capture(),any());
        SysUser saved=patch.getValue(); assertNotNull(saved.getPassword()); assertNotNull(saved.getSalt());
        assertNull(saved.getUsername()); assertNull(saved.getStatus()); assertNull(saved.getDepartIds()); assertNull(saved.getPhone());
    }
    @Test public void profileRejectsForeignIdentityBeforeWriting() {
        UserProfileRequest request=new UserProfileRequest(); request.setId(target.getId()); request.setRealname("other");
        denied(()->new UserProfileService(users).update(request)); verify(users,never()).update(any(),any());
    }
    @Test public void profilePayloadRejectsCredentialAndScopeFields() throws Exception {
        for(String field:Arrays.asList("password","salt","phone","status","departIds","selectedroles","username")) {
            try { new ObjectMapper().readValue("{\"realname\":\"name\",\""+field+"\":\"bad\"}",UserProfileRequest.class); fail(field); }
            catch(com.fasterxml.jackson.databind.JsonMappingException expected) { }
        }
        assertEquals("name",new ObjectMapper().readValue("{\"realname\":\"name\"}",UserProfileRequest.class).getRealname());
    }

    @Test public void realmIgnoresSurvivingDeveloperCacheAfterDatabaseRevocation() {
        ShiroRealm realm = new ShiroRealm();
        ISysUserService liveUsers = mock(ISysUserService.class);
        ReflectionTestUtils.setField(realm, "sysUserService", liveUsers);
        LoginUser principal = new LoginUser(); principal.setId("former-dev"); principal.setUsername("former_dev");
        PrincipalCollection principals = new SimplePrincipalCollection(principal, realm.getName());
        SimpleAuthorizationInfo old = new SimpleAuthorizationInfo(new HashSet<>(Arrays.asList("admin", "dev")));
        old.addStringPermission("*");
        Map<Object, AuthorizationInfo> stored = new HashMap<>(); stored.put(principals, old);
        Cache<Object, AuthorizationInfo> stale = spy(new MapCache<>(realm.getAuthorizationCacheName(), stored));
        CacheManager manager = mock(CacheManager.class);
        doReturn(stale).when(manager).getCache(anyString());
        doThrow(new CacheException("synthetic eviction failure")).when(stale).remove(principals);
        try { stale.remove(principals); fail("injected eviction failure must occur"); }
        catch (CacheException expected) { }
        assertSame(old, stored.get(principals));
        clearInvocations(stale, manager);
        realm.setCacheManager(manager);
        realm.init();
        assertFalse(realm.isAuthorizationCachingEnabled());
        when(liveUsers.getUserRolesSet("former_dev")).thenReturn(new HashSet<>(Arrays.asList("admin", "dev")));
        when(liveUsers.getUserPermissionsSet("former_dev")).thenReturn(Collections.singleton("sys:role:add"));
        assertTrue(realm.hasRole(principals, "dev")); assertTrue(realm.hasRole(principals, "admin"));
        assertTrue(realm.isPermitted(principals, "sys:role:add"));
        when(liveUsers.getUserRolesSet("former_dev")).thenReturn(Collections.singleton("student"));
        when(liveUsers.getUserPermissionsSet("former_dev")).thenReturn(Collections.emptySet());
        assertFalse(realm.hasRole(principals, "dev")); assertFalse(realm.hasRole(principals, "admin"));
        assertFalse(realm.isPermitted(principals, "sys:role:add"));
        assertSame(old, stored.get(principals));
        verify(manager, never()).getCache(anyString());
        verify(stale, never()).get(any()); verify(stale, never()).put(any(), any());
        verify(liveUsers, times(6)).getUserRolesSet("former_dev");
        verify(liveUsers, times(6)).getUserPermissionsSet("former_dev");
    }

    @Test public void shiroConfigurationCannotReattachAnOldAuthorizationCache() {
        ShiroRealm realm = new ShiroRealm();
        boolean authenticationCaching = realm.isAuthenticationCachingEnabled();
        realm.setAuthorizationCachingEnabled(true);
        realm.setAuthorizationCache(mock(Cache.class));
        RedisCacheManager manager = mock(RedisCacheManager.class);
        ShiroConfig configuration = new ShiroConfig() {
            @Override public RedisCacheManager redisCacheManager() { return manager; }
        };
        configuration.securityManager(realm);
        assertFalse(realm.isAuthorizationCachingEnabled()); assertNull(realm.getAuthorizationCache());
        assertEquals(authenticationCaching, realm.isAuthenticationCachingEnabled());
        assertSame(manager, realm.getCacheManager());
        verify(manager, never()).getCache(anyString());
    }
}
