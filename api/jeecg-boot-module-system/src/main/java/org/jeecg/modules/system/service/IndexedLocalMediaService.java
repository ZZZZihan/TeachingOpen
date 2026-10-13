package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.beans.factory.annotation.Autowired;

import java.io.Serializable;
import java.util.*;

/** ID-based source writes and their derived references commit or roll back together. */
public class IndexedLocalMediaService<M extends BaseMapper<T>, T> extends ServiceImpl<M, T> {
    @Autowired protected LocalMediaReferenceIndex mediaIndex;

    protected LocalMediaSource mediaSource() {
        return LocalMediaSource.forTable(currentModelClass().getAnnotation(TableName.class).value());
    }
    private String id(T entity) {
        Object id = new BeanWrapperImpl(entity).getPropertyValue("id");
        if (id == null) throw new IllegalStateException("Persisted media source has no id");
        return id.toString();
    }
    protected void indexMedia(String id) { mediaIndex.replace(mediaSource(), id); }

    @Override public boolean save(T entity) {
        return mediaIndex.write(() -> {
            boolean changed = super.save(entity);
            if (changed) indexMedia(id(entity));
            return changed;
        });
    }
    @Override public boolean updateById(T entity) {
        return mediaIndex.write(() -> {
            boolean changed = super.updateById(entity);
            if (changed) indexMedia(id(entity));
            return changed;
        });
    }
    @Override public boolean saveBatch(Collection<T> entities, int batchSize) {
        return mediaIndex.write(() -> {
            boolean changed = super.saveBatch(entities, batchSize);
            if (changed) for (T entity : entities) indexMedia(id(entity));
            return changed;
        });
    }
    @Override public boolean updateBatchById(Collection<T> entities, int batchSize) {
        return mediaIndex.write(() -> {
            boolean changed = super.updateBatchById(entities, batchSize);
            if (changed) for (T entity : entities) indexMedia(id(entity));
            return changed;
        });
    }
    @Override public boolean saveOrUpdate(T entity) {
        return mediaIndex.write(() -> super.saveOrUpdate(entity));
    }
    @Override public boolean saveOrUpdateBatch(Collection<T> entities, int batchSize) {
        return mediaIndex.write(() -> {
            boolean changed = super.saveOrUpdateBatch(entities, batchSize);
            if (changed) for (T entity : entities) indexMedia(id(entity));
            return changed;
        });
    }
    @Override public boolean removeById(Serializable id) {
        return mediaIndex.write(() -> {
            boolean changed = super.removeById(id);
            if (changed) indexMedia(id.toString());
            return changed;
        });
    }
    @Override public boolean removeByIds(Collection<? extends Serializable> ids) {
        return mediaIndex.write(() -> {
            boolean changed = super.removeByIds(ids);
            if (changed) for (Serializable id : ids) indexMedia(id.toString());
            return changed;
        });
    }

    // No application caller uses unrestricted wrapper writes on these sources.
    // Reject new bypasses explicitly instead of silently creating an incomplete index.
    @Override public boolean update(T entity, Wrapper<T> wrapper) {
        throw new UnsupportedOperationException("Local media sources require ID-based transactional updates");
    }
    @Override public boolean remove(Wrapper<T> wrapper) {
        throw new UnsupportedOperationException("Local media sources require ID-based transactional deletes");
    }
    @Override public boolean removeByMap(Map<String, Object> columns) {
        throw new UnsupportedOperationException("Local media sources require ID-based transactional deletes");
    }
}
