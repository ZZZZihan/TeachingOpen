package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import lombok.extern.slf4j.Slf4j;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.constant.CacheConstant;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.RedisUtil;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.entity.SysUserDepart;
import org.jeecg.modules.system.mapper.SysDepartMapper;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.mapper.SysUserDepartMapper;
import org.jeecg.modules.system.model.DepartmentSelectionRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationAdapter;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.util.*;

/** A current department is a member's preference; it cannot assign membership. */
@Service
@Slf4j
public class DepartmentSelectionService {
    private final SysUserMapper users;
    private final SysDepartMapper departments;
    private final SysUserDepartMapper memberships;
    private final RedisUtil redis;

    public DepartmentSelectionService(SysUserMapper users, SysDepartMapper departments,
            SysUserDepartMapper memberships, RedisUtil redis) {
        this.users=users; this.departments=departments; this.memberships=memberships; this.redis=redis;
    }

    @Transactional(rollbackFor = Exception.class)
    public SysUser select(DepartmentSelectionRequest request) {
        Object principal=SecurityUtils.getSubject().getPrincipal();
        if (!(principal instanceof LoginUser) || request == null) throw denied();
        LoginUser actor=(LoginUser) principal;
        if (request.getUsername() != null && !request.getUsername().isEmpty()
                && !Objects.equals(actor.getUsername(), request.getUsername())) throw denied();
        String orgCode=request.getOrgCode();
        if (orgCode == null || !orgCode.matches("[A-Za-z0-9]{1,64}")) throw denied();
        // Same lock order as membership administration: department, then account,
        // then membership. Removal cannot commit between validation and this write.
        SysDepart department=departments.selectOne(new QueryWrapper<SysDepart>().eq("org_code",orgCode).last("FOR UPDATE"));
        if (department == null || !orgCode.equals(department.getOrgCode()) || !"0".equals(department.getDelFlag())) throw denied();
        List<SysUser> locked=users.lockAdministrationUsers(Collections.singletonList(actor.getId()));
        if (locked.size()!=1) throw denied();
        SysUser user=locked.get(0);
        if (!Objects.equals(actor.getId(),user.getId()) || !Objects.equals(actor.getUsername(),user.getUsername())
                || !Integer.valueOf(1).equals(user.getStatus()) || !Integer.valueOf(0).equals(user.getDelFlag())) throw denied();
        List<SysUserDepart> selected=memberships.selectList(new QueryWrapper<SysUserDepart>()
                .eq("user_id",user.getId()).eq("dep_id",department.getId()).last("FOR UPDATE"));
        if (selected.stream().noneMatch(m -> user.getId().equals(m.getUserId()) && department.getId().equals(m.getDepId()))) throw denied();
        if (users.update(new SysUser().setOrgCode(department.getOrgCode()), new QueryWrapper<SysUser>().eq("id",user.getId())) != 1)
            throw new JeecgBootException("切换部门失败");
        user.setOrgCode(department.getOrgCode());
        Runnable evict=() -> {
            try { redis.del(CacheConstant.SYS_USERS_CACHE + "::" + user.getUsername()); }
            catch (RuntimeException failure) { log.warn("部门切换已提交，用户缓存清理失败", failure); }
        };
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronizationAdapter() {
                @Override public void afterCommit() { evict.run(); }
            });
        } else evict.run();
        return user;
    }
    private UnauthorizedException denied() { return new UnauthorizedException("只能切换本人已加入的部门"); }
}
