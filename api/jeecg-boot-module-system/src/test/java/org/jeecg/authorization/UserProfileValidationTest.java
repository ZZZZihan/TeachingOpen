package org.jeecg.authorization;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.model.UserProfileRequest;
import org.jeecg.modules.system.service.UserProfileService;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.mockito.ArgumentCaptor;

import java.util.Arrays;
import java.util.Map;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class UserProfileValidationTest {
    private SysUserMapper users;
    private UserProfileService service;

    @Before public void setup() {
        TableInfoHelper.initTableInfo(new MapperBuilderAssistant(new MybatisConfiguration(), "profile-validation-test"), SysUser.class);
        users = mock(SysUserMapper.class);
        service = new UserProfileService(users);
        LoginUser principal = new LoginUser(); principal.setId("self"); principal.setUsername("student");
        Subject subject = mock(Subject.class); when(subject.getPrincipal()).thenReturn(principal);
        ThreadContext.bind(subject);
        when(users.update(isNull(), any())).thenReturn(1);
    }

    @After public void cleanup() { ThreadContext.unbindSubject(); }

    private UserProfileRequest request(String email) {
        UserProfileRequest request = new UserProfileRequest();
        request.setId("self"); request.setRealname("  合法名称  "); request.setEmail(email);
        return request;
    }

    @Test public void invalidEmailIsRejectedBeforeAnyDatabaseOperation() {
        for (String email : Arrays.asList("abc", "user@", "@example.test", "user@example", "user@@example.test",
                "user name@example.test", " user@example.test", "user@example.test ", "user@example.test\n",
                "user\u00a0name@example.test", "u\uFEFFser@example.test", "u\u0085ser@example.test", "\"u\u0001ser\"@example.test", String.join("", java.util.Collections.nCopies(101, "a")) + "@example.test")) {
            try { service.update(request(email)); fail("Invalid email must be rejected: " + email); }
            catch (JeecgBootException expected) { assertEquals("个人资料格式不正确", expected.getMessage()); }
        }
        verifyZeroInteractions(users);
    }

    @Test public void validEmailKeepsTheExistingProfileValidatorContract() {
        for (String email : Arrays.asList("candidate@example.test", "first.last+tag@sub.example.com", "\"quoted.name\"@example.test", "name@[127.0.0.1]")) {
            service.update(request(email));
            ArgumentCaptor<LambdaUpdateWrapper> patch = ArgumentCaptor.forClass(LambdaUpdateWrapper.class);
            verify(users).update(isNull(), patch.capture());
            Map<String, Object> parameters = patch.getValue().getParamNameValuePairs();
            assertTrue(parameters.containsValue(email)); assertTrue(parameters.containsValue("合法名称"));
            assertTrue(patch.getValue().getSqlSegment().contains("id ="));
            assertTrue(patch.getValue().getParamNameValuePairs().containsValue("self"));
            clearInvocations(users);
        }
    }

    @Test public void absentOrEmptyEmailRemainsOptional() {
        for (String email : new String[]{null, ""}) {
            service.update(request(email));
            ArgumentCaptor<LambdaUpdateWrapper> patch = ArgumentCaptor.forClass(LambdaUpdateWrapper.class);
            verify(users).update(isNull(), patch.capture());
            assertTrue(patch.getValue().getSqlSet().contains("email="));
            assertTrue(patch.getValue().getParamNameValuePairs().containsValue(email));
            clearInvocations(users);
        }
    }

    @Test public void failedDatabaseUpdateDoesNotReportSaved() {
        when(users.update(isNull(), any())).thenReturn(0);
        try { service.update(request("candidate@example.test")); fail("A missing row must not report success"); }
        catch (JeecgBootException expected) { assertEquals("个人资料未保存", expected.getMessage()); }
        verify(users).update(isNull(), any());
    }
}
