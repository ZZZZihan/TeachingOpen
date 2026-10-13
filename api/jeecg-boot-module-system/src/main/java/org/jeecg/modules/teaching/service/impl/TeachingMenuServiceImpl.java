package org.jeecg.modules.teaching.service.impl;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.IdWorker;
import org.jeecg.common.constant.CacheConstant;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.teaching.entity.TeachingMenu;
import org.jeecg.modules.teaching.mapper.TeachingMenuMapper;
import org.jeecg.modules.teaching.model.TreeModel;
import org.jeecg.modules.teaching.service.ITeachingMenuService;
import org.jeecg.modules.teaching.service.TeachingMenuAccessService;
import org.jeecg.modules.teaching.util.TeachingMenuUrlPolicy;
import org.springframework.beans.BeanUtils;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;
import java.util.stream.Collectors;

@Service
public class TeachingMenuServiceImpl implements ITeachingMenuService {
    private final TeachingMenuMapper menus;
    private final TeachingMenuAccessService access;
    public TeachingMenuServiceImpl(TeachingMenuMapper menus, TeachingMenuAccessService access) { this.menus = menus; this.access = access; }

    @Override public List<TeachingMenu> listPublic() {
        return menus.selectList(new QueryWrapper<TeachingMenu>().eq("hidden", 0).eq("del_flag", 0).orderByAsc("sort_no"))
                .stream().filter(menu -> Integer.valueOf(0).equals(menu.getDelFlag()) && !menu.isHidden()
                        && (Integer.valueOf(0).equals(menu.getMenuType()) || Integer.valueOf(1).equals(menu.getMenuType())))
                .map(TeachingMenuServiceImpl::publicMenu).collect(Collectors.toList());
    }
    private static TeachingMenu publicMenu(TeachingMenu stored) {
        TeachingMenu copy = new TeachingMenu(); BeanUtils.copyProperties(stored, copy);
        String url = TeachingMenuUrlPolicy.safeUrl(stored.getUrl());
        copy.setUrl(url == null ? "" : url);
        copy.setRoute(url != null && TeachingMenuUrlPolicy.local(url) && stored.isRoute());
        copy.setInternalOrExternal(url != null && !url.isEmpty() && stored.isInternalOrExternal());
        return copy;
    }
    @Override public List<TeachingMenu> listManaged(Wrapper<TeachingMenu> query) { access.requireManager(); return menus.selectList(query); }
    @Override public List<TreeModel> queryListByParentId(String parentId) {
        access.requireManager();
        QueryWrapper<TeachingMenu> query = new QueryWrapper<TeachingMenu>().eq("del_flag", 0).orderByAsc("sort_no");
        if (parentId == null || parentId.trim().isEmpty()) query.and(root -> root.isNull("parent_id").or().eq("parent_id", ""));
        else query.eq("parent_id", parentId);
        return menus.selectList(query).stream().map(TreeModel::new).collect(Collectors.toList());
    }
    @Override @Transactional @CacheEvict(value = CacheConstant.TEACHING_MENU_CACHE, allEntries = true)
    public void addPermission(TeachingMenu input) {
        SysUser actor = access.requireManager();
        TeachingMenu value = validated(input, null);
        value.setId(IdWorker.getIdStr()).setCreateBy(actor.getUsername()).setCreateTime(new Date()).setDelFlag(0).setLeaf(true);
        if (menus.insert(value) != 1) throw new JeecgBootException("新增菜单失败");
        refreshLeaf(value.getParentId());
    }
    @Override @Transactional @CacheEvict(value = CacheConstant.TEACHING_MENU_CACHE, allEntries = true)
    public void editPermission(TeachingMenu input) {
        SysUser actor = access.requireManager();
        TeachingMenu stored = requireExisting(input == null ? null : input.getId());
        TeachingMenu value = validated(input, stored.getId());
        value.setId(stored.getId()).setDelFlag(0).setCreateBy(stored.getCreateBy()).setCreateTime(stored.getCreateTime())
                .setUpdateBy(actor.getUsername()).setUpdateTime(new Date()).setLeaf(childCount(stored.getId()) == 0);
        if (menus.updateById(value) != 1) throw new JeecgBootException("修改菜单失败");
        refreshLeaf(value.getParentId());
        if (!Objects.equals(value.getParentId(), stored.getParentId())) refreshLeaf(stored.getParentId());
    }
    @Override @Transactional @CacheEvict(value = CacheConstant.TEACHING_MENU_CACHE, allEntries = true)
    public void deletePermission(String id) { deletePermissions(Collections.singletonList(id)); }
    @Override @Transactional @CacheEvict(value = CacheConstant.TEACHING_MENU_CACHE, allEntries = true)
    public void deletePermissions(Collection<String> ids) {
        access.requireManager();
        if (ids == null || ids.isEmpty()) throw new JeecgBootException("请选择菜单");
        Set<String> removed = new LinkedHashSet<>();
        for (String id : ids) removed.add(requireExisting(id).getId());
        List<TeachingMenu> all = menus.selectList(new QueryWrapper<>());
        boolean added;
        do {
            added = false;
            for (TeachingMenu row : all) if (removed.contains(row.getParentId())) added |= removed.add(row.getId());
        } while (added);
        // Validate every requested identity before the first write; one transaction owns the cascade.
        if (menus.deleteBatchIds(removed) != removed.size()) throw new JeecgBootException("菜单已变化，请刷新后重试");
        for (TeachingMenu row : all) if (removed.contains(row.getId()) && !removed.contains(row.getParentId())) refreshLeaf(row.getParentId());
    }
    private TeachingMenu validated(TeachingMenu input, String id) {
        if (input == null) throw new JeecgBootException("菜单信息不能为空");
        String name = input.getName() == null ? "" : input.getName().trim();
        if (name.isEmpty() || name.length() > 100) throw new JeecgBootException("菜单名称应为1到100个字符");
        if (!Integer.valueOf(0).equals(input.getMenuType()) && !Integer.valueOf(1).equals(input.getMenuType())) throw new JeecgBootException("菜单类型无效");
        String url = TeachingMenuUrlPolicy.safeUrl(input.getUrl());
        if (url == null) throw new JeecgBootException("菜单路径仅支持站内绝对路径或HTTPS链接");
        Double sort = input.getSortNo() == null ? 0D : input.getSortNo();
        if (sort.isNaN() || sort.isInfinite() || Math.abs(sort) > 999999.99) throw new JeecgBootException("菜单排序无效");
        Integer needLogin = input.getNeedLogin() == null ? 0 : input.getNeedLogin();
        if (needLogin != 0 && needLogin != 1) throw new JeecgBootException("登录显示设置无效");
        String icon = input.getIcon();
        if (icon != null && !icon.isEmpty() && !icon.matches("[A-Za-z0-9_-]{1,100}")) throw new JeecgBootException("菜单图标无效");
        if (input.getDescription() != null && input.getDescription().length() > 255) throw new JeecgBootException("菜单描述过长");
        String parent = Integer.valueOf(0).equals(input.getMenuType()) ? "" : input.getParentId();
        if (input.getMenuType() == 1) {
            if (parent == null || parent.isEmpty()) throw new JeecgBootException("请选择上级菜单");
            Set<String> visited = new HashSet<>(); if (id != null) visited.add(id);
            String ancestor = parent;
            while (ancestor != null && !ancestor.isEmpty()) {
                if (!visited.add(ancestor)) throw new JeecgBootException("菜单层级不能形成循环");
                ancestor = requireExisting(ancestor).getParentId();
            }
        }
        return new TeachingMenu().setName(name).setParentId(parent).setMenuType(input.getMenuType()).setUrl(url).setSortNo(sort)
                .setIcon(icon).setDescription(input.getDescription()).setHidden(input.isHidden()).setNeedLogin(needLogin)
                .setRoute(TeachingMenuUrlPolicy.local(url) && input.isRoute()).setInternalOrExternal(!url.isEmpty() && input.isInternalOrExternal());
    }
    private TeachingMenu requireExisting(String id) {
        if (id == null || id.trim().isEmpty()) throw new JeecgBootException("菜单不存在");
        TeachingMenu value = menus.selectById(id);
        if (value == null || !Integer.valueOf(0).equals(value.getDelFlag())) throw new JeecgBootException("菜单不存在");
        return value;
    }
    private int childCount(String id) { return menus.selectCount(new QueryWrapper<TeachingMenu>().eq("parent_id", id).eq("del_flag", 0)); }
    private void refreshLeaf(String id) { if (id != null && !id.isEmpty()) menus.setMenuLeaf(id, childCount(id) == 0 ? 1 : 0); }
}
