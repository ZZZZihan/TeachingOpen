package org.jeecg.modules.teaching.service.impl;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.service.GlobalResourceAccessService;
import org.jeecg.modules.teaching.entity.TeachingScratchAssets;
import org.jeecg.modules.teaching.mapper.TeachingScratchAssetsMapper;
import org.jeecg.modules.teaching.service.ITeachingScratchAssetsService;
import org.jeecg.modules.teaching.service.ScratchAssetValidator;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.io.Serializable;
import java.util.*;

/** Every shared-library mutation, including generic Excel batch calls, crosses this boundary. */
@Service
public class TeachingScratchAssetsServiceImpl extends ServiceImpl<TeachingScratchAssetsMapper, TeachingScratchAssets>
        implements ITeachingScratchAssetsService {
    @Autowired private GlobalResourceAccessService access;

    @Override @Transactional(rollbackFor = Exception.class)
    public boolean save(TeachingScratchAssets input) {
        SysUser actor = access.requireAdministrator();
        return insert(ScratchAssetValidator.writable(input), actor);
    }

    @Override @Transactional(rollbackFor = Exception.class)
    public boolean saveBatch(Collection<TeachingScratchAssets> inputs) { return saveBatch(inputs, 200); }

    @Override @Transactional(rollbackFor = Exception.class)
    public boolean saveBatch(Collection<TeachingScratchAssets> inputs, int batchSize) {
        SysUser actor = access.requireAdministrator();
        if (inputs == null || inputs.isEmpty() || inputs.size() > 200) throw invalid();
        List<TeachingScratchAssets> values = new ArrayList<>();
        // Validate all rows before the first write; transaction also covers database failures.
        for (TeachingScratchAssets input : inputs) values.add(ScratchAssetValidator.writable(input));
        for (TeachingScratchAssets value : values) insert(value, actor);
        return true;
    }

    private boolean insert(TeachingScratchAssets value, SysUser actor) {
        value.setId(UUID.randomUUID().toString().replace("-", "")).setDelFlag(0)
                .setCreateBy(actor.getUsername()).setCreateTime(new Date());
        if (baseMapper.insert(value) != 1) throw invalid();
        return true;
    }

    @Override @Transactional(rollbackFor = Exception.class)
    public boolean updateById(TeachingScratchAssets input) {
        SysUser actor = access.requireAdministrator();
        TeachingScratchAssets value = ScratchAssetValidator.writable(input);
        value.setId(ScratchAssetValidator.id(input.getId()));
        TeachingScratchAssets existing = baseMapper.selectById(value.getId());
        if (existing == null) throw invalid();
        value.setUpdateBy(actor.getUsername()).setUdpateTime(new Date());
        if (baseMapper.updateById(value) != 1) throw invalid();
        return true;
    }

    @Override @Transactional(rollbackFor = Exception.class)
    public boolean removeById(Serializable id) {
        return removeByIds(Collections.singletonList(id));
    }

    @Override @Transactional(rollbackFor = Exception.class)
    public boolean removeByIds(Collection<? extends Serializable> ids) {
        access.requireAdministrator();
        if (ids == null || ids.isEmpty() || ids.size() > 200) throw invalid();
        List<String> checked = new ArrayList<>();
        for (Serializable id : ids) checked.add(ScratchAssetValidator.id(id));
        baseMapper.deleteBatchIds(checked);
        // Index removal is not object garbage collection. Assets may remain in saved projects;
        // file management performs reference checks separately before reclaiming bytes.
        return true;
    }

    // No request consumer needs wrapper updates/upserts. Keep them from bypassing schema checks.
    private boolean unsupported() { access.requireAdministrator(); throw invalid(); }
    @Override public boolean update(TeachingScratchAssets value, Wrapper<TeachingScratchAssets> wrapper) { return unsupported(); }
    @Override public boolean updateBatchById(Collection<TeachingScratchAssets> values, int batchSize) { return unsupported(); }
    @Override public boolean saveOrUpdate(TeachingScratchAssets value) { return unsupported(); }
    @Override public boolean saveOrUpdateBatch(Collection<TeachingScratchAssets> values, int batchSize) { return unsupported(); }
    @Override public boolean remove(Wrapper<TeachingScratchAssets> wrapper) { return unsupported(); }
    @Override public boolean removeByMap(Map<String, Object> columns) { return unsupported(); }
    private JeecgBootException invalid() { return new JeecgBootException("素材操作参数无效或保存失败"); }
}
