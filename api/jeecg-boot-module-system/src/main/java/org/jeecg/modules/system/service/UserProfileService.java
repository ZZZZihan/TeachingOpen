package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.constant.CacheConstant;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.model.UserProfileRequest;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserProfileService {
    private final SysUserMapper users;
    public UserProfileService(SysUserMapper users) { this.users = users; }

    @Transactional(rollbackFor = Exception.class)
    @CacheEvict(value = CacheConstant.SYS_USERS_CACHE, allEntries = true)
    public void update(UserProfileRequest request) {
        Object principal = SecurityUtils.getSubject().getPrincipal();
        if (!(principal instanceof LoginUser)) throw new UnauthorizedException("请先登录");
        LoginUser user = (LoginUser) principal;
        if (request == null || (request.getId() != null && !user.getId().equals(request.getId()))) {
            throw new UnauthorizedException("只能修改本人的资料");
        }
        if (request.getRealname() == null || request.getRealname().trim().isEmpty()
                || request.getRealname().length() > 100
                || (request.getSex() != null && request.getSex() != 1 && request.getSex() != 2)
                || (request.getEmail() != null && request.getEmail().length() > 100)
                || (request.getAvatar() != null && request.getAvatar().length() > 255)) {
            throw new JeecgBootException("个人资料格式不正确");
        }
        LambdaUpdateWrapper<SysUser> patch = new LambdaUpdateWrapper<SysUser>()
                .eq(SysUser::getId, user.getId()).eq(SysUser::getDelFlag, 0)
                .set(SysUser::getRealname, request.getRealname().trim())
                .set(SysUser::getAvatar, request.getAvatar()).set(SysUser::getEmail, request.getEmail())
                .set(SysUser::getSex, request.getSex()).set(SysUser::getBirthday, request.getBirthday());
        if (users.update(null, patch) != 1) throw new JeecgBootException("个人资料未保存");
    }
}
