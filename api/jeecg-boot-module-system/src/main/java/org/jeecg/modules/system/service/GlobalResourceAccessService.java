package org.jeecg.modules.system.service;

import java.util.List;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.mapper.SysUserRoleMapper;
import org.springframework.stereotype.Service;

/** Live boundary for shared application resources, separate from class-scoped teaching writes. */
@Service
public class GlobalResourceAccessService {
    private final SysUserMapper users;
    private final SysUserRoleMapper roles;

    public GlobalResourceAccessService(SysUserMapper users, SysUserRoleMapper roles) {
        this.users = users; this.roles = roles;
    }

    public SysUser requireAdministrator() {
        Object principal = SecurityUtils.getSubject().getPrincipal();
        if (!(principal instanceof LoginUser)) throw denied();
        String id = ((LoginUser) principal).getId();
        if (id == null || id.isEmpty()) throw denied();
        SysUser actor = users.selectById(id);
        if (actor == null || !id.equals(actor.getId()) || !Integer.valueOf(1).equals(actor.getStatus())
                || !Integer.valueOf(0).equals(actor.getDelFlag())) throw denied();
        List<String> current = roles.getRoleByUserId(id);
        if (current == null || (!current.contains("admin") && !current.contains("dev"))) throw denied();
        return actor;
    }

    private UnauthorizedException denied() { return new UnauthorizedException("没有全局资源管理权限"); }
}
