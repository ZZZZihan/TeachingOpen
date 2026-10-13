package org.jeecg.modules.system.service;

import org.jeecg.common.util.dynamic.db.DataSourceCachePool;
import org.springframework.stereotype.Component;

@Component
public class DataSourceCacheInvalidator {
    public void invalidate(String code) {
        DataSourceCachePool.removeCache(code);
    }
}
