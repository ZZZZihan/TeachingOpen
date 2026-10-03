package org.jeecg.modules.system.service.impl;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.apache.shiro.subject.Subject;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.oConvertUtils;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.entity.SysDepartRole;
import org.jeecg.modules.system.entity.SysDepartRoleUser;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.entity.SysUserDepart;
import org.jeecg.modules.system.mapper.SysUserDepartMapper;
import org.jeecg.modules.system.mapper.SysDepartRoleMapper;
import org.jeecg.modules.system.mapper.SysDepartRoleUserMapper;
import org.jeecg.modules.system.model.DepartIdModel;
import org.jeecg.modules.system.service.ISysDepartService;
import org.jeecg.modules.system.service.ISysUserDepartService;
import org.jeecg.modules.system.service.ISysUserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;

/**
 * <P>
 * 用户部门表实现类
 * <p/>
 * @Author ZhiLin
 *@since 2019-02-22
 */
@Service
public class SysUserDepartServiceImpl extends ServiceImpl<SysUserDepartMapper, SysUserDepart> implements ISysUserDepartService {
	@Autowired
	private ISysDepartService sysDepartService;
	@Autowired
	private ISysUserService sysUserService;
	@Autowired
	private SysDepartRoleMapper sysDepartRoleMapper;
	@Autowired
	private SysDepartRoleUserMapper sysDepartRoleUserMapper;

	@Override
	@Transactional(rollbackFor = Exception.class)
	public void addUsersToDepart(String depId, List<String> userIds) {
		try {
			requireMembershipAdministrator();
			String targetDepartId = lockDepart(depId);
			Set<String> targetUserIds = requireUserIds(userIds);
			lockUsers(targetUserIds);
			Set<String> existingUserIds = list(new LambdaQueryWrapper<SysUserDepart>()
					.eq(SysUserDepart::getDepId, targetDepartId).in(SysUserDepart::getUserId, targetUserIds)
					.last("FOR UPDATE")).stream().map(SysUserDepart::getUserId).collect(Collectors.toSet());
			for (String userId : targetUserIds) {
				if (!existingUserIds.contains(userId)
						&& baseMapper.insert(new SysUserDepart(null, userId, targetDepartId)) != 1) {
					throw new JeecgBootException("添加用户部门关系失败");
				}
			}
		} catch (DataAccessException e) {
			throw new JeecgBootException("添加用户部门关系失败", e);
		}
	}

	@Override
	@Transactional(rollbackFor = Exception.class)
	public void removeUsersFromDepart(String depId, List<String> userIds) {
		try {
			LoginUser operator = requireMembershipAdministrator();
			String targetDepartId = lockDepart(depId);
			Set<String> targetUserIds = requireUserIds(userIds);
			lockUsers(targetUserIds);
			List<SysUserDepart> members = list(new LambdaQueryWrapper<SysUserDepart>()
					.eq(SysUserDepart::getDepId, targetDepartId).in(SysUserDepart::getUserId, targetUserIds)
					.last("FOR UPDATE"));
			Set<String> memberUserIds = members.stream().map(SysUserDepart::getUserId).collect(Collectors.toSet());
			if (!memberUserIds.equals(targetUserIds)) {
				throw new JeecgBootException("当前选中部门与用户无关联关系!");
			}
			requireRemovalRoleLevel(operator, targetUserIds);
			removeMembersAndDepartRoles(targetDepartId, targetUserIds, members.size());
		} catch (DataAccessException e) {
			throw new JeecgBootException("删除用户部门关系失败", e);
		}
	}

	@Override
	@Transactional(rollbackFor = Exception.class)
	public void clearDepartUsers(String depId) {
		try {
			LoginUser operator = requireMembershipAdministrator();
			String targetDepartId = lockDepart(depId);
			List<SysUserDepart> members = list(new LambdaQueryWrapper<SysUserDepart>()
					.eq(SysUserDepart::getDepId, targetDepartId).last("FOR UPDATE"));
			if (members.isEmpty()) {
				return;
			}
			Set<String> targetUserIds = requireUserIds(members.stream()
					.map(SysUserDepart::getUserId).collect(Collectors.toList()));
			lockUsers(targetUserIds);
			requireRemovalRoleLevel(operator, targetUserIds);
			removeMembersAndDepartRoles(targetDepartId, targetUserIds, members.size());
		} catch (DataAccessException e) {
			throw new JeecgBootException("清空部门成员失败", e);
		}
	}

