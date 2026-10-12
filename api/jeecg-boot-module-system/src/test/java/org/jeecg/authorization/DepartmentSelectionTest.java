package org.jeecg.authorization;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.RedisUtil;
import org.jeecg.modules.system.entity.*;
import org.jeecg.modules.system.mapper.*;
import org.jeecg.modules.system.model.DepartmentSelectionRequest;
import org.jeecg.modules.system.service.DepartmentSelectionService;
import org.junit.*;
import org.mockito.ArgumentCaptor;
import org.springframework.transaction.support.*;
import java.util.*;
import static org.junit.Assert.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

public class DepartmentSelectionTest {
    private SysUserMapper users; private SysDepartMapper departments; private SysUserDepartMapper memberships;
    private RedisUtil redis; private DepartmentSelectionService service; private DepartmentSelectionRequest request;
    @Before public void setup() {
        users=mock(SysUserMapper.class); departments=mock(SysDepartMapper.class); memberships=mock(SysUserDepartMapper.class); redis=mock(RedisUtil.class);
        service=new DepartmentSelectionService(users,departments,memberships,redis);
        LoginUser identity=new LoginUser(); identity.setId("a"); identity.setUsername("alice");
        Subject subject=mock(Subject.class); when(subject.getPrincipal()).thenReturn(identity); ThreadContext.bind(subject);
        SysDepart department=new SysDepart(); department.setId("class-a"); department.setOrgCode("A01"); department.setDelFlag("0");
        when(departments.selectOne(any())).thenReturn(department);
        when(users.lockAdministrationUsers(Arrays.asList("a"))).thenReturn(Arrays.asList(new SysUser().setId("a").setUsername("alice").setStatus(1).setDelFlag(0)));
        when(memberships.selectList(any())).thenReturn(Arrays.asList(new SysUserDepart("membership","a","class-a")));
        when(users.update(any(),any())).thenReturn(1);
        request=new DepartmentSelectionRequest(); request.setOrgCode("A01"); request.setUsername("alice");
    }
    @After public void cleanup() {
        ThreadContext.unbindSubject();
        if(TransactionSynchronizationManager.isSynchronizationActive()) TransactionSynchronizationManager.clearSynchronization();
    }
    private void denied() {
        try { service.select(request); fail("must reject authorization"); } catch(UnauthorizedException expected) { }
        verify(users,never()).update(any(),any()); verifyZeroInteractions(redis);
    }
    @Test public void otherUsernameIsRejectedBeforeAnyQueryOrCacheChange() {
        request.setUsername("bob"); denied(); verifyZeroInteractions(users,departments,memberships);
    }
    @Test public void nonMembershipDoesNotWriteOrEvict() {
        when(memberships.selectList(any())).thenReturn(Collections.emptyList()); denied();
    }
    @Test public void aliasOrUnknownOrganizationCannotSelectAnotherRange() {
        for(String code:Arrays.asList("a01","A01%","A01'","unknown","")) { request.setOrgCode(code); denied(); }
    }
    @Test public void frozenUserAndRevokedMembershipAreDenied() {
        when(users.lockAdministrationUsers(anyList())).thenReturn(Arrays.asList(new SysUser().setId("a").setUsername("alice").setStatus(2).setDelFlag(0)));
        denied(); verify(memberships,never()).selectList(any());
    }
    @Test public void ownMembershipUpdatesOnlyOrgCodeAndEvictsAfterCommit() {
        request.setUsername(null); TransactionSynchronizationManager.initSynchronization();
        SysUser result=service.select(request); assertEquals("A01",result.getOrgCode());
        ArgumentCaptor<SysUser> patch=ArgumentCaptor.forClass(SysUser.class); verify(users).update(patch.capture(),any());
        assertEquals("A01",patch.getValue().getOrgCode()); assertNull(patch.getValue().getUsername()); assertNull(patch.getValue().getDepartIds());
        verifyZeroInteractions(redis);
        for(TransactionSynchronization callback:TransactionSynchronizationManager.getSynchronizations()) callback.afterCommit();
        verify(redis).del("sys:cache:user::alice");
    }
    @Test public void failedDatabaseUpdateDoesNotEvict() {
        when(users.update(any(),any())).thenThrow(new org.springframework.dao.DataIntegrityViolationException("synthetic"));
        try { service.select(request); fail("database failure"); } catch(org.springframework.dao.DataIntegrityViolationException expected) { }
        verifyZeroInteractions(redis);
    }
}
