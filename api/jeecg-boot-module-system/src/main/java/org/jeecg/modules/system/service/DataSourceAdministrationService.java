package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import java.util.*;
import lombok.extern.slf4j.Slf4j;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.modules.system.entity.SysDataSource;
import org.jeecg.modules.system.mapper.SysDataSourceMapper;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationAdapter;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/** Explicit administration commands; generic IService imports cannot bypass this boundary. */
@Slf4j
@Service
public class DataSourceAdministrationService {
    private final InfrastructureAccessService access;
    private final SysDataSourceMapper sources;
    private final DataSourceCacheInvalidator cache;

    public DataSourceAdministrationService(InfrastructureAccessService access, SysDataSourceMapper sources,
            DataSourceCacheInvalidator cache) {
        this.access = access; this.sources = sources; this.cache = cache;
    }

    public IPage<SysDataSource> page(Page<SysDataSource> page, Wrapper<SysDataSource> query) {
        access.requireOperator();
        return sources.selectPage(page, query);
    }

    public List<SysDataSource> list(Wrapper<SysDataSource> query) {
        access.requireOperator();
        return sources.selectList(query);
    }

    public SysDataSource get(String id) {
        access.requireOperator();
        return sources.selectById(id);
    }

    @Transactional(rollbackFor = Exception.class)
    public void add(SysDataSource command) {
        access.requireOperator();
        SysDataSource value = fields(command);
        validate(value);
        if (sources.insert(value) != 1) throw new JeecgBootException("数据源保存失败");
    }

    @Transactional(rollbackFor = Exception.class)
    public void edit(SysDataSource command) {
        access.requireOperator();
        if (command == null || command.getId() == null) throw new JeecgBootException("数据源不存在");
        SysDataSource current = required(command.getId());
        if (command.getCode() != null && !current.getCode().equals(command.getCode())) {
            throw new JeecgBootException("数据源编码不可更改");
        }
        SysDataSource value = fields(command).setId(current.getId()).setCode(current.getCode());
        // An omitted/blank edit password preserves the credential; it is never sent back to the form.
        if (value.getDbPassword() == null || value.getDbPassword().isEmpty()) value.setDbPassword(current.getDbPassword());
        validate(value);
        if (sources.updateById(value) != 1) throw new JeecgBootException("数据源更新失败");
        invalidateAfterCommit(Collections.singletonList(current));
    }

    @Transactional(rollbackFor = Exception.class)
    public void delete(Collection<String> requested) {
        access.requireOperator();
        List<String> ids = AccountAdministrationService.ids(requested);
        List<SysDataSource> current = new ArrayList<>();
        for (String id : ids) current.add(required(id));
        if (sources.deleteBatchIds(ids) != ids.size()) throw new JeecgBootException("数据源删除失败");
        invalidateAfterCommit(current);
    }

    @Transactional(rollbackFor = Exception.class)
    public void importSources(List<SysDataSource> commands) {
        access.requireOperator();
        if (commands == null || commands.isEmpty() || commands.size() > 100) {
            throw new JeecgBootException("每次导入1至100个数据源");
        }
        List<SysDataSource> values = new ArrayList<>();
        Set<String> codes = new HashSet<>();
        for (SysDataSource command : commands) {
            SysDataSource value = fields(command);
            validate(value);
            if (!codes.add(value.getCode())) throw new JeecgBootException("数据源编码重复");
            values.add(value);
        }
        for (SysDataSource value : values) {
            if (sources.insert(value) != 1) throw new JeecgBootException("数据源导入失败");
        }
    }

    private SysDataSource required(String id) {
        SysDataSource value = sources.selectById(id);
        if (value == null || !id.equals(value.getId())) throw new JeecgBootException("数据源不存在");
        return value;
    }

    private static SysDataSource fields(SysDataSource value) {
        if (value == null) throw new JeecgBootException("数据源不能为空");
        return new SysDataSource().setCode(value.getCode()).setName(value.getName()).setRemark(value.getRemark())
                .setDbType(value.getDbType()).setDbDriver(value.getDbDriver()).setDbUrl(value.getDbUrl())
                .setDbName(value.getDbName()).setDbUsername(value.getDbUsername()).setDbPassword(value.getDbPassword());
    }

    private static void validate(SysDataSource value) {
        if (value.getCode() == null || !value.getCode().matches("[A-Za-z][A-Za-z0-9_-]{0,63}")
                || empty(value.getName()) || empty(value.getDbDriver()) || empty(value.getDbUrl())
                || empty(value.getDbType()) || empty(value.getDbName()) || empty(value.getDbUsername())
                || empty(value.getDbPassword())) throw new JeecgBootException("数据源资料不完整");
    }

    private static boolean empty(String value) { return value == null || value.trim().isEmpty(); }

    private void invalidateAfterCommit(List<SysDataSource> values) {
        Runnable invalidate = () -> values.forEach(value -> {
            try { cache.invalidate(value.getCode()); }
            catch (RuntimeException failure) {
                // A committed administration write must not be reported as rolled back.
                log.error("数据源已更新，但缓存失效失败: {}", value.getCode(), failure);
            }
        });
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronizationAdapter() {
                @Override public void afterCommit() { invalidate.run(); }
            });
        } else invalidate.run();
    }
}
