package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.PasswordUtil;
import org.jeecg.common.util.oConvertUtils;
import org.jeecg.modules.system.entity.*;
import org.jeecg.modules.system.mapper.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationAdapter;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.util.*;
import java.util.stream.Collectors;

/** One transactional boundary for account and role administration. */
@Service
public class AccountAdministrationService {
    private final SysUserMapper users;
    private final SysRoleMapper roles;
    private final SysUserRoleMapper userRoles;
    private final SysUserDepartMapper userDeparts;
    private final SysDepartRoleUserMapper departRoles;
    private final SysDepartMapper departs;
    private final PasswordResetCodeStore caches;

    public AccountAdministrationService(SysUserMapper users, SysRoleMapper roles,
            SysUserRoleMapper userRoles, SysUserDepartMapper userDeparts,
            SysDepartRoleUserMapper departRoles, SysDepartMapper departs, PasswordResetCodeStore caches) {
        this.users = users; this.roles = roles; this.userRoles = userRoles;
        this.userDeparts = userDeparts; this.departRoles = departRoles; this.departs = departs; this.caches = caches;
    }

    public LoginUser requireAdministrator() {
        Object principal = SecurityUtils.getSubject().getPrincipal();
        if (!(principal instanceof LoginUser)) throw new UnauthorizedException("没有账户管理权限");
        LoginUser operator = (LoginUser) principal;
        // Administrative writes use current database roles, not a cached grant.
        List<String> assigned = userRoles.getRoleByUserId(operator.getId());
        if (assigned == null || (!assigned.contains("admin") && !assigned.contains("dev"))) {
            throw new UnauthorizedException("没有账户管理权限");
        }
        return operator;
    }

    public static List<String> ids(Collection<String> requested) {
        if (requested == null || requested.isEmpty() || requested.size() > 100) {
            throw new JeecgBootException("请选择1至100个目标");
        }
        Set<String> result = new TreeSet<>();
        for (String id : requested) {
            if (id == null || id.trim().isEmpty()) throw new JeecgBootException("目标ID不能为空");
            result.add(id.trim());
        }
        return new ArrayList<>(result);
    }

    public static List<String> ids(String requested) {
        // Older list widgets append one trailing delimiter; interior empty IDs remain invalid.
        if (requested != null && requested.endsWith(",")) requested = requested.substring(0, requested.length() - 1);
        return ids(requested == null ? null : Arrays.asList(requested.split(",", -1)));
    }

    private int level(String userId) {
        Integer value = userRoles.getUserRoleLevel(userId);
        return value == null ? -1 : value;
    }

    public void requireAssignableRoles(Collection<String> roleIds) {
        LoginUser operator = requireAdministrator();
        for (String id : ids(roleIds)) requireRole(operator, id);
    }

    private SysRole requireRole(LoginUser operator, String roleId) {
        SysRole role = roles.selectById(roleId);
        List<String> assigned = userRoles.getRoleByUserId(operator.getId());
        if (role == null || !roleId.equals(role.getId()) || role.getRoleLevel() == null
                || role.getRoleLevel() > level(operator.getId())
                || ("dev".equals(role.getRoleCode()) && !assigned.contains("dev"))) {
            throw new UnauthorizedException("不允许分配或移除此角色");
        }
        return role;
    }

    private List<SysUser> lockTargets(LoginUser operator, List<String> targetIds, int deleted) {
        Set<String> lockIds = new TreeSet<>(targetIds);
        lockIds.add(operator.getId());
        List<SysUser> locked = users.lockAdministrationUsers(new ArrayList<>(lockIds));
        Map<String, SysUser> byId = locked.stream().collect(Collectors.toMap(SysUser::getId, u -> u));
        if (!byId.keySet().equals(lockIds)) throw new JeecgBootException("未找到全部目标用户");
        SysUser current = byId.get(operator.getId());
        if (!Integer.valueOf(0).equals(current.getDelFlag()) || !Integer.valueOf(1).equals(current.getStatus())) {
            throw new UnauthorizedException("账户不可用");
        }
        requireAdministrator();
        List<SysUser> result = new ArrayList<>();
        for (String id : targetIds) {
            SysUser user = byId.get(id);
            if (!Integer.valueOf(deleted).equals(user.getDelFlag())) {
                throw new JeecgBootException(deleted == 1 ? "整批用户必须都在回收站中" : "目标用户不可用");
            }
            if (level(id) > level(operator.getId())) throw new UnauthorizedException("不能管理更高权限的账户");
            result.add(user);
        }
        return result;
    }

