package org.jeecg.authorization;

import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;
import org.apache.shiro.subject.Subject;
import org.apache.shiro.util.ThreadContext;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.constant.CommonConstant;
import org.jeecg.common.system.api.ISysBaseAPI;
import org.jeecg.common.system.util.JwtUtil;
import org.jeecg.common.util.RedisUtil;
import org.jeecg.modules.shiro.authc.aop.MediaCookie;
import org.jeecg.modules.system.controller.LoginController;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.service.ISysUserService;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Date;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

import static org.junit.Assert.*;
import static org.mockito.Mockito.*;

public class LogoutSessionIsolationTest {
    private final LoginController controller = new LoginController();
    private final ISysUserService users = mock(ISysUserService.class);
    private final ISysBaseAPI profile = mock(ISysBaseAPI.class);
    private final MediaCookie cookie = mock(MediaCookie.class);
    private final Subject subject = mock(Subject.class);
    private final MemoryRedis redis = new MemoryRedis();
    private final String index = CommonConstant.PREFIX_USER_TOKEN + "student";

    @Before public void setup() {
        ReflectionTestUtils.setField(controller, "sysUserService", users);
        ReflectionTestUtils.setField(controller, "sysBaseAPI", profile);
        ReflectionTestUtils.setField(controller, "mediaCookie", cookie);
        ReflectionTestUtils.setField(controller, "redisUtil", redis);
        when(users.getUserByName("student")).thenReturn(new SysUser().setId("student-id")
                .setUsername("student").setRealname("Synthetic student").setPassword("current-secret"));
        ThreadContext.bind(subject);
    }
    @After public void cleanup() { ThreadContext.remove(); }

    private Result<?> logout(String token) {
        MockHttpServletRequest request = new MockHttpServletRequest();
        if (token != null) request.addHeader("X-Access-Token", token);
        return controller.logout(request, new MockHttpServletResponse());
    }
    private void session(String token) {
        redis.values.put(index, token);
        redis.values.put(CommonConstant.PREFIX_USER_TOKEN + token, token);
    }

    @Test public void forgedUsernameCannotMutateVictimSessionOrWriteSuccessAudit() {
        String victim = JwtUtil.sign("student", "current-secret");
        session(victim);
        Map<String, Object> before = new HashMap<>(redis.values);
        assertFalse(logout(JwtUtil.sign("student", "wrong-secret")).isSuccess());
        assertEquals(before, redis.values);
        verifyZeroInteractions(profile, subject);
    }

    @Test public void invalidAlgorithmMalformedMissingAndUnknownCredentialsHaveNoServerSideEffects() {
        String victim = JwtUtil.sign("student", "current-secret"); session(victim);
        Map<String, Object> before = new HashMap<>(redis.values);
        String[] rejected = {null, "not-a-jwt", JWT.create().withClaim("username", "student")
                .sign(Algorithm.HMAC512("current-secret")), JwtUtil.sign("missing-user", "any-secret")};
        for (String token : rejected) {
            assertFalse(logout(token).isSuccess());
            assertEquals(before, redis.values);
        }
        verifyZeroInteractions(profile, subject);
    }

    @Test public void currentLogoutRevokesOnlyItsSessionAndCanBeRetried() {
        String token = JwtUtil.sign("student", "current-secret"); session(token);
        redis.values.put(CommonConstant.PREFIX_USER_TOKEN + "other", "other-session");
        redis.values.put(CommonConstant.PREFIX_USER_TOKEN + "other-session", "other-session");
        assertTrue(logout(token).isSuccess());
        assertFalse(redis.values.containsKey(index));
        assertFalse(redis.values.containsKey(CommonConstant.PREFIX_USER_TOKEN + token));
        assertEquals("other-session", redis.values.get(CommonConstant.PREFIX_USER_TOKEN + "other"));
        assertEquals("other-session", redis.values.get(CommonConstant.PREFIX_USER_TOKEN + "other-session"));
        Map<String, Object> after = new HashMap<>(redis.values);
        assertTrue(logout(token).isSuccess());
        assertEquals(after, redis.values);
    }

    @Test public void delayedOlderLogoutPreservesTheNewLoginIndex() {
        String old = JWT.create().withClaim("username", "student").withClaim("nonce", "old")
                .sign(Algorithm.HMAC256("current-secret"));
        String current = JwtUtil.sign("student", "current-secret"); session(current);
        redis.values.put(CommonConstant.PREFIX_USER_TOKEN + old, old);
        assertTrue(logout(old).isSuccess());
        assertEquals(current, redis.values.get(index));
        assertEquals(current, redis.values.get(CommonConstant.PREFIX_USER_TOKEN + current));
        assertFalse(redis.values.containsKey(CommonConstant.PREFIX_USER_TOKEN + old));
        assertTrue(logout(old).isSuccess());
        assertEquals(current, redis.values.get(index));
    }

    @Test public void expiredSignedCredentialCanStillRevokeItsOwnCachedSession() {
        String expired = JWT.create().withClaim("username", "student")
                .withExpiresAt(new Date(System.currentTimeMillis() - 60000))
                .sign(Algorithm.HMAC256("current-secret"));
        session(expired);
        assertFalse(JwtUtil.verify(expired, "student", "current-secret"));
        assertTrue(logout(expired).isSuccess());
        assertFalse(redis.values.containsKey(index));
        assertFalse(redis.values.containsKey(CommonConstant.PREFIX_USER_TOKEN + expired));
    }

    @Test public void credentialFromBeforePasswordChangeCannotDeleteNewLoginIndex() {
        String current = JwtUtil.sign("student", "current-secret"); session(current);
        Map<String, Object> before = new HashMap<>(redis.values);
        assertFalse(logout(JwtUtil.sign("student", "previous-secret")).isSuccess());
        assertEquals(before, redis.values);
        verifyZeroInteractions(profile, subject);
    }

    private static class MemoryRedis extends RedisUtil {
        final Map<String, Object> values = new HashMap<>();
        @Override public void del(String... keys) { for (String key : keys) values.remove(key); }
        @Override public boolean deleteIfEquals(String key, Object value) {
            if (!Objects.equals(values.get(key), value)) return false;
            values.remove(key); return true;
        }
    }
}
