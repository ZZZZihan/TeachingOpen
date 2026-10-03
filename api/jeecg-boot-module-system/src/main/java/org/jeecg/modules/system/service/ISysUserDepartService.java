package org.jeecg.modules.system.service;


import java.util.List;

import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.entity.SysUserDepart;
import org.jeecg.modules.system.model.DepartIdModel;


import com.baomidou.mybatisplus.extension.service.IService;

/**
 * <p>
 * SysUserDpeart用户组织机构service
 * </p>
 * @Author ZhiLin
 *
 */
public interface ISysUserDepartService extends IService<SysUserDepart> {

	/**
	 * 管理员添加已有用户到指定部门，全部目标有效后统一写入；已有关系保持幂等。
	 */
	void addUsersToDepart(String depId, List<String> userIds);

	/**
	 * 管理员移除指定部门的用户关系及这些用户在该部门的角色关系。
	 */
	void removeUsersFromDepart(String depId, List<String> userIds);

	/**
	 * 管理员清空指定部门的成员，沿用单删/批删的用户角色等级约束。
	 */
	void clearDepartUsers(String depId);
	

	/**
	 * 根据指定用户id查询部门信息
	 * @param userId
	 * @return
	 */
	List<DepartIdModel> queryDepartIdsOfUser(String userId);

	//用户所属的部门id
	List<String> userDepartIds(String userId);
	

	/**
	 * 根据部门id查询用户信息
	 * @param depId
	 * @return
	 */
	List<SysUser> queryUserByDepId(String depId);
  	/**
	 * 根据部门code，查询当前部门和下级部门的用户信息
	 */
	public List<SysUser> queryUserByDepCode(String depCode,String realname);
}
