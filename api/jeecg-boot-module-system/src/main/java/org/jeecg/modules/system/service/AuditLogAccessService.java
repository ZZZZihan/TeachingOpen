package org.jeecg.modules.system.service;

import java.util.List;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.mapper.SysUserRoleMapper;
import org.springframework.stereotype.Service;

/** Audit payloads and version snapshots are management data, including historical rows. */
@Service
public class AuditLogAccessService {
    private final SysUserMapper users;
    private final SysUserRoleMapper roles;

    public AuditLogAccessService(SysUserMapper users, SysUserRoleMapper roles) {
        this.users = users; this.roles = roles;
    }

    public void requireManager() {
        Object principal = SecurityUtils.getSubject().getPrincipal();
        if (!(principal instanceof LoginUser)) throw denied();
        String id = ((LoginUser) principal).getId();
        if (id == null || id.trim().isEmpty()) throw denied();
        SysUser user = users.selectById(id);
        if (user == null || !id.equals(user.getId()) || !Integer.valueOf(1).equals(user.getStatus())
                || !Integer.valueOf(0).equals(user.getDelFlag())) throw denied();
        List<String> assigned = roles.getRoleByUserId(id);
        if (assigned == null || (!assigned.contains("admin") && !assigned.contains("dev"))) throw denied();
    }

    private UnauthorizedException denied() { return new UnauthorizedException("没有审计日志管理权限"); }
}