    private void refreshAfterCommit(List<SysUser> affected) {
        Runnable refresh = () -> affected.forEach(u -> caches.clearUserCaches(u.getId(), u.getUsername()));
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronizationAdapter() {
                @Override public void afterCommit() { refresh.run(); }
            });
        } else {
            refresh.run();
        }
    }

    @Transactional(rollbackFor = Exception.class)
    public void changeRole(String roleId, Collection<String> requested, boolean add) {
        LoginUser operator = requireAdministrator();
        List<String> targetIds = ids(requested);
        List<SysUser> targets = lockTargets(operator, targetIds, 0);
        requireRole(operator, roleId);
        for (SysUser user : targets) {
            LambdaQueryWrapper<SysUserRole> query = new LambdaQueryWrapper<SysUserRole>()
                    .eq(SysUserRole::getUserId, user.getId()).eq(SysUserRole::getRoleId, roleId);
            if (add) {
                if (userRoles.selectCount(query) == 0 && userRoles.insert(new SysUserRole(user.getId(), roleId)) != 1) {
                    throw new JeecgBootException("角色分配失败");
                }
            } else {
                userRoles.delete(query);
            }
        }
        refreshAfterCommit(targets);
    }

    @Transactional(rollbackFor = Exception.class)
    public void resetPassword(String targetId, String password) {
        LoginUser operator = requireAdministrator();
        List<SysUser> targets = lockTargets(operator, ids(Collections.singletonList(targetId)), 0);
        if (!PasswordResetService.validPassword(password)) throw new JeecgBootException("密码须为8至64位，包含字母、数字和特殊字符");
        SysUser target = targets.get(0);
        String salt = oConvertUtils.randomGen(8);
        SysUser patch = new SysUser().setSalt(salt)
                .setPassword(PasswordUtil.encrypt(target.getUsername(), password, salt));
        if (users.update(patch, new LambdaUpdateWrapper<SysUser>().eq(SysUser::getId, target.getId())) != 1) {
            throw new JeecgBootException("密码修改失败");
        }
        refreshAfterCommit(targets);
    }

    @Transactional(rollbackFor = Exception.class)
    public void saveAccount(SysUser request, String roleIds, String departIds, boolean create) {
        LoginUser operator = requireAdministrator();
        if (request == null) throw new JeecgBootException("用户资料不能为空");
        SysUser existing = create ? null : lockTargets(operator, ids(Collections.singletonList(request.getId())), 0).get(0);
        List<String> selectedRoles;
        if (roleIds == null || roleIds.trim().isEmpty()) {
            SysRole student = roles.selectOne(new LambdaQueryWrapper<SysRole>().eq(SysRole::getRoleCode, "student"));
            if (student == null) throw new JeecgBootException("学生角色不存在");
            selectedRoles = Collections.singletonList(student.getId());
        } else selectedRoles = ids(roleIds);
        for (String roleId : selectedRoles) requireRole(operator, roleId);
        List<String> selectedDeparts = departIds == null || departIds.trim().isEmpty()
                ? Collections.emptyList() : ids(departIds);
        if (!selectedDeparts.isEmpty()) {
            Set<String> found = departs.selectList(new LambdaQueryWrapper<SysDepart>()
                    .in(SysDepart::getId, selectedDeparts).eq(SysDepart::getDelFlag, "0"))
                    .stream().map(SysDepart::getId).collect(Collectors.toSet());
            if (!found.equals(new HashSet<>(selectedDeparts))) throw new JeecgBootException("未找到全部目标部门");
        }
        // Administrative edits also preserve credential and identity columns.
        SysUser patch = new SysUser().setRealname(request.getRealname()).setAvatar(request.getAvatar())
                .setBirthday(request.getBirthday()).setSex(request.getSex()).setEmail(request.getEmail())
                .setPhone(request.getPhone()).setWorkNo(request.getWorkNo()).setPost(request.getPost())
                .setTelephone(request.getTelephone()).setUserIdentity(request.getUserIdentity())
                .setDepartIds(request.getDepartIds()).setOrgCode(request.getOrgCode()).setSchool(request.getSchool());
        if (create) {
            if (request.getUsername() == null || !request.getUsername().matches("[A-Za-z0-9_@.\\-]{3,100}")
                    || !PasswordResetService.validPassword(request.getPassword())) {
                throw new JeecgBootException("账号或密码格式不正确");
            }
            String salt = oConvertUtils.randomGen(8);
            patch.setUsername(request.getUsername()).setSalt(salt)
                    .setPassword(PasswordUtil.encrypt(request.getUsername(), request.getPassword(), salt))
                    .setStatus(1).setDelFlag(0);
            if (users.insert(patch) != 1) throw new JeecgBootException("新增账户失败");
        } else {
            patch.setId(existing.getId());
            if (users.updateById(patch) != 1) throw new JeecgBootException("修改账户失败");
            userRoles.delete(new LambdaQueryWrapper<SysUserRole>().eq(SysUserRole::getUserId, patch.getId()));
            userDeparts.delete(new LambdaQueryWrapper<SysUserDepart>().eq(SysUserDepart::getUserId, patch.getId()));
        }
        for (String roleId : selectedRoles) {
            if (userRoles.insert(new SysUserRole(patch.getId(), roleId)) != 1) throw new JeecgBootException("角色分配失败");
        }
        for (String departId : selectedDeparts) {
            if (userDeparts.insert(new SysUserDepart(patch.getId(), departId)) != 1) throw new JeecgBootException("部门分配失败");
        }
        refreshAfterCommit(Collections.singletonList(create ? patch : existing));
    }

    /** Each import row has the same grant checks and transaction as the account form. */
    @Transactional(rollbackFor = Exception.class)
    public void importAccount(SysUser request, String roleReferences, String departReferences, boolean studentOnly) {
        LoginUser operator = requireAdministrator();
        List<String> resolvedRoles = new ArrayList<>();
        String references = studentOnly || roleReferences == null || roleReferences.trim().isEmpty()
                ? "student" : roleReferences;
        for (String reference : ids(references)) {
            List<SysRole> found = roles.selectList(new LambdaQueryWrapper<SysRole>()
                    .eq(SysRole::getId, reference).or().eq(SysRole::getRoleCode, reference)
                    .or().eq(SysRole::getRoleName, reference));
            if (found.size() != 1) throw new JeecgBootException("角色不存在或名称不唯一");
            requireRole(operator, found.get(0).getId());
            resolvedRoles.add(found.get(0).getId());
        }
        List<String> resolvedDeparts = new ArrayList<>();
        if (departReferences != null && !departReferences.trim().isEmpty()) {
            for (String reference : ids(departReferences)) {
                List<SysDepart> found = departs.selectList(new LambdaQueryWrapper<SysDepart>()
                        .and(q -> q.eq(SysDepart::getId, reference).or().eq(SysDepart::getOrgCode, reference)
                                .or().eq(SysDepart::getDepartName, reference)).eq(SysDepart::getDelFlag, "0"));
                if (found.size() != 1) throw new JeecgBootException("部门不存在或名称不唯一");
                resolvedDeparts.add(found.get(0).getId());
            }
        }
        SysUser existing = studentOnly ? users.selectOne(new LambdaQueryWrapper<SysUser>()
                .eq(SysUser::getUsername, request.getUsername())) : null;
        if (existing == null) {
            saveAccount(request, String.join(",", resolvedRoles), String.join(",", resolvedDeparts), true);
            return;
        }
        // Class import may attach an existing account, but may not replace its identity or credentials.
        lockTargets(operator, Collections.singletonList(existing.getId()), 0);
        for (String department : resolvedDeparts) {
            LambdaQueryWrapper<SysUserDepart> query = new LambdaQueryWrapper<SysUserDepart>()
                    .eq(SysUserDepart::getUserId, existing.getId()).eq(SysUserDepart::getDepId, department);
            if (userDeparts.selectCount(query) == 0 && userDeparts.insert(new SysUserDepart(existing.getId(), department)) != 1)
                throw new JeecgBootException("部门分配失败");
        }
        refreshAfterCommit(Collections.singletonList(existing));
    }

    @Transactional(rollbackFor = Exception.class)
    public void deleteAccounts(Collection<String> requested) {
        LoginUser operator = requireAdministrator();
        List<String> targets = ids(requested);
        List<SysUser> affected = lockTargets(operator, targets, 0);
        if (targets.contains(operator.getId())) throw new JeecgBootException("不能删除当前登录账户");
        if (users.deleteBatchIds(targets) != targets.size()) throw new JeecgBootException("删除用户失败");
        refreshAfterCommit(affected);
    }

    @Transactional(rollbackFor = Exception.class)
    public void recycle(Collection<String> requested, boolean restore) {
        LoginUser operator = requireAdministrator();
        List<String> targetIds = ids(requested);
        List<SysUser> targets = lockTargets(operator, targetIds, 1);
        if (restore) {
            SysUser patch = new SysUser().setUpdateBy(operator.getUsername()).setUpdateTime(new Date());
            if (users.revertLogicDeleted(targetIds, patch) != targetIds.size()) throw new JeecgBootException("还原失败");
        } else {
            if (users.deleteLogicDeleted(targetIds) != targetIds.size()) throw new JeecgBootException("删除失败");
            userDeparts.delete(new LambdaQueryWrapper<SysUserDepart>().in(SysUserDepart::getUserId, targetIds));
            userRoles.delete(new LambdaQueryWrapper<SysUserRole>().in(SysUserRole::getUserId, targetIds));
            departRoles.delete(new LambdaQueryWrapper<SysDepartRoleUser>().in(SysDepartRoleUser::getUserId, targetIds));
        }
        refreshAfterCommit(targets);
    }
}
