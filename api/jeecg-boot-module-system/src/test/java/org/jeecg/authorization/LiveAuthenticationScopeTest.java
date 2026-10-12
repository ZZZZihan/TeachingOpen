package org.jeecg.authorization;

import org.jeecg.common.constant.CommonConstant;
import org.jeecg.common.system.api.ISysBaseAPI;
import org.jeecg.common.system.util.JwtUtil;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.RedisUtil;
import org.jeecg.modules.shiro.authc.ShiroRealm;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.service.ISysUserService;
import org.junit.Test;
import org.springframework.beans.BeanUtils;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.util.ReflectionUtils;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.Assert.*;
import static org.mockito.Mockito.*;

public class LiveAuthenticationScopeTest {
    @Test public void lateCacheFillCannotRestoreRevokedClassWithTheSameToken() throws Exception {
        ShiroRealm realm = new ShiroRealm();
        ISysUserService users = mock(ISysUserService.class);
        RedisUtil redis = mock(RedisUtil.class);
        ISysBaseAPI profileApi = mock(ISysBaseAPI.class);
        ReflectionTestUtils.setField(realm, "sysUserService", users);
        ReflectionTestUtils.setField(realm, "redisUtil", redis);
        // Supports running this exact regression against the pre-fix realm.
        if (ReflectionUtils.findField(ShiroRealm.class, "sysBaseAPI") != null) {
            ReflectionTestUtils.setField(realm, "sysBaseAPI", profileApi);
        }
        SysUser old = new SysUser().setId("teacher").setUsername("teacher")
                .setPassword("synthetic-scope-secret").setStatus(1).setDelFlag(0)
                .setDepartIds("class-a").setOrgCode("A01").setRealname("Teacher");
        SysUser revoked = new SysUser(); BeanUtils.copyProperties(old, revoked);
        revoked.setDepartIds("").setOrgCode("A02").setRealname("Updated Teacher");
        AtomicReference<SysUser> committed = new AtomicReference<>(old);
        LoginUser oldProfile = new LoginUser(); BeanUtils.copyProperties(old, oldProfile);
        AtomicReference<LoginUser> cache = new AtomicReference<>(oldProfile);
        when(users.getUserByName("teacher")).thenAnswer(call -> committed.get());
        when(profileApi.getUserByName("teacher")).thenAnswer(call -> cache.get());
        String token = JwtUtil.sign("teacher", old.getPassword());
        when(redis.get(CommonConstant.PREFIX_USER_TOKEN + token)).thenReturn(token);
        assertEquals("class-a", realm.checkUserTokenIsEffect(token).getDepartIds());

        CountDownLatch readOld = new CountDownLatch(1), allowFill = new CountDownLatch(1);
        Thread inFlightCacheMiss = new Thread(() -> {
            LoginUser snapshot = new LoginUser(); BeanUtils.copyProperties(committed.get(), snapshot);
            readOld.countDown();
            try {
                if (!allowFill.await(5, TimeUnit.SECONDS)) throw new AssertionError("barrier timeout");
                cache.set(snapshot);
            } catch (InterruptedException ex) { Thread.currentThread().interrupt(); }
        });
        inFlightCacheMiss.start();
        try {
            assertTrue(readOld.await(5, TimeUnit.SECONDS));
            committed.set(revoked);  // committed revocation precedes new authentication
            cache.set(null);       // successful eviction does not prevent a delayed put
        } finally { allowFill.countDown(); }
        inFlightCacheMiss.join(5000);
        assertFalse(inFlightCacheMiss.isAlive());
        assertEquals("class-a", cache.get().getDepartIds());
        LoginUser principal = realm.checkUserTokenIsEffect(token);
        assertEquals("", principal.getDepartIds());
        assertEquals("A02", principal.getOrgCode());
        assertEquals("Updated Teacher", principal.getRealname());
        assertEquals("teacher", principal.getId());
        assertEquals(old.getPassword(), principal.getPassword());
        assertEquals(Integer.valueOf(1), principal.getStatus());
        assertNotSame(cache.get(), principal);
    }
}
