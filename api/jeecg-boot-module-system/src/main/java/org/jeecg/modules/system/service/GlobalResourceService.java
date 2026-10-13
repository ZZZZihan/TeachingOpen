package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.modules.system.entity.SysUser;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;
import java.io.Serializable;
import java.util.*;

/** Mutation boundary shared only by the global category/fill/check configuration tables. */
public abstract class GlobalResourceService<M extends BaseMapper<T>, T> extends ServiceImpl<M, T> {
    @Autowired protected GlobalResourceAccessService access;
    protected abstract T writable(T input, boolean editing, SysUser actor);
    protected abstract String entityId(T value);
    protected void insertPrepared(T value) { if (baseMapper.insert(value) != 1) throw invalid(); }
    protected void updatePrepared(T value) { if (baseMapper.updateById(value) != 1) throw invalid(); }

    @Override @Transactional(rollbackFor = Exception.class)
    public boolean save(T input) {
        T value = writable(input, false, access.requireAdministrator());
        insertPrepared(value); return true;
    }
    @Override @Transactional(rollbackFor = Exception.class)
    public boolean saveBatch(Collection<T> values) { return saveBatch(values, 200); }
    @Override @Transactional(rollbackFor = Exception.class)
    public boolean saveBatch(Collection<T> values, int batchSize) {
        SysUser actor = access.requireAdministrator();
        if (values == null || values.isEmpty() || values.size() > 200) throw invalid();
        List<T> checked = new ArrayList<>();
        for (T value : values) checked.add(writable(value, false, actor));
        for (T value : checked) insertPrepared(value);
        return true;
    }
    @Override @Transactional(rollbackFor = Exception.class)
    public boolean updateById(T input) {
        T value = writable(input, true, access.requireAdministrator());
        if (baseMapper.selectById(entityId(value)) == null) throw invalid();
        updatePrepared(value); return true;
    }
    @Override @Transactional(rollbackFor = Exception.class)
    public boolean removeById(Serializable id) { return removeByIds(Collections.singletonList(id)); }
    @Override @Transactional(rollbackFor = Exception.class)
    public boolean removeByIds(Collection<? extends Serializable> ids) {
        access.requireAdministrator();
        if (ids == null || ids.isEmpty() || ids.size() > 200) throw invalid();
        List<String> checked = new ArrayList<>();
        for (Serializable id : ids) checked.add(checkedId(id));
        baseMapper.deleteBatchIds(checked); return true;
    }
    private boolean unsupported() { access.requireAdministrator(); throw invalid(); }
    @Override public boolean update(T value, Wrapper<T> wrapper) { return unsupported(); }
    @Override public boolean updateBatchById(Collection<T> values, int batchSize) { return unsupported(); }
    @Override public boolean saveOrUpdate(T value) { return unsupported(); }
    @Override public boolean saveOrUpdateBatch(Collection<T> values, int batchSize) { return unsupported(); }
    @Override public boolean remove(Wrapper<T> wrapper) { return unsupported(); }
    @Override public boolean removeByMap(Map<String, Object> columns) { return unsupported(); }

    protected static String checkedId(Object value) {
        if (!(value instanceof String) || !((String)value).matches("[A-Za-z0-9_-]{1,64}")) throw invalid();
        return (String)value;
    }
    protected static String code(String value) {
        if (value == null || !value.matches("[A-Za-z0-9_-]{1,100}")) throw invalid(); return value;
    }
    protected static String text(String value, int max, boolean required) {
        if (value == null || value.trim().isEmpty()) { if (required) throw invalid(); return value; }
        if (value.length() > max) throw invalid(); return value;
    }
    protected static JeecgBootException invalid() { return new JeecgBootException("全局资源参数无效或保存失败"); }
}
