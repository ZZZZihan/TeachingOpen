package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import org.jeecg.modules.system.entity.SysDataSource;

/** Internal connection lookup only. Administration uses DataSourceAdministrationService. */
public interface ISysDataSourceService {
    SysDataSource getById(String id);
    SysDataSource getOne(Wrapper<SysDataSource> query);
}
