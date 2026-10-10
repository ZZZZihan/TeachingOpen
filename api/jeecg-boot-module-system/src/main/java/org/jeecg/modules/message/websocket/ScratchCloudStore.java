package org.jeecg.modules.message.websocket;

import org.jeecg.common.constant.CacheConstant;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.connection.ReturnType;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.nio.charset.StandardCharsets;
import java.util.Map;

/** Preserve existing keys/JSON values; schema changes and bounded upserts are atomic. */
@Service
public class ScratchCloudStore {
    static final int MAX_VARIABLES = 64;
    @Autowired private RedisTemplate<String, Object> redisTemplate;
    private static final byte[] MUTATE = ("local exists=redis.call('HEXISTS',KEYS[1],ARGV[1]); "
            + "local op=ARGV[4]; if op=='delete' then redis.call('HDEL',KEYS[1],ARGV[1]); return 1; end; "
            + "if op=='rename' then if exists==0 then return 0; end; "
            + "if ARGV[1]==ARGV[3] then return 2; end; "
            + "if redis.call('HEXISTS',KEYS[1],ARGV[3])==1 then return 0; end; "
            + "local value=redis.call('HGET',KEYS[1],ARGV[1]); redis.call('HSET',KEYS[1],ARGV[3],value); "
            + "redis.call('HDEL',KEYS[1],ARGV[1]); return 1; end; "
            + "if op=='create' and exists==1 then return 2; end; "
            + "if exists==0 and (ARGV[5]~='1' or redis.call('HLEN',KEYS[1])>=64) then return 0; end; "
            + "redis.call('HSET',KEYS[1],ARGV[1],ARGV[2]); return 1;").getBytes(StandardCharsets.UTF_8);

    public Map<Object, Object> snapshot(String projectId) {
        String key = CacheConstant.SCRATCH_CLOUD + projectId;
        if (redisTemplate.opsForHash().size(key) > MAX_VARIABLES) throw new IllegalStateException("Cloud data limit exceeded");
        return redisTemplate.opsForHash().entries(key);
    }

    @SuppressWarnings("unchecked")
    public long mutate(String projectId, String method, String name, String value, String newName, boolean owner) {
        // Fields use the string serializer; preserve the configured JSON values.
        byte[] encoded = ((org.springframework.data.redis.serializer.RedisSerializer<Object>) redisTemplate.getHashValueSerializer()).serialize(value);
        Long result = redisTemplate.execute((RedisCallback<Long>) connection -> connection.eval(MUTATE,
                ReturnType.INTEGER, 1, bytes(CacheConstant.SCRATCH_CLOUD + projectId), bytes(name),
                encoded == null ? bytes("") : encoded, bytes(newName == null ? "" : newName), bytes(method), bytes(owner ? "1" : "0")));
        if (result == null) throw new IllegalStateException("Cloud data unavailable");
        return result;
    }

    private static byte[] bytes(String value) { return value.getBytes(StandardCharsets.UTF_8); }
}
