package org.jeecg.accountrecovery;

import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;
import org.apache.shiro.authc.AuthenticationException;
import org.jeecg.common.constant.CommonConstant;
import org.jeecg.common.system.api.ISysBaseAPI;
import org.jeecg.common.system.util.JwtUtil;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.RedisUtil;
import org.jeecg.modules.shiro.authc.ShiroRealm;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.service.ISysUserService;
import org.junit.Before;
import org.junit.Test;
import org.springframework.test.util.ReflectionTestUtils;
import java.util.Date;
import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class AccountRecoverySessionTest {
    private ShiroRealm realm;
    private RedisUtil redis;
    private ISysUserService users;
    @Before public void setup() {
        realm = new ShiroRealm(); redis = mock(RedisUtil.class); users = mock(ISysUserService.class);
        ISysBaseAPI api = mock(ISysBaseAPI.class);
        ReflectionTestUtils.setField(realm, "redisUtil", redis); ReflectionTestUtils.setField(realm, "sysUserService", users);
        ReflectionTestUtils.setField(realm, "sysBaseAPI", api);
        when(users.getUserByName("synthetic")).thenReturn(new SysUser().setUsername("synthetic").setStatus(1).setPassword("new-secret"));
        LoginUser cached = new LoginUser(); cached.setUsername("synthetic"); cached.setPassword("stale-secret");
        when(api.getUserByName("synthetic")).thenReturn(cached);
    }
    @Test public void signatureChecksClaimAndAlgorithm() {
        String token = JwtUtil.sign("synthetic", "new-secret"); assertTrue(JwtUtil.verifySignature(token, "synthetic", "new-secret"));
        assertFalse(JwtUtil.verifySignature(token, "other", "new-secret"));
        assertFalse(JwtUtil.verifySignature(token, "synthetic", "old-secret"));
        assertFalse(JwtUtil.verifySignature(JWT.create().withClaim("username", "synthetic").sign(Algorithm.HMAC512("new-secret")), "synthetic", "new-secret"));
        assertFalse(JwtUtil.verifySignature("not-a-jwt", "synthetic", "new-secret"));
    }
    @Test(expected = AuthenticationException.class) public void oldPasswordSessionCannotBeResignedEvenIfCached() {
        String token = JwtUtil.sign("synthetic", "old-secret"); when(redis.get(CommonConstant.PREFIX_USER_TOKEN + token)).thenReturn(token);
        try { realm.checkUserTokenIsEffect(token); } finally { verify(redis, never()).set(anyString(), any()); }
    }
    @Test public void liveDbPasswordOverridesStaleUserCache() {
        String token = JwtUtil.sign("synthetic", "new-secret"); when(redis.get(CommonConstant.PREFIX_USER_TOKEN + token)).thenReturn(token);
        assertNotNull(realm.checkUserTokenIsEffect(token)); verify(redis, never()).set(anyString(), any());
    }
    @Test(expected = AuthenticationException.class) public void validSignatureDoesNotRestoreMissingRedisSession() {
        realm.checkUserTokenIsEffect(JwtUtil.sign("synthetic", "new-secret"));
    }
    @Test public void expiredValidOriginalSignatureRetainsRedisRefresh() {
        String token = JWT.create().withClaim("username", "synthetic").withExpiresAt(new Date(System.currentTimeMillis()-10000)).sign(Algorithm.HMAC256("new-secret"));
        assertFalse(JwtUtil.verify(token, "synthetic", "new-secret")); assertTrue(JwtUtil.verifySignature(token, "synthetic", "new-secret"));
        when(redis.get(CommonConstant.PREFIX_USER_TOKEN + token)).thenReturn(token); assertNotNull(realm.checkUserTokenIsEffect(token));
        verify(redis).set(eq(CommonConstant.PREFIX_USER_TOKEN + token), argThat(value -> JwtUtil.verify(String.valueOf(value), "synthetic", "new-secret")));
    }
    @Test(expected = AuthenticationException.class) public void frozenAccountStillRejectsValidSignature() {
        when(users.getUserByName("synthetic")).thenReturn(new SysUser().setUsername("synthetic").setStatus(2).setPassword("new-secret"));
        realm.checkUserTokenIsEffect(JwtUtil.sign("synthetic", "new-secret"));
    }
}
