package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.apache.commons.lang.StringUtils;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysDepartMapper;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.mapper.SysUserRoleMapper;
import org.springframework.stereotype.Service;
import java.util.*;

/** Live account/class boundary for private user searches, including aliases and exports. */
@Service
public class UserQueryAccessService {
    private final SysUserMapper users;
    private final SysUserRoleMapper roles;
    private final SysDepartMapper departments;
    private final ISysDepartService departmentService;

    public UserQueryAccessService(SysUserMapper users, SysUserRoleMapper roles,
            SysDepartMapper departments, ISysDepartService departmentService) {
        this.users = users; this.roles = roles; this.departments = departments; this.departmentService = departmentService;
    }

    public SysUser currentUser() {
        Object principal = SecurityUtils.getSubject().getPrincipal();
        if (!(principal instanceof LoginUser)) throw denied();
        LoginUser identity = (LoginUser) principal;
        SysUser user = users.selectById(identity.getId());
        if (user == null || !identity.getId().equals(user.getId())
                || !Integer.valueOf(1).equals(user.getStatus()) || !Integer.valueOf(0).equals(user.getDelFlag())) throw denied();
        return user;
    }

    public boolean isAdministrator(SysUser user) {
        List<String> assigned = roles.getRoleByUserId(user.getId());
        return assigned != null && (assigned.contains("admin") || assigned.contains("dev"));
    }

    public void requireAdministrator() {
        if (!isAdministrator(currentUser())) throw denied();
    }

    public List<String> managedDepartmentIds(SysUser user) {
        List<String> assigned = roles.getRoleByUserId(user.getId());
        if (assigned == null || !assigned.contains("teacher") || StringUtils.isBlank(user.getDepartIds())) throw denied();
        List<String> ids = departmentService.getMySubDepIdsByDepId(user.getDepartIds());
        if (ids == null || ids.isEmpty()) throw denied();
        return ids;
    }

    public void limitUsers(QueryWrapper<?> query) {
        SysUser user = currentUser();
        if (!isAdministrator(user)) UserQueryFilters.departments(query, managedDepartmentIds(user));
    }

    public SysDepart requireDepartment(String id) {
        SysUser user = currentUser();
        SysDepart department = departments.selectById(id);
        if (department == null || !Objects.equals(id, department.getId()) || !"0".equals(department.getDelFlag())) throw denied();
        if (!isAdministrator(user) && !managedDepartmentIds(user).contains(department.getId())) throw denied();
        return department;
    }

    public String requireOrganization(String orgCode) {
        SysUser user = currentUser();
        if (StringUtils.isBlank(orgCode)) {
            if (isAdministrator(user)) return "";
            throw denied();
        }
        // Organization codes are generated as alphanumeric paths. A prefix is only
        // accepted when it identifies a real authorized object, never an arbitrary range.
        if (!orgCode.matches("[A-Za-z0-9]{1,64}")) throw denied();
        SysDepart department = departments.selectOne(new QueryWrapper<SysDepart>().eq("org_code", orgCode));
        if (department == null || !orgCode.equals(department.getOrgCode()) || !"0".equals(department.getDelFlag())) throw denied();
        if (!isAdministrator(user) && !managedDepartmentIds(user).contains(department.getId())) throw denied();
        return department.getOrgCode();
    }

    private UnauthorizedException denied() { return new UnauthorizedException("没有用户资料查询权限"); }
}
