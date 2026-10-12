package org.jeecg.modules.teaching.service;

import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.mapper.SysUserRoleMapper;
import org.springframework.stereotype.Service;
import java.util.List;

/** Public navigation is readable anonymously; its administration requires a current grant. */
@Service
public class TeachingMenuAccessService {
    private final SysUserMapper users;
    private final SysUserRoleMapper roles;
    public TeachingMenuAccessService(SysUserMapper users, SysUserRoleMapper roles) { this.users = users; this.roles = roles; }
    public SysUser requireManager() {
        Object principal = SecurityUtils.getSubject().getPrincipal();
        if (!(principal instanceof LoginUser)) throw new UnauthorizedException("请先登录");
        String id = ((LoginUser) principal).getId();
        if (id == null || id.trim().isEmpty()) throw new UnauthorizedException("请先登录");
        SysUser user = users.selectById(id);
        if (user == null || !id.equals(user.getId()) || !Integer.valueOf(0).equals(user.getDelFlag()) || !Integer.valueOf(1).equals(user.getStatus()))
            throw new UnauthorizedException("账户不可用");
        List<String> assigned = roles.getRoleByUserId(user.getId());
        if (assigned == null || !(assigned.contains("admin") || assigned.contains("dev"))) throw new UnauthorizedException("没有菜单管理权限");
        return user;
    }
}