	private LoginUser requireMembershipAdministrator() {
		Subject subject = SecurityUtils.getSubject();
		if (!(subject.getPrincipal() instanceof LoginUser)
				|| (!subject.hasRole("admin") && !subject.hasRole("dev"))) {
			throw new UnauthorizedException("没有班级成员管理权限");
		}
		return (LoginUser) subject.getPrincipal();
	}

	private String lockDepart(String depId) {
		if (depId == null || depId.trim().isEmpty()) {
			throw new JeecgBootException("请选择要操作的部门");
		}
		String targetDepartId = depId.trim();
		// Serialize these membership operations for the same exact department.
		SysDepart depart = sysDepartService.getOne(new LambdaQueryWrapper<SysDepart>()
				.eq(SysDepart::getId, targetDepartId).last("FOR UPDATE"));
		if (depart == null || !targetDepartId.equals(depart.getId()) || !"0".equals(depart.getDelFlag())) {
			throw new JeecgBootException("未找到对应部门");
		}
		return targetDepartId;
	}

	private Set<String> requireUserIds(List<String> userIds) {
		if (userIds == null || userIds.isEmpty()) {
			throw new JeecgBootException("请选择要操作的用户");
		}
		Set<String> targetUserIds = new TreeSet<>();
		for (String userId : userIds) {
			if (userId == null || userId.trim().isEmpty()) {
				throw new JeecgBootException("用户ID不能为空");
			}
			targetUserIds.add(userId.trim());
		}
		return targetUserIds;
	}

	private void lockUsers(Set<String> userIds) {
		// SysUser's logical-delete filter excludes deleted accounts.
		List<SysUser> users = sysUserService.list(new LambdaQueryWrapper<SysUser>()
				.in(SysUser::getId, userIds).orderByAsc(SysUser::getId).last("FOR UPDATE"));
		Set<String> existingUserIds = users.stream().map(SysUser::getId).collect(Collectors.toSet());
		// Do not persist an ID alias accepted only by a case-insensitive SQL collation.
		if (!existingUserIds.equals(userIds)) {
			throw new JeecgBootException("未找到全部目标用户");
		}
	}

	private void requireRemovalRoleLevel(LoginUser operator, Set<String> userIds) {
		int operatorLevel = sysUserService.getUserRoleLevel(operator.getId());
		for (String userId : userIds) {
			if (operatorLevel < sysUserService.getUserRoleLevel(userId)) {
				throw new UnauthorizedException("权限不足");
			}
		}
	}

	private void removeMembersAndDepartRoles(String depId, Set<String> userIds, int expectedMembers) {
		int removed = baseMapper.delete(new LambdaQueryWrapper<SysUserDepart>()
				.eq(SysUserDepart::getDepId, depId).in(SysUserDepart::getUserId, userIds));
		if (removed != expectedMembers) {
			throw new JeecgBootException("删除用户部门关系失败");
		}
		List<String> roleIds = sysDepartRoleMapper.selectList(new LambdaQueryWrapper<SysDepartRole>()
				.eq(SysDepartRole::getDepartId, depId).last("FOR UPDATE"))
				.stream().map(SysDepartRole::getId).collect(Collectors.toList());
		if (!roleIds.isEmpty()) {
			sysDepartRoleUserMapper.delete(new LambdaQueryWrapper<SysDepartRoleUser>()
					.in(SysDepartRoleUser::getUserId, userIds).in(SysDepartRoleUser::getDroleId, roleIds));
		}
	}
	

