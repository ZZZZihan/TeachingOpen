package org.jeecg.accountrecovery;

import com.alibaba.fastjson.JSONObject;
import org.jeecg.common.api.vo.Result;
import org.jeecg.modules.system.entity.SysRole;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.RegistrationProfileMapper;
import org.jeecg.modules.system.service.*;
import org.junit.Before;
import org.junit.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;
import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class AccountRegistrationServiceTest {
    private ISysUserService users;
    private ISysRoleService roles;
    private ISysConfigService config;
    private RegistrationProfileMapper profiles;
    private PlatformTransactionManager tx;
    private AccountRegistrationService service;
    @Before public void setup() {
        users = mock(ISysUserService.class); roles = mock(ISysRoleService.class);
        config = mock(ISysConfigService.class); profiles = mock(RegistrationProfileMapper.class);
        tx = mock(PlatformTransactionManager.class);
        when(tx.getTransaction(any())).thenReturn(new SimpleTransactionStatus());
        when(config.getConfigItem("allowReg")).thenReturn("1");
        when(roles.getOne(any())).thenReturn(new SysRole().setId("student-role").setRoleCode("student"));
        when(users.save(any(SysUser.class))).thenAnswer(call -> { ((SysUser) call.getArgument(0)).setId("new-user"); return true; });
        when(profiles.insertProfile(anyString(), anyString())).thenReturn(1);
        service = new AccountRegistrationService(users, roles, config, profiles, tx);
    }
    private JSONObject request() {
        JSONObject r = new JSONObject(); r.put("phone", "13900000001"); r.put("password", "Synthetic8!");
        r.put("realname", " 张同学 "); r.put("school", " 测试学校 "); r.put("identity", "teacher"); return r;
    }
    private void failed(Result<?> result, int code) { assertFalse(result.isSuccess()); assertEquals(Integer.valueOf(code), result.getCode()); assertNull(result.getResult()); }
    @Test public void requiredFieldsAndTypesNeverWrite() {
        for (String field : new String[]{"phone", "password", "realname", "school", "identity"}) {
            JSONObject r = request(); r.remove(field); failed(service.register(r), 400);
            r = request(); r.put(field, new JSONObject()); failed(service.register(r), 400);
        }
        failed(service.register(null), 400); verifyZeroInteractions(users, profiles, tx);
    }
    @Test public void teacherDeclarationCannotGrantPrivilegesOrBindRequestFields() {
        JSONObject r = request(); r.put("username", "admin"); r.put("roles", "admin,teacher");
        r.put("userIdentity", 2); r.put("departIds", "secret"); r.put("status", 2); r.put("id", "admin");
        Result<?> result = service.register(r); assertTrue(result.isSuccess()); assertNull(result.getResult());
        ArgumentCaptor<SysUser> capture = ArgumentCaptor.forClass(SysUser.class); verify(users).save(capture.capture());
        SysUser u = capture.getValue(); assertEquals("13900000001", u.getUsername()); assertEquals("张同学", u.getRealname());
        assertEquals("测试学校", u.getSchool()); assertEquals(Integer.valueOf(1), u.getUserIdentity()); assertEquals("", u.getDepartIds());
        assertEquals(Integer.valueOf(1), u.getStatus()); assertNotEquals("Synthetic8!", u.getPassword());
        verify(users).addUserWithRole(u, "student-role"); verify(profiles).insertProfile("new-user", "teacher"); verify(tx).commit(any());
    }
    @Test public void disabledMissingRoleAndReservedPhoneFailClosed() {
        when(config.getConfigItem("allowReg")).thenReturn("0"); failed(service.register(request()), 403);
        when(config.getConfigItem("allowReg")).thenReturn("1"); when(profiles.countReservedPhone(anyString())).thenReturn(1); failed(service.register(request()), 409);
        when(profiles.countReservedPhone(anyString())).thenReturn(0); when(roles.getOne(any())).thenReturn(null); failed(service.register(request()), 503);
        verifyZeroInteractions(users, tx);
    }
    @Test public void concurrentUniqueConstraintFailureRollsBackAndReturnsConflict() {
        when(users.save(any(SysUser.class))).thenThrow(new DuplicateKeyException("private"));
        failed(service.register(request()), 409); verify(tx).rollback(any()); verify(profiles, never()).insertProfile(anyString(), anyString());
    }
    @Test public void profileOrRoleFailureRollsBackWholeRegistration() {
        when(profiles.insertProfile(anyString(), anyString())).thenReturn(0); failed(service.register(request()), 503); verify(tx).rollback(any());
        reset(tx); when(tx.getTransaction(any())).thenReturn(new SimpleTransactionStatus());
        when(profiles.insertProfile(anyString(), anyString())).thenReturn(1);
        doThrow(new IllegalStateException("private")).when(users).addUserWithRole(any(), anyString());
        failed(service.register(request()), 503); verify(tx).rollback(any()); verify(tx, never()).commit(any());
    }
}
