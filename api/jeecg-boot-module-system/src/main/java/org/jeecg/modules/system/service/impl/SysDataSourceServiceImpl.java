package org.jeecg.modules.system.service.impl;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import org.jeecg.modules.system.entity.SysDataSource;
import org.jeecg.modules.system.mapper.SysDataSourceMapper;
import org.jeecg.modules.system.service.ISysDataSourceService;
import org.springframework.stereotype.Service;

/** This internal read contract deliberately exposes no generic write/import API. */
@Service
public class SysDataSourceServiceImpl implements ISysDataSourceService {
    private final SysDataSourceMapper sources;
    public SysDataSourceServiceImpl(SysDataSourceMapper sources) { this.sources = sources; }
    @Override public SysDataSource getById(String id) { return sources.selectById(id); }
    @Override public SysDataSource getOne(Wrapper<SysDataSource> query) { return sources.selectOne(query); }
}