	/**
	 * 根据用户id查询部门信息
	 */
	@Override
	public List<DepartIdModel> queryDepartIdsOfUser(String userId) {
		LambdaQueryWrapper<SysUserDepart> queryUDep = new LambdaQueryWrapper<SysUserDepart>();
		LambdaQueryWrapper<SysDepart> queryDep = new LambdaQueryWrapper<SysDepart>();
		try {
			queryUDep.eq(SysUserDepart::getUserId, userId);
			List<String> depIdList = new ArrayList<>();
			List<DepartIdModel> depIdModelList = new ArrayList<>();
			List<SysUserDepart> userDepList = this.list(queryUDep);
			if(userDepList != null && userDepList.size() > 0) {
			for(SysUserDepart userDepart : userDepList) {
					depIdList.add(userDepart.getDepId());
				}
			queryDep.in(SysDepart::getId, depIdList);
			List<SysDepart> depList = sysDepartService.list(queryDep);
			if(depList != null || depList.size() > 0) {
				for(SysDepart depart : depList) {
					depIdModelList.add(new DepartIdModel().convertByUserDepart(depart));
				}
			}
			return depIdModelList;
			}
		}catch(Exception e) {
			e.fillInStackTrace();
		}
		return null;
		
		
	}

    @Override
    public List<String> userDepartIds(String userId) {
		List<SysUserDepart> sysUserDeparts = this.list(new QueryWrapper<SysUserDepart>().lambda().eq(SysUserDepart::getUserId, userId));
		List<String> departIds = new ArrayList<>();
		if (!sysUserDeparts.isEmpty()){
			departIds = sysUserDeparts.stream().map(SysUserDepart::getDepId).collect(Collectors.toList());
		}
        return departIds;
    }


    /**
	 * 根据部门id查询用户信息
	 */
	@Override
	public List<SysUser> queryUserByDepId(String depId) {
		LambdaQueryWrapper<SysUserDepart> queryUDep = new LambdaQueryWrapper<SysUserDepart>();
		queryUDep.eq(SysUserDepart::getDepId, depId);
		List<String> userIdList = new ArrayList<>();
		List<SysUserDepart> uDepList = this.list(queryUDep);
		if(uDepList != null && uDepList.size() > 0) {
			for(SysUserDepart uDep : uDepList) {
				userIdList.add(uDep.getUserId());
			}
			List<SysUser> userList = (List<SysUser>) sysUserService.listByIds(userIdList);
			//update-begin-author:taoyan date:201905047 for:接口调用查询返回结果不能返回密码相关信息
			for (SysUser sysUser : userList) {
				sysUser.setSalt("");
				sysUser.setPassword("");
			}
			//update-end-author:taoyan date:201905047 for:接口调用查询返回结果不能返回密码相关信息
			return userList;
		}
		return new ArrayList<SysUser>();
	}

	/**
	 * 根据部门code，查询当前部门和下级部门的 用户信息
	 */
	@Override
	public List<SysUser> queryUserByDepCode(String depCode,String realname) {
		LambdaQueryWrapper<SysDepart> queryByDepCode = new LambdaQueryWrapper<SysDepart>();
		queryByDepCode.likeRight(SysDepart::getOrgCode,depCode);
		List<SysDepart> sysDepartList = sysDepartService.list(queryByDepCode);
		List<String> depIds = sysDepartList.stream().map(SysDepart::getId).collect(Collectors.toList());

		LambdaQueryWrapper<SysUserDepart> queryUDep = new LambdaQueryWrapper<SysUserDepart>();
		queryUDep.in(SysUserDepart::getDepId, depIds);
		List<String> userIdList = new ArrayList<>();
		List<SysUserDepart> uDepList = this.list(queryUDep);
		if(uDepList != null && uDepList.size() > 0) {
			for(SysUserDepart uDep : uDepList) {
				userIdList.add(uDep.getUserId());
			}
			LambdaQueryWrapper<SysUser> queryUser = new LambdaQueryWrapper<SysUser>();
			queryUser.in(SysUser::getId,userIdList);
			if(oConvertUtils.isNotEmpty(realname)){
				queryUser.like(SysUser::getRealname,realname.trim());
			}
			List<SysUser> userList = (List<SysUser>) sysUserService.list(queryUser);
			//update-begin-author:taoyan date:201905047 for:接口调用查询返回结果不能返回密码相关信息
			for (SysUser sysUser : userList) {
				sysUser.setSalt("");
				sysUser.setPassword("");
			}
			//update-end-author:taoyan date:201905047 for:接口调用查询返回结果不能返回密码相关信息
			return userList;
		}
		return new ArrayList<SysUser>();
	}
	
}
