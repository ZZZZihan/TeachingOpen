package org.jeecg.registration;

import com.alibaba.fastjson.JSONObject;
import org.jeecg.common.api.vo.Result;
import org.jeecg.modules.system.entity.SysRole;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.service.*;
import org.junit.Before;
import org.junit.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.SimpleTransactionStatus;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class RegistrationServiceTest {
    private ISysUserService users;
    private ISysConfigService config;
    private ISysRoleService roles;
    private PlatformTransactionManager manager;
    private RegistrationService service;

    @Before public void setup() {
        users = mock(ISysUserService.class); config = mock(ISysConfigService.class);
        roles = mock(ISysRoleService.class); manager = mock(PlatformTransactionManager.class);
        when(config.getConfigItem("allowReg")).thenReturn("1");
        when(users.save(any(SysUser.class))).thenAnswer(call -> { ((SysUser) call.getArgument(0)).setId("synthetic-id"); return true; });
        when(manager.getTransaction(any())).thenReturn(new SimpleTransactionStatus());
        service = new RegistrationService(users, config, roles, mock(ISysDepartService.class), manager);
    }
    private JSONObject request() {
        JSONObject r = new JSONObject(); r.put("username", "synthetic_student"); r.put("realname", "合成学生");
        r.put("password", "Synthetic8!"); return r;
    }
    private void state(Result<JSONObject> result, String state) {
        assertFalse(result.isSuccess()); assertEquals(state, result.getResult().getString("registrationState"));
    }
    @Test public void closedRegistrationCannotWrite() {
        when(config.getConfigItem("allowReg")).thenReturn("0"); state(service.register(request()), "closed");
        verifyZeroInteractions(users, manager);
    }
    @Test public void nonStringAndMalformedRequestsCannotWrite() {
        state(service.register(null), "invalid_username");
        for (String field : new String[]{"username", "realname", "password"}) {
            JSONObject r = request(); r.put(field, new JSONObject()); assertFalse(service.register(r).isSuccess());
        }
        JSONObject r = request(); r.put("password", "Abcd123!中文"); state(service.register(r), "invalid_password");
        r = request(); r.put("realname", "😀"); state(service.register(r), "invalid_realname");
        verifyZeroInteractions(users, manager);
    }
    @Test public void duplicateAccountNeverWrites() {
        when(users.getUserByName(anyString())).thenReturn(new SysUser()); state(service.register(request()), "duplicate"); verifyZeroInteractions(manager);
    }
    @Test public void unsafeDefaultRoleCannotWrite() {
        when(config.getConfigItem("_defaultRole")).thenReturn("role_admin"); when(roles.getById("role_admin")).thenReturn(new SysRole().setId("role_admin").setRoleCode("admin"));
        state(service.register(request()), "invalid_defaults"); verifyZeroInteractions(manager);
    }
    @Test public void registrationNeedsNoPhoneOrSmsCode() {
        Result<JSONObject> result = service.register(request()); assertTrue(result.isSuccess());
        ArgumentCaptor<SysUser> saved = ArgumentCaptor.forClass(SysUser.class); verify(users).save(saved.capture());
        assertNull(saved.getValue().getPhone()); verify(users, never()).getUserByPhone(anyString());
    }
    @Test public void registrationDoesNotBindClientPrivilegesOrReturnSecrets() {
        JSONObject r = request(); r.put("id", "fixture_admin"); r.put("status", 2); r.put("userIdentity", 2); r.put("roles", "admin"); r.put("school", "external"); r.put("phone", "19900000001"); r.put("smscode", "untrusted");
        Result<JSONObject> result = service.register(r); assertTrue(result.isSuccess()); assertEquals(1, result.getResult().size());
        ArgumentCaptor<SysUser> saved = ArgumentCaptor.forClass(SysUser.class); verify(users).save(saved.capture());
        SysUser user = saved.getValue(); assertEquals(Integer.valueOf(1), user.getStatus()); assertEquals(Integer.valueOf(1), user.getUserIdentity());
        assertEquals("", user.getSchool()); assertNull(user.getDepartIds()); assertNull(user.getEmail()); assertNull(user.getPhone()); assertNotEquals(r.getString("password"), user.getPassword()); verify(manager).commit(any());
    }
    @Test public void relationshipFailureRequestsRollbackAndFixedRetryState() {
        when(config.getConfigItem("_defaultRole")).thenReturn("role_student"); when(roles.getById("role_student")).thenReturn(new SysRole().setId("role_student").setRoleCode("student"));
        doThrow(new IllegalStateException("private SQL and credentials")).when(users).addUserWithRole(any(), anyString());
        Result<JSONObject> result = service.register(request()); state(result, "registration_failed"); assertFalse(result.getMessage().contains("private")); verify(manager).rollback(any()); verify(manager, never()).commit(any());
    }
    @Test public void failedSaveRollsBack() {
        when(users.save(any(SysUser.class))).thenReturn(false); state(service.register(request()), "registration_failed"); verify(manager).rollback(any());
    }
    @Test public void unavailableConfigurationNeverWrites() {
        when(config.getConfigItem("allowReg")).thenThrow(new IllegalStateException("private"));
        state(service.register(request()), "service_unavailable"); verifyZeroInteractions(users, manager);
    }
    @Test public void registrationRechecksOpenSwitchInsideTransaction() {
        when(config.getConfigItem("allowReg")).thenReturn("1", "0");
        state(service.register(request()), "registration_failed"); verify(manager).rollback(any()); verify(users, never()).save(any());
    }
}
