package org.jeecg.accountrecovery;

import com.alibaba.fastjson.JSONObject;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.util.PasswordUtil;
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
        JSONObject r = new JSONObject(); r.put("username", " learner_01 "); r.put("password", "Synthetic8!");
        r.put("realname", " 张同学 "); r.put("school", " 测试学校 "); return r;
    }
    private Result<JSONObject> register(JSONObject request, boolean teacher) {
        return teacher ? service.registerTeacher(request) : service.register(request);
    }
    private void failed(Result<?> result, int code) { assertFalse(result.isSuccess()); assertEquals(Integer.valueOf(code), result.getCode()); assertNull(result.getResult()); }
    @Test public void requiredFieldsAndTypesNeverWrite() {
        for (boolean teacher : new boolean[]{false, true}) {
            for (String field : new String[]{"username", "password", "realname", "school"}) {
                JSONObject r = request(); r.remove(field); failed(register(r, teacher), 400);
                r = request(); r.put(field, new JSONObject()); failed(register(r, teacher), 400);
            }
            failed(register(null, teacher), 400);
        }
        verifyZeroInteractions(users, profiles, roles, config, tx);
    }
    @Test public void phoneOnlyLegacyRequestRequiresUsernameBeforeAnySideEffect() {
        for (boolean teacher : new boolean[]{false, true}) {
            JSONObject r = request(); r.remove("username"); r.put("phone", "13900000001");
            Result<?> result = register(r, teacher);
            failed(result, 400); assertTrue(result.getMessage().contains("用户名"));
        }
        verifyZeroInteractions(users, profiles, roles, config, tx);
    }
    @Test public void bothEntriesAcceptExistingUsernameCharactersAndTrimSurroundingWhitespace() {
        for (boolean teacher : new boolean[]{false, true}) {
            for (String username : new String[]{"abc", "13900000001", "Learner_01@example.edu-cn",
                    new String(new char[100]).replace('\0', 'a')}) {
                setup(); JSONObject r = request(); r.put("username", " " + username + " ");
                // A phone supplied by stale or forged clients is not contact information.
                r.put("phone", "13900000002");
                assertTrue(register(r, teacher).isSuccess());
                ArgumentCaptor<SysUser> captured = ArgumentCaptor.forClass(SysUser.class);
                verify(users).save(captured.capture());
                SysUser user = captured.getValue();
                assertEquals(username, user.getUsername()); assertNull(user.getPhone());
                assertEquals(PasswordUtil.encrypt(username, "Synthetic8!", user.getSalt()), user.getPassword());
                verify(profiles).countReservedUsername(username);
            }
        }
    }
    @Test public void invalidUsernameBoundariesNeverReadOrWrite() {
        for (boolean teacher : new boolean[]{false, true}) {
            for (String username : new String[]{"", "  ", "ab", new String(new char[101]).replace('\0', 'a'),
                    "姓名账号", "abc def", "abc\nxyz", "abc/xyz", "abc'xyz"}) {
                JSONObject r = request(); r.put("username", username); failed(register(r, teacher), 400);
            }
        }
        verifyZeroInteractions(users, profiles, roles, config, tx);
    }
    @Test public void bothEntriesAcceptBoundedPasswordsWithoutCharacterMixAndPreserveLoginValue() {
        String[] passwords = {"12345678", "abcdefgh", "!!!!!!!!", "abcd1234",
                new String(new char[64]).replace('\0', 'a')};
        for (boolean teacher : new boolean[]{false, true}) {
            for (String password : passwords) {
                setup();
                JSONObject r = request(); r.put("password", password);
                assertTrue(register(r, teacher).isSuccess());
                ArgumentCaptor<SysUser> captured = ArgumentCaptor.forClass(SysUser.class);
                verify(users).save(captured.capture());
                SysUser user = captured.getValue();
                assertNotNull(user.getPassword());
                assertNotEquals(password, user.getPassword());
                assertEquals(PasswordUtil.encrypt(user.getUsername(), password, user.getSalt()), user.getPassword());
                verify(profiles).insertProfile("new-user", teacher ? "teacher" : "student");
                verify(users).addUserWithRole(user, "student-role");
                verify(tx).commit(any());
            }
        }
    }
    @Test public void bothEntriesRejectInvalidPasswordBoundariesBeforeAnySideEffect() {
        String[] passwords = {"", "1234567", new String(new char[65]).replace('\0', 'a'),
                "abc defg", "abcdefgh中文", "abcdefgh\n", "abcdefgh\t", "abcdefgh\u007f"};
        for (boolean teacher : new boolean[]{false, true}) {
            for (String password : passwords) {
                JSONObject r = request(); r.put("password", password);
                failed(register(r, teacher), 400);
            }
        }
        verifyZeroInteractions(users, profiles, roles, config, tx);
    }
    @Test public void publicRegistrationWithoutIdentityCreatesStudentProfile() {
        assertTrue(service.register(request()).isSuccess());
        verify(profiles).insertProfile("new-user", "student");
        verify(users).addUserWithRole(any(SysUser.class), eq("student-role"));
        verify(tx).commit(any());
    }
    @Test public void publicRegistrationIgnoresEverySuppliedIdentity() {
        Object[] identities = {"teacher", "admin", "", null, 2, new JSONObject()};
        for (Object identity : identities) {
            JSONObject r = request(); r.put("identity", identity);
            assertTrue(service.register(r).isSuccess());
        }
        verify(users, times(identities.length)).save(any(SysUser.class));
        verify(profiles, times(identities.length)).insertProfile("new-user", "student");
        verify(users, times(identities.length)).addUserWithRole(any(SysUser.class), eq("student-role"));
        verify(tx, times(identities.length)).commit(any());
        verify(profiles, never()).insertProfile(anyString(), eq("teacher"));
    }
    @Test public void bothEntriesIgnorePrivilegeFieldsAndUseTheirFixedProfile() {
        for (boolean teacher : new boolean[]{false, true}) {
            setup();
            JSONObject r = request(); r.put("identity", teacher ? "student" : "teacher");
            assertFixedAccount(r, teacher);
        }
    }
    private void assertFixedAccount(JSONObject r, boolean teacher) {
        r.put("phone", "13900000001"); r.put("roles", "admin,teacher");
        r.put("userIdentity", 2); r.put("departIds", "secret"); r.put("status", 2); r.put("id", "admin");
        Result<?> result = register(r, teacher); assertTrue(result.isSuccess()); assertNull(result.getResult());
        ArgumentCaptor<SysUser> capture = ArgumentCaptor.forClass(SysUser.class); verify(users).save(capture.capture());
        SysUser u = capture.getValue(); assertEquals("learner_01", u.getUsername()); assertNull(u.getPhone()); assertEquals("张同学", u.getRealname());
        assertEquals("测试学校", u.getSchool()); assertEquals(Integer.valueOf(1), u.getUserIdentity()); assertEquals("", u.getDepartIds());
        assertEquals(Integer.valueOf(1), u.getStatus()); assertNotEquals("Synthetic8!", u.getPassword());
        assertEquals(Integer.valueOf(0), u.getDelFlag());
        verify(users).addUserWithRole(u, "student-role");
        verify(profiles).insertProfile("new-user", teacher ? "teacher" : "student"); verify(tx).commit(any());
    }
    @Test public void teacherRegistrationWithoutIdentityCreatesTeacherProfile() {
        assertTrue(service.registerTeacher(request()).isSuccess());
        verify(profiles).insertProfile("new-user", "teacher");
        verify(users).addUserWithRole(any(SysUser.class), eq("student-role"));
        verify(tx).commit(any());
    }
    @Test public void disabledMissingRoleAndReservedUsernameFailClosed() {
        when(config.getConfigItem("allowReg")).thenReturn("0");
        for (boolean teacher : new boolean[]{false, true}) failed(register(request(), teacher), 403);
        when(config.getConfigItem("allowReg")).thenReturn("1"); when(profiles.countReservedUsername(anyString())).thenReturn(1);
        for (boolean teacher : new boolean[]{false, true}) failed(register(request(), teacher), 409);
        when(profiles.countReservedUsername(anyString())).thenReturn(0); when(roles.getOne(any())).thenReturn(null);
        for (boolean teacher : new boolean[]{false, true}) failed(register(request(), teacher), 503);
        verifyZeroInteractions(users, tx);
    }
    @Test public void concurrentUniqueConstraintFailureRollsBackAndReturnsConflict() {
        for (boolean teacher : new boolean[]{false, true}) {
            setup(); when(users.save(any(SysUser.class))).thenThrow(new DuplicateKeyException("private"));
            failed(register(request(), teacher), 409); verify(tx).rollback(any());
            verify(tx, never()).commit(any()); verify(profiles, never()).insertProfile(anyString(), anyString());
        }
    }
    @Test public void profileOrRoleFailureRollsBackWholeRegistration() {
        for (boolean teacher : new boolean[]{false, true}) {
            setup(); when(profiles.insertProfile(anyString(), anyString())).thenReturn(0);
            failed(register(request(), teacher), 503); verify(tx).rollback(any()); verify(tx, never()).commit(any());
            reset(tx); when(tx.getTransaction(any())).thenReturn(new SimpleTransactionStatus());
            when(profiles.insertProfile(anyString(), anyString())).thenReturn(1);
            doThrow(new IllegalStateException("private")).when(users).addUserWithRole(any(), anyString());
            failed(register(request(), teacher), 503); verify(tx).rollback(any()); verify(tx, never()).commit(any());
        }
    }
}
