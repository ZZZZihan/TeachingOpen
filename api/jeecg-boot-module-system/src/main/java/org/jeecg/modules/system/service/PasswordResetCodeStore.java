package org.jeecg.modules.system.service;

import org.jeecg.common.constant.CacheConstant;
import org.jeecg.common.constant.CommonConstant;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

import java.util.Arrays;
import java.util.Collections;
import java.util.concurrent.TimeUnit;

/** Text-only storage for password recovery; never shares login/registration keys. */
@Component
public class PasswordResetCodeStore {
    public static final long CODE_TTL_SECONDS = 600;
    private static final DefaultRedisScript<Long> COMPARE_DELETE = new DefaultRedisScript<>(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0", Long.class);
    private static final DefaultRedisScript<Long> PUBLISH = new DefaultRedisScript<>(
            "if redis.call('get', KEYS[1]) == ARGV[1] then redis.call('set', KEYS[1], ARGV[2], 'EX', ARGV[3]); return 1 end return 0", Long.class);
    private final StringRedisTemplate redis;

    public PasswordResetCodeStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public static String key(String userId, String phone) {
        return "sys:password-reset:code:" + userId + ":" + phone;
    }

    public boolean reserve(String userId, String phone, String reservation) {
        // A short reservation prevents concurrent sends from delivering different
        // codes. Only publish() makes it a usable six-digit recovery code.
        return Boolean.TRUE.equals(redis.opsForValue().setIfAbsent(key(userId, phone), reservation, 30, TimeUnit.SECONDS));
    }

    public boolean publish(String userId, String phone, String reservation, String code) {
        return Long.valueOf(1).equals(redis.execute(PUBLISH, Collections.singletonList(key(userId, phone)),
                reservation, code, String.valueOf(CODE_TTL_SECONDS)));
    }

    public boolean matches(String userId, String phone, String code) {
        return code.equals(redis.opsForValue().get(key(userId, phone)));
    }

    public boolean consume(String userId, String phone, String expected) {
        return Long.valueOf(1).equals(redis.execute(COMPARE_DELETE, Collections.singletonList(key(userId, phone)), expected));
    }

    public void clearUserCaches(String userId, String username) {
        // These existing caches also use String keys; deleting by key does not
        // depend on their different JSON value serializers.
        redis.delete(Arrays.asList(CommonConstant.PREFIX_USER_TOKEN + username,
                CommonConstant.PREFIX_USER_SHIRO_CACHE + userId, CacheConstant.SYS_USERS_CACHE + "::" + username));
    }
}
