package org.jeecg.modules.system.service;

import java.util.List;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.mapper.SysUserRoleMapper;
import org.springframework.stereotype.Service;

/** Infrastructure administration is reserved for the current, active dev role. */
@Service
public class InfrastructureAccessService {
    private final SysUserMapper users;
    private final SysUserRoleMapper roles;

    public InfrastructureAccessService(SysUserMapper users, SysUserRoleMapper roles) {
        this.users = users;
        this.roles = roles;
    }

    public void requireOperator() {
        Object principal = SecurityUtils.getSubject().getPrincipal();
        if (!(principal instanceof LoginUser)) throw new UnauthorizedException("请先登录");
        String id = ((LoginUser) principal).getId();
        if (id == null || id.isEmpty()) throw new UnauthorizedException("账户不可用");
        SysUser current = users.selectById(id);
        if (current == null || !id.equals(current.getId()) || !Integer.valueOf(0).equals(current.getDelFlag())
                || !Integer.valueOf(1).equals(current.getStatus())) throw new UnauthorizedException("账户不可用");
        // Do not trust cached Shiro roles or a previous request's principal after revocation.
        List<String> assigned = roles.getRoleByUserId(id);
        if (assigned == null || !assigned.contains("dev")) throw new UnauthorizedException("没有运维管理权限");
    }
}
