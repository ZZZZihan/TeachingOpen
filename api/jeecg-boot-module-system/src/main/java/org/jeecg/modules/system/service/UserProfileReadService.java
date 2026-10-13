package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.entity.SysUserDepart;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.mapper.SysUserDepartMapper;
import org.jeecg.modules.system.model.UserProfileView;
import org.springframework.stereotype.Service;
import java.util.*;
import java.util.stream.Collectors;

/** Profile object authorization is shared by single, batch and compatibility reads. */
@Service
public class UserProfileReadService {
    private final UserQueryAccessService access;
    private final SysUserMapper users;
    private final SysUserDepartMapper memberships;
    public UserProfileReadService(UserQueryAccessService access, SysUserMapper users, SysUserDepartMapper memberships) {
        this.access=access; this.users=users; this.memberships=memberships;
    }

    public UserProfileView read(String id) { return readAll(Collections.singletonList(id)).get(0); }

    public List<UserProfileView> readAll(Collection<String> requested) {
        List<String> ids=AccountAdministrationService.ids(requested);
        SysUser actor=access.currentUser();
        boolean administrator=access.isAdministrator(actor);
        List<SysUser> targets=users.selectBatchIds(ids);
        Set<String> found=targets.stream().map(SysUser::getId).collect(Collectors.toSet());
        if (!found.equals(new HashSet<>(ids))) throw denied();
        if (!administrator && ids.stream().anyMatch(id -> !id.equals(actor.getId()))) {
            List<String> departments=access.managedDepartmentIds(actor);
            Set<String> allowed=memberships.selectList(new QueryWrapper<SysUserDepart>()
                    .in("user_id",ids).in("dep_id",departments)).stream().map(SysUserDepart::getUserId).collect(Collectors.toSet());
            for(String id:ids) if(!id.equals(actor.getId()) && !allowed.contains(id)) throw denied();
        }
        // Complete authorization before constructing any response, including mixed batches.
        return targets.stream().map(user -> UserProfileView.from(user, actor.getId().equals(user.getId()), administrator)).collect(Collectors.toList());
    }

    /** Used only after UserQueryAccessService has constrained the SQL result. */
    public List<UserProfileView> managedViews(List<SysUser> records) {
        SysUser actor=access.currentUser(); boolean administrator=access.isAdministrator(actor);
        return records.stream().map(user -> UserProfileView.from(user, actor.getId().equals(user.getId()), administrator)).collect(Collectors.toList());
    }

    public IPage<UserProfileView> managedPage(IPage<SysUser> records) {
        return new Page<UserProfileView>(records.getCurrent(),records.getSize(),records.getTotal()).setRecords(managedViews(records.getRecords()));
    }
    private UnauthorizedException denied() { return new UnauthorizedException("没有用户资料查询权限"); }
}
