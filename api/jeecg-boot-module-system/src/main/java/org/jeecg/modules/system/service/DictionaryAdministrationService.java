package org.jeecg.modules.system.service;

import java.util.Collection;
import java.util.List;
import java.util.Set;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.constant.CacheConstant;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysDict;
import org.jeecg.modules.system.entity.SysDictItem;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.mapper.SysUserRoleMapper;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Shared boundary for dictionary management, including imports and recycle-bin writes. */
@Service
public class DictionaryAdministrationService {
    private final SysUserMapper users;
    private final SysUserRoleMapper roles;
    private final ISysDictService dictionaries;
    private final ISysDictItemService items;
    private final RedisTemplate<String, Object> redis;

    public DictionaryAdministrationService(SysUserMapper users, SysUserRoleMapper roles,
            ISysDictService dictionaries, ISysDictItemService items, RedisTemplate<String, Object> redis) {
        this.users = users;
        this.roles = roles;
        this.dictionaries = dictionaries;
        this.items = items;
        this.redis = redis;
    }

    public void requireManager() {
        Object principal = SecurityUtils.getSubject().getPrincipal();
        if (!(principal instanceof LoginUser)) throw new UnauthorizedException("请先登录");
        String id = ((LoginUser) principal).getId();
        if (id == null || id.isEmpty()) throw new UnauthorizedException("账户不可用");
        SysUser actor = users.selectById(id);
        if (actor == null || !id.equals(actor.getId()) || !Integer.valueOf(0).equals(actor.getDelFlag())
                || !Integer.valueOf(1).equals(actor.getStatus())) throw new UnauthorizedException("账户不可用");
        // Match dict_code duplicate checking; cached Shiro roles cannot retain revoked access.
        List<String> current = roles.getRoleByUserId(id);
        if (current == null || (!current.contains("admin") && !current.contains("dev"))) {
            throw new UnauthorizedException("没有字典管理权限");
        }
    }

    @CacheEvict(value = CacheConstant.SYS_DICT_CACHE, allEntries = true)
    public boolean addDictionary(SysDict value) {
        requireManager();
        return dictionaries.save(value);
    }

    @CacheEvict(value = CacheConstant.SYS_DICT_CACHE, allEntries = true)
    public boolean editDictionary(SysDict value) {
        requireManager();
        return dictionaries.updateById(value);
    }

    @CacheEvict(value = CacheConstant.SYS_DICT_CACHE, allEntries = true)
    public boolean deleteDictionary(String id) {
        requireManager();
        return dictionaries.removeById(id);
    }

    @CacheEvict(value = CacheConstant.SYS_DICT_CACHE, allEntries = true)
    public boolean deleteDictionaries(Collection<String> ids) {
        requireManager();
        return dictionaries.removeByIds(ids);
    }

    @Transactional(rollbackFor = Exception.class)
    @CacheEvict(value = CacheConstant.SYS_DICT_CACHE, allEntries = true)
    public Integer importDictionary(SysDict value, List<SysDictItem> children) {
        requireManager();
        return dictionaries.saveMain(value, children);
    }

    @Transactional(rollbackFor = Exception.class)
    @CacheEvict(value = CacheConstant.SYS_DICT_CACHE, allEntries = true)
    public void deleteDictionaryPermanently(String id) {
        requireManager();
        dictionaries.deleteOneDictPhysically(id);
    }

    @CacheEvict(value = CacheConstant.SYS_DICT_CACHE, allEntries = true)
    public void restoreDictionary(String id) {
        requireManager();
        dictionaries.updateDictDelFlag(0, id);
    }

    @CacheEvict(value = CacheConstant.SYS_DICT_CACHE, allEntries = true)
    public boolean addItem(SysDictItem value) {
        requireManager();
        return items.save(value);
    }

    @CacheEvict(value = CacheConstant.SYS_DICT_CACHE, allEntries = true)
    public boolean editItem(SysDictItem value) {
        requireManager();
        return items.updateById(value);
    }

    @CacheEvict(value = CacheConstant.SYS_DICT_CACHE, allEntries = true)
    public boolean deleteItem(String id) {
        requireManager();
        return items.removeById(id);
    }

    @CacheEvict(value = CacheConstant.SYS_DICT_CACHE, allEntries = true)
    public boolean deleteItems(Collection<String> ids) {
        requireManager();
        return items.removeByIds(ids);
    }

    public void refreshCache() {
        requireManager();
        for (String prefix : new String[]{CacheConstant.SYS_DICT_CACHE, CacheConstant.SYS_DICT_TABLE_CACHE,
                CacheConstant.SYS_DEPARTS_CACHE, CacheConstant.SYS_DEPART_IDS_CACHE}) {
            Set<String> keys = redis.keys(prefix + "*");
            if (keys != null && !keys.isEmpty()) redis.delete(keys);
        }
    }
}
