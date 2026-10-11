package org.jeecg.modules.teaching.service;

import org.jeecg.common.exception.JeecgBootException;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

/** Read-only bridge: an old marker is ambiguous because it preceded the SQL write. */
@Service
public class LegacyUnitViewMarkerStore {
    private final RedisTemplate<String, Object> redis;

    public LegacyUnitViewMarkerStore(RedisTemplate<String, Object> redis) {
        this.redis = redis;
    }

    public boolean contains(String departId, String unitId) {
        // RedisUtil.sHasKey swallows failures as false, which could recount old successes.
        Boolean present = redis.opsForSet().isMember("departLog:unitView:" + departId, unitId);
        if (present == null) throw new JeecgBootException("无法核对历史单元浏览记录，请稍后重试");
        return present;
    }
}
