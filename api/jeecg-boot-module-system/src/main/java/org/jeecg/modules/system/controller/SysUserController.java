package org.jeecg.modules.system.controller;


import cn.hutool.core.util.RandomUtil;
import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.lang.StringUtils;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.annotation.Logical;
import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.apache.shiro.authz.annotation.RequiresRoles;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.aspect.annotation.PermissionData;
import org.jeecg.common.constant.CommonConstant;
import org.jeecg.common.system.api.ISysBaseAPI;
import org.jeecg.common.system.query.QueryGenerator;
import org.jeecg.common.system.util.JeecgDataAutorUtils;
import org.jeecg.common.system.util.JwtUtil;
import org.jeecg.common.system.vo.DictModel;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.system.vo.SysPermissionDataRuleModel;
import org.jeecg.common.util.*;
import org.jeecg.modules.common.controller.BaseController;
import org.jeecg.modules.system.entity.*;
import org.jeecg.modules.system.model.DepartIdModel;
import org.jeecg.modules.system.model.UserProfileRequest;
import org.jeecg.modules.system.model.SysUserModel;
import org.jeecg.modules.system.model.SysUserSysDepartModel;
import org.jeecg.modules.system.service.*;
import org.jeecg.modules.system.vo.SysDepartUsersVO;
import org.jeecg.modules.system.vo.SysUserRoleVO;
import org.jeecgframework.poi.excel.ExcelImportUtil;
import org.jeecgframework.poi.excel.def.NormalExcelConstants;
import org.jeecgframework.poi.excel.entity.ExportParams;
import org.jeecgframework.poi.excel.entity.ImportParams;
import org.jeecgframework.poi.excel.view.JeecgEntityExcelView;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;
import org.springframework.web.servlet.ModelAndView;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.File;
import java.io.IOException;
import java.util.*;
import java.util.stream.Collectors;

/**
 * <p>
 * 用户表 前端控制器
 * </p>
 *
 * @Author scott
 * @since 2018-12-20
 */
@Slf4j
@RestController
@RequestMapping("/sys/user")
public class SysUserController extends BaseController {
    @Autowired private AccountAdministrationService accountAdministration;
    @Autowired private UserProfileService userProfiles;
	@Autowired
	private ISysBaseAPI sysBaseAPI;
	@Autowired
	private ISysUserService sysUserService;
    @Autowired
    private ISysDepartService sysDepartService;
	@Autowired
	private ISysUserRoleService sysUserRoleService;
	@Autowired
	private ISysUserDepartService sysUserDepartService;
	@Autowired
	private ISysRoleService sysRoleService;
    @Autowired
    private ISysConfigService sysConfigService;
	@Autowired
	private RedisUtil redisUtil;
	@Autowired
	private PasswordResetService passwordResetService;
    @Autowired
    private AccountRegistrationService accountRegistrationService;

    @Value("${jeecg.path.upload}")
    private String upLoadPath;

    @PermissionData(pageComponent = "system/UserList")
	@RequestMapping(value = "/list", method = RequestMethod.GET)
	public Result<IPage<SysUser>> queryPageList(SysUser user, @RequestParam(name="pageNo", defaultValue="1") Integer pageNo,
                                                @RequestParam(name="pageSize", defaultValue="10") Integer pageSize, HttpServletRequest req) {
		Result<IPage<SysUser>> result = new Result<IPage<SysUser>>();
//		QueryWrapper<SysUserModel> queryWrapper = QueryGenerator.initQueryWrapper(user, req.getParameterMap());
        Map<String, String[]> param = req.getParameterMap();
        String[] areaRaw = param.get("area");
        String provinceId = null;
        String cityId = null;
        if (areaRaw != null && areaRaw.length == 1){
            JSONObject area = JSONObject.parseObject(areaRaw[0]);
            provinceId = area.getString("provinceId");
            cityId = area.getString("cityId");
        }

//        String departName = param.containsKey("departName")?param.get("departName")[0]:null;
        String roleCode = param.containsKey("roleCode")?param.get("roleCode")[0]:null;
        String roleId = param.containsKey("roleId")?param.get("roleId")[0]:null;

        QueryWrapper<SysUser> queryWrapper = new QueryWrapper<>();
        queryWrapper.eq(org.apache.commons.lang3.StringUtils.isNotEmpty(provinceId), "sys_user.province", provinceId);
        queryWrapper.eq(org.apache.commons.lang3.StringUtils.isNotEmpty(cityId),"sys_user.city", cityId);
        queryWrapper.eq("sys_user.del_flag", 0); //过滤已删除用户

        //departId批量查询条件
        String departId = param.containsKey("departId")?param.get("departId")[0]:null;
        if(StringUtils.isNotEmpty(departId)){
            departId = "('" + departId.replaceAll(",", "','") + "')";
            queryWrapper.inSql("sys_user.id","select user_id from sys_user_depart where dep_id in " + departId);
        }
        //roleCode查询条件
        if (StringUtils.isNotEmpty(roleCode) && StringUtils.isEmpty(roleId)){
            SysRole sysRole = sysRoleService.getRoleByCode(roleCode);
            if (sysRole != null)roleId = sysRole.getId();
        }
        //roleId批量查询条件
        if (StringUtils.isNotEmpty(roleId)){
            roleId = "('" + roleId.replaceAll(",", "','") + "')";
            queryWrapper.inSql("sys_user.id","select user_id from sys_user_role where role_id in " + roleId);
        }

        QueryGenerator.installMplus(queryWrapper, user, req.getParameterMap());

        //非admin和dev角色，只显示自己管理的部门下的用户
        List<String> myDeptIds = new ArrayList<>();
        if(!hasRole("admin") && !hasRole("dev")){
            myDeptIds = sysDepartService.getMySubDepIdsByDepId(getCurrentUser().getDepartIds());
            if (myDeptIds==null || myDeptIds.isEmpty()){
                result.error500("您没有负责的班级");
                return result;
            }
            String myDeptIdStr = "('" + String.join("','", myDeptIds) + "')";
            queryWrapper.inSql("sys_user.id","select user_id from sys_user_depart where dep_id in " + myDeptIdStr);
        }

		Page<SysUser> page = new Page<SysUser>(pageNo, pageSize);
        IPage<SysUser> pageList = sysUserService.getUserList(page, queryWrapper);

//		IPage<SysUserModel> pageList = sysUserService.page(page, queryWrapper);

        //批量查询用户的所属部门
        //step.1 先拿到全部的 useids
        //step.2 通过 useids，一次性查询用户的所属部门名字
        List<String> userIds = pageList.getRecords().stream().map(SysUser::getId).collect(Collectors.toList());
        Map<String,String>  useDepNames = sysUserService.getDepNamesByUserIds(userIds);
        Map<String,String>  roleNames = sysUserService.getRoleNamesByUserIds(userIds);
        pageList.getRecords().forEach(item->{
            item.setOrgCodeTxt(useDepNames.get(item.getId()));
            item.setRoleTxt(roleNames.get(item.getId()));
        });
		result.setSuccess(true);
		result.setResult(pageList);
		log.info(pageList.toString());
		return result;
	}

	@RequestMapping(value = "/add", method = RequestMethod.POST)
    //@RequiresPermissions("user:add")
	@RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
	public Result<SysUser> add(@RequestBody JSONObject jsonObject) {
        accountAdministration.saveAccount(JSON.parseObject(jsonObject.toJSONString(), SysUser.class),
                jsonObject.getString("selectedroles"), jsonObject.getString("selecteddeparts"), true);
        return new Result<SysUser>().success("保存成功!");
    }

	@RequestMapping(value = "/edit", method = RequestMethod.PUT)
    //@RequiresRoles({"admin"})
    //@RequiresPermissions("user:edit")
	@RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
	public Result<SysUser> edit(@RequestBody JSONObject jsonObject) {
        accountAdministration.saveAccount(JSON.parseObject(jsonObject.toJSONString(), SysUser.class),
                jsonObject.getString("selectedroles"), jsonObject.getString("selecteddeparts"), false);
        return new Result<SysUser>().success("保存成功!");
    }

	/**
	 * 删除用户
	 */
	//@RequiresRoles({"admin"})
	@RequestMapping(value = "/delete", method = RequestMethod.DELETE)
	@RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
	public Result<?> delete(@RequestParam(name="id",required=true) String id) {
        accountAdministration.deleteAccounts(Collections.singletonList(id));
        return Result.ok("删除用户成功");
    }

	/**
	 * 批量删除用户
	 */
	//@RequiresRoles({"admin"})
	@RequestMapping(value = "/deleteBatch", method = RequestMethod.DELETE)
	@RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
	public Result<?> deleteBatch(@RequestParam(name="ids",required=true) String ids) {
        accountAdministration.deleteAccounts(AccountAdministrationService.ids(ids));
        return Result.ok("批量删除用户成功");
    }

	/**
	  * 冻结&解冻用户
	 * @param jsonObject
	 * @return
	 */
	//@RequiresRoles({"admin"})
	@RequestMapping(value = "/frozenBatch", method = RequestMethod.PUT)
	public Result<SysUser> frozenBatch(@RequestBody JSONObject jsonObject) {
		SecurityUtils.getSubject().checkPermission("user:status");
		Result<SysUser> result = new Result<SysUser>();
		try {
			LoginUser operator = getCurrentUser();
			if (operator == null) {
				return result.error500("权限不足");
			}
			if (jsonObject == null) {
				return result.error500("请求参数不能为空");
			}
			sysUserService.updateUserStatus(jsonObject.getString("ids"),
					jsonObject.getString("status"), operator.getId());
			return result.success("操作成功!");
		} catch (IllegalArgumentException e) {
			return result.error500(e.getMessage());
		} catch (Exception e) {
			log.error("冻结或解冻用户失败", e);
			return result.error500("操作失败");
		}
    }

    @RequestMapping(value = "/queryById", method = RequestMethod.GET)
    public Result<SysUser> queryById(@RequestParam(name = "id", required = true) String id) {
        Result<SysUser> result = new Result<SysUser>();
        SysUser sysUser = sysUserService.getById(id);
        if (sysUser == null) {
            result.error500("未找到对应实体");
        } else {
            result.setResult(sysUser);
            result.setSuccess(true);
        }
        return result;
    }

    @RequestMapping(value = "/queryUserRole", method = RequestMethod.GET)
    public Result<List<String>> queryUserRole(@RequestParam(name = "userid", required = true) String userid) {
        Result<List<String>> result = new Result<>();
        List<String> list = new ArrayList<String>();
        List<SysUserRole> userRole = sysUserRoleService.list(new QueryWrapper<SysUserRole>().lambda().eq(SysUserRole::getUserId, userid));
        if (userRole == null || userRole.size() <= 0) {
            result.error500("未找到用户相关角色信息");
        } else {
            for (SysUserRole sysUserRole : userRole) {
                list.add(sysUserRole.getRoleId());
            }
            result.setSuccess(true);
            result.setResult(list);
        }
        return result;
    }


    /**
	  *  校验用户账号是否唯一<br>
	  *  可以校验其他 需要检验什么就传什么。。。
     *
     * @param sysUser
     * @return
     */
    @RequestMapping(value = "/checkOnlyUser", method = RequestMethod.GET)
    public Result<Boolean> checkOnlyUser(SysUser sysUser) {
        Result<Boolean> result = new Result<>();
        //如果此参数为false则程序发生异常
        result.setResult(true);
        try {
            //通过传入信息查询新的用户信息
            List<SysUser> user = sysUserService.list(new LambdaQueryWrapper<SysUser>()
                    .eq(StringUtils.isNotBlank(sysUser.getPhone()), SysUser::getPhone, sysUser.getPhone())
                    .eq(StringUtils.isNotBlank(sysUser.getEmail()), SysUser::getEmail, sysUser.getEmail())
                    .eq(StringUtils.isNotBlank(sysUser.getUsername()), SysUser::getUsername, sysUser.getUsername()));
            if (user != null && !user.isEmpty()) {
                result.setSuccess(false);
                result.setMessage("用户账号已存在");
                return result;
            }

        } catch (Exception e) {
            result.setSuccess(false);
            result.setMessage(e.getMessage());
            return result;
        }
        result.setSuccess(true);
        return result;
    }

    /**
     * 修改密码
     */
    //@RequiresRoles({"admin"})
    @RequestMapping(value = "/changePassword", method = RequestMethod.PUT)
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    public Result<?> changePassword(@RequestBody SysUser sysUser) {
        accountAdministration.resetPassword(sysUser.getId(), sysUser.getPassword());
        return Result.ok("密码修改成功!");
    }

    /**
     * 查询指定用户和部门关联的数据
     *
     * @param userId
     * @return
     */
    @RequestMapping(value = "/userDepartList", method = RequestMethod.GET)
    public Result<List<DepartIdModel>> getUserDepartsList(@RequestParam(name = "userId", required = true) String userId) {
        Result<List<DepartIdModel>> result = new Result<>();
        try {
            List<DepartIdModel> depIdModelList = this.sysUserDepartService.queryDepartIdsOfUser(userId);
            if (depIdModelList != null && depIdModelList.size() > 0) {
                result.setSuccess(true);
                result.setMessage("查找成功");
                result.setResult(depIdModelList);
            } else {
                result.setSuccess(false);
                result.setMessage("查找失败");
            }
            return result;
        } catch (Exception e) {
        	log.error(e.getMessage(), e);
            result.setSuccess(false);
            result.setMessage("查找过程中出现了异常: " + e.getMessage());
            return result;
        }

    }

    /**
     * 生成在添加用户情况下没有主键的问题,返回给前端,根据该id绑定部门数据
     *
     * @return
     */
    @RequestMapping(value = "/generateUserId", method = RequestMethod.GET)
    public Result<String> generateUserId() {
        Result<String> result = new Result<>();
        System.out.println("我执行了,生成用户ID==============================");
        String userId = UUID.randomUUID().toString().replace("-", "");
        result.setSuccess(true);
        result.setResult(userId);
        return result;
    }

    /**
     * 根据部门id查询用户信息
     *
     * @param id
     * @return
     */
    @RequestMapping(value = "/queryUserByDepId", method = RequestMethod.GET)
    public Result<List<SysUser>> queryUserByDepId(@RequestParam(name = "id", required = true) String id,@RequestParam(name="realname",required=false) String realname) {
        Result<List<SysUser>> result = new Result<>();
        //List<SysUser> userList = sysUserDepartService.queryUserByDepId(id);
        SysDepart sysDepart = sysDepartService.getById(id);
        List<SysUser> userList = sysUserDepartService.queryUserByDepCode(sysDepart.getOrgCode(),realname);

        //批量查询用户的所属部门
        //step.1 先拿到全部的 useids
        //step.2 通过 useids，一次性查询用户的所属部门名字
        List<String> userIds = userList.stream().map(SysUser::getId).collect(Collectors.toList());
        if(userIds!=null && userIds.size()>0){
            Map<String,String>  useDepNames = sysUserService.getDepNamesByUserIds(userIds);
            userList.forEach(item->{
                //TODO 临时借用这个字段用于页面展示
                item.setOrgCode(useDepNames.get(item.getId()));
            });
        }

        try {
            result.setSuccess(true);
            result.setResult(userList);
            return result;
        } catch (Exception e) {
        	log.error(e.getMessage(), e);
            result.setSuccess(false);
            return result;
        }
    }

    /**
     * 导出excel
     *
     * @param request
     */
    @RequestMapping(value = "/exportXls")
    public ModelAndView exportXls(SysUserModel sysUser,HttpServletRequest request) {
        // Step.1 组装查询条件
        Map<String, String[]> param = request.getParameterMap();
        log.info("param:{}", param);
        String roleId = param.containsKey("roleId")?param.get("roleId")[0]:null;
        String departId = param.containsKey("departId")?param.get("departId")[0]:null;
        String userSex = param.containsKey("userSex")?param.get("userSex")[0]:null;
        String status = param.containsKey("userStatus")?param.get("userStatus")[0]:null;

        QueryWrapper<SysUser> queryWrapper = new QueryWrapper<>();
//        queryWrapper.eq(org.apache.commons.lang3.StringUtils.isNotEmpty(provinceId), "sys_user.province", provinceId);
//        queryWrapper.eq(org.apache.commons.lang3.StringUtils.isNotEmpty(cityId),"sys_user.city", cityId);
        queryWrapper.eq(org.apache.commons.lang3.StringUtils.isNotEmpty(roleId), "role_id", roleId);
        queryWrapper.eq(org.apache.commons.lang3.StringUtils.isNotEmpty(userSex), "sys_user.sex", userSex);
        queryWrapper.eq(org.apache.commons.lang3.StringUtils.isNotEmpty(status), "sys_user.status", status);
        if(StringUtils.isNotEmpty(departId)){
            queryWrapper.in("sys_depart.id", Arrays.asList(departId.split(",")));
        }
        //TODO 外部模拟登陆临时账号，列表不显示
        queryWrapper.ne("username","_reserve_user_external");
        queryWrapper.eq("sys_user.del_flag", 0);
        queryWrapper.groupBy("sys_user.id");

        //选中数据
        String selections = request.getParameter("selections");
        if(!oConvertUtils.isEmpty(selections)){
            queryWrapper.in("sys_user.id",selections.split(","));
        }

        //非admin和dev角色，只显示自己管理的部门下的用户
        List<String> myDeptIds = new ArrayList<>();
        if(!hasRole("admin") && !hasRole("dev")){
            myDeptIds = sysDepartService.getMySubDepIdsByDepId(getCurrentUser().getDepartIds());
            if (myDeptIds==null || myDeptIds.isEmpty()){
                return null;
            }
            String myDeptIdStr = "('" + String.join("','", myDeptIds) + "')";
            queryWrapper.inSql("sys_user.id","select user_id from sys_user_depart where dep_id in " + myDeptIdStr);
        }

        QueryGenerator.installMplus(queryWrapper, sysUser, request.getParameterMap());
        Page<SysUser> page = new Page<SysUser>(1, 999);
        IPage<SysUser> pageList = sysUserService.getUserList(page, queryWrapper);

        //批量查询用户的所属部门
        //step.1 先拿到全部的 useids
        //step.2 通过 useids，一次性查询用户的所属部门名字
        List<String> userIds = pageList.getRecords().stream().map(SysUser::getId).collect(Collectors.toList());
        Map<String,String>  useDepNames = sysUserService.getDepNamesByUserIds(userIds);
        Map<String,String>  roleNames = sysUserService.getRoleNamesByUserIds(userIds);
        pageList.getRecords().forEach(item->{
            item.setOrgCodeTxt(useDepNames.get(item.getId()));
            item.setRoleTxt(roleNames.get(item.getId()));
        });

//        QueryWrapper<SysUser> queryWrapper = QueryGenerator.initQueryWrapper(sysUser, request.getParameterMap());
        //Step.2 AutoPoi 导出Excel
        ModelAndView mv = new ModelAndView(new JeecgEntityExcelView());
        //update-begin--Author:kangxiaolin  Date:20180825 for：[03]用户导出，如果选择数据则只导出相关数据--------------------

        //update-end--Author:kangxiaolin  Date:20180825 for：[03]用户导出，如果选择数据则只导出相关数据----------------------
//        List<SysUser> pageList = sysUserService.list(queryWrapper);

        //导出文件名称
        mv.addObject(NormalExcelConstants.FILE_NAME, "用户列表");
        mv.addObject(NormalExcelConstants.CLASS, SysUserModel.class);
        LoginUser user = (LoginUser) SecurityUtils.getSubject().getPrincipal();
        ExportParams exportParams = new ExportParams("用户列表数据", "导出人:"+user.getRealname(), "导出信息");
        exportParams.setImageBasePath(upLoadPath);
        mv.addObject(NormalExcelConstants.PARAMS, exportParams);
        mv.addObject(NormalExcelConstants.DATA_LIST, pageList.getRecords());
        return mv;
    }

    /**
     * 通过excel导入数据
     *
     * @param request
     * @param response
     * @return
     */
    //@RequiresPermissions("user:import")
    @RequestMapping(value = "/importExcel", method = RequestMethod.POST)
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    public Result<?> importExcel(HttpServletRequest request, HttpServletResponse response) {
        return importAccounts(request, null, false);
    }

    @RequestMapping(value = "/importStudent", method = RequestMethod.POST)
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    public Result<?> importStudent(@RequestParam(required = false) String departIds,
                                   HttpServletRequest request, HttpServletResponse response) {
        return importAccounts(request, departIds, true);
    }

    private Result<?> importAccounts(HttpServletRequest request, String departIds, boolean studentOnly) {
        accountAdministration.requireAdministrator();
        MultipartHttpServletRequest multipart = (MultipartHttpServletRequest) request;
        List<String> errors = new ArrayList<>();
        int success = 0, failed = 0;
        for (MultipartFile file : multipart.getFileMap().values()) {
            ImportParams params = new ImportParams();
            params.setTitleRows(2); params.setHeadRows(1); params.setNeedSave(false);
            try (java.io.InputStream input = file.getInputStream()) {
                List<SysUserModel> rows = ExcelImportUtil.importExcel(input, SysUserModel.class, params);
                for (int i = 0; i < rows.size(); i++) {
                    SysUserModel row = rows.get(i);
                    try {
                        accountAdministration.importAccount(row, row.getRoleTxt(),
                                StringUtils.isBlank(departIds) ? row.getOrgCodeTxt() : departIds, studentOnly);
                        success++;
                    } catch (RuntimeException failure) {
                        failed++;
                        errors.add("第 " + (i + 1) + " 行：导入失败，请检查账号、强密码、角色和部门；该行未保存。");
                    }
                }
            } catch (Exception failure) {
                failed++;
                errors.add("文件读取失败，请检查导入模板。");
            }
        }
        JSONObject result = new JSONObject();
        result.put("successCount", success); result.put("errorCount", failed); result.put("errors", errors);
        Result<JSONObject> response = new Result<>();
        response.setResult(result); response.setSuccess(failed == 0);
        response.setMessage("已导入" + success + "行，失败" + failed + "行");
        return response;
    }


    /**
	 * @功能：根据id 批量查询
	 * @param userIds
	 * @return
	 */
	@RequestMapping(value = "/queryByIds", method = RequestMethod.GET)
	public Result<Collection<SysUser>> queryByIds(@RequestParam String userIds) {
		Result<Collection<SysUser>> result = new Result<>();
		String[] userId = userIds.split(",");
		Collection<String> idList = Arrays.asList(userId);
		Collection<SysUser> userRole = sysUserService.listByIds(idList);
		result.setSuccess(true);
		result.setResult(userRole);
		return result;
	}

	/**
	 * 首页用户重置密码
	 */
	//@RequiresRoles({"admin"})
	@RequestMapping(value = "/updatePassword", method = RequestMethod.PUT)
	public Result<?> changPassword(@RequestBody JSONObject json) {
        LoginUser user = getCurrentUser();
        if (user == null || (json.containsKey("username") && !user.getUsername().equals(json.getString("username")))) {
            throw new org.apache.shiro.authz.UnauthorizedException("只能修改本人密码");
        }
        return sysUserService.resetPassword(user.getUsername(), json.getString("oldpassword"),
                json.getString("password"), json.getString("confirmpassword"));
    }

    @RequestMapping(value = "/userRoleList", method = RequestMethod.GET)
    public Result<IPage<SysUser>> userRoleList(@RequestParam(name="pageNo", defaultValue="1") Integer pageNo,
                                               @RequestParam(name="pageSize", defaultValue="10") Integer pageSize, HttpServletRequest req) {
        Result<IPage<SysUser>> result = new Result<IPage<SysUser>>();
        Page<SysUser> page = new Page<SysUser>(pageNo, pageSize);
        String roleId = req.getParameter("roleId");
        String username = req.getParameter("username");
        IPage<SysUser> pageList = sysUserService.getUserByRoleId(page,roleId,username);
        result.setSuccess(true);
        result.setResult(pageList);
        return result;
    }

    /**
     * 给指定角色添加用户
     *
     * @param
     * @return
     */
    //@RequiresRoles({"admin"})
    @RequestMapping(value = "/addSysUserRole", method = RequestMethod.POST)
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    public Result<String> addSysUserRole(@RequestBody SysUserRoleVO sysUserRoleVO) {
        accountAdministration.changeRole(sysUserRoleVO.getRoleId(), sysUserRoleVO.getUserIdList(), true);
        return new Result<String>().success("添加成功!");
    }
    /**
     *   删除指定角色的用户关系
     * @param
     * @return
     */
    //@RequiresRoles({"admin"})
    @RequestMapping(value = "/deleteUserRole", method = RequestMethod.DELETE)
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    public Result<SysUserRole> deleteUserRole(@RequestParam(name="roleId") String roleId,
                                                    @RequestParam(name="userId",required=true) String userId
    ) {
        accountAdministration.changeRole(roleId, Collections.singletonList(userId), false);
        return new Result<SysUserRole>().success("删除成功!");
    }

    /**
     * 批量删除指定角色的用户关系
     *
     * @param
     * @return
     */
    //@RequiresRoles({"admin"})
    @RequestMapping(value = "/deleteUserRoleBatch", method = RequestMethod.DELETE)
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    public Result<SysUserRole> deleteUserRoleBatch(
            @RequestParam(name="roleId") String roleId,
            @RequestParam(name="userIds",required=true) String userIds) {
        accountAdministration.changeRole(roleId, AccountAdministrationService.ids(userIds), false);
        return new Result<SysUserRole>().success("删除成功!");
    }

    /**
     * 部门用户列表
     */
    @PermissionData(pageComponent = "system/DepartList")
    @RequestMapping(value = "/departUserList", method = RequestMethod.GET)
    public Result<IPage<SysUser>> departUserList(SysUser user, @RequestParam(name="pageNo", defaultValue="1") Integer pageNo,
                                                 @RequestParam(name="pageSize", defaultValue="10") Integer pageSize, HttpServletRequest req) {
        Result<IPage<SysUser>> result = new Result<IPage<SysUser>>();
        Page<SysUser> page = new Page<SysUser>(pageNo, pageSize);
        String depId = req.getParameter("depId");
        QueryWrapper<SysUser> queryWrapper = new QueryWrapper<>();
        QueryGenerator.installMplus(queryWrapper, user, req.getParameterMap());

        //根据部门ID查询,当前和下级所有的部门IDS
        List<String> subDepids = new ArrayList<>();
        //部门id为空时，查询我的部门下所有用户
        if(oConvertUtils.isEmpty(depId)){
            LoginUser loginUser = (LoginUser) SecurityUtils.getSubject().getPrincipal();
            int userIdentity = loginUser.getUserIdentity() != null?loginUser.getUserIdentity():CommonConstant.USER_IDENTITY_1;
            if(oConvertUtils.isNotEmpty(userIdentity) && userIdentity == CommonConstant.USER_IDENTITY_2 ){
                subDepids = sysDepartService.getMySubDepIdsByDepId(loginUser.getDepartIds());
            }
        }else{
            subDepids = sysDepartService.getSubDepIdsByDepId(depId);
        }
        if(subDepids != null && subDepids.size()>0){
            String myDeptIdStr = "('" + String.join("','", subDepids) + "')";
            queryWrapper.inSql("sys_user.id","select user_id from sys_user_depart where dep_id in " + myDeptIdStr);
            IPage<SysUser> pageList = sysUserService.getUserList(page,queryWrapper);
            //批量查询用户的所属部门
            //step.1 先拿到全部的 useids
            //step.2 通过 useids，一次性查询用户的所属部门名字
            List<String> userIds = pageList.getRecords().stream().map(SysUser::getId).collect(Collectors.toList());
            if(userIds!=null && userIds.size()>0){
                Map<String, String> useDepNames = sysUserService.getDepNamesByUserIds(userIds);
                pageList.getRecords().forEach(item -> {
                    //批量查询用户的所属部门
                    item.setOrgCode(useDepNames.get(item.getId()));
                });
            }
            result.setSuccess(true);
            result.setResult(pageList);
        }else{
            result.setSuccess(true);
            result.setResult(null);
        }
        return result;
    }


    /**
     * 根据 orgCode 查询用户，包括子部门下的用户
     * 若某个用户包含多个部门，则会显示多条记录，可自行处理成单条记录
     */
    @GetMapping("/queryByOrgCode")
    public Result<?> queryByDepartId(
            @RequestParam(name = "pageNo", defaultValue = "1") Integer pageNo,
            @RequestParam(name = "pageSize", defaultValue = "10") Integer pageSize,
            @RequestParam(name = "orgCode") String orgCode,
            SysUser userParams
    ) {
        IPage<SysUserSysDepartModel> pageList = sysUserService.queryUserByOrgCode(orgCode, userParams, new Page(pageNo, pageSize));
        return Result.ok(pageList);
    }

    /**
     * 根据 orgCode 查询用户，包括子部门下的用户
     * 针对通讯录模块做的接口，将多个部门的用户合并成一条记录，并转成对前端友好的格式
     */
    @GetMapping("/queryByOrgCodeForAddressList")
    public Result<?> queryByOrgCodeForAddressList(
            @RequestParam(name = "pageNo", defaultValue = "1") Integer pageNo,
            @RequestParam(name = "pageSize", defaultValue = "10") Integer pageSize,
            @RequestParam(name = "orgCode",required = false) String orgCode,
            SysUser userParams
    ) {
        IPage page = new Page(pageNo, pageSize);
        IPage<SysUserSysDepartModel> pageList = sysUserService.queryUserByOrgCode(orgCode, userParams, page);
        List<SysUserSysDepartModel> list = pageList.getRecords();

        // 记录所有出现过的 user, key = userId
        Map<String, JSONObject> hasUser = new HashMap<>(list.size());

        JSONArray resultJson = new JSONArray(list.size());

        for (SysUserSysDepartModel item : list) {
            String userId = item.getId();
            // userId
            JSONObject getModel = hasUser.get(userId);
            // 之前已存在过该用户，直接合并数据
            if (getModel != null) {
                String departName = getModel.get("departName").toString();
                getModel.put("departName", (departName + " | " + item.getDepartName()));
            } else {
                // 将用户对象转换为json格式，并将部门信息合并到 json 中
                JSONObject json = JSON.parseObject(JSON.toJSONString(item));
                json.remove("id");
                json.put("userId", userId);
                json.put("departId", item.getDepartId());
                json.put("departName", item.getDepartName());
//                json.put("avatar", item.getSysUser().getAvatar());
                resultJson.add(json);
                hasUser.put(userId, json);
            }
        }

        IPage<JSONObject> result = new Page<>(pageNo, pageSize, pageList.getTotal());
        result.setRecords(resultJson.toJavaList(JSONObject.class));
        return Result.ok(result);
    }

    /**
     * 给指定部门添加对应的用户
     */
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    @RequestMapping(value = "/editSysDepartWithUser", method = RequestMethod.POST)
    public Result<String> editSysDepartWithUser(@RequestBody SysDepartUsersVO sysDepartUsersVO) {
        Result<String> result = new Result<String>();
        sysUserDepartService.addUsersToDepart(sysDepartUsersVO.getDepId(), sysDepartUsersVO.getUserIdList());
        result.setMessage("添加成功!");
        result.setSuccess(true);
        return result;
    }

    /**
     *   删除指定机构的用户关系
     */
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    @RequestMapping(value = "/deleteUserInDepart", method = RequestMethod.DELETE)
    public Result<SysUserDepart> deleteUserInDepart(@RequestParam(name="depId") String depId,
                                                    @RequestParam(name="userId",required=true) String userId
    ) {
        Result<SysUserDepart> result = new Result<SysUserDepart>();
        sysUserDepartService.removeUsersFromDepart(depId, Collections.singletonList(userId));
        result.success("删除成功!");
        return result;
    }

    /**
     * 批量删除指定机构的用户关系
     */
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    @RequestMapping(value = "/deleteUserInDepartBatch", method = RequestMethod.DELETE)
    public Result<SysUserDepart> deleteUserInDepartBatch(
            @RequestParam(name="depId") String depId,
            @RequestParam(name="userIds",required=true) String userIds) {
        Result<SysUserDepart> result = new Result<SysUserDepart>();
        // The existing department UI appends a comma to the final selected ID.
        sysUserDepartService.removeUsersFromDepart(depId, Arrays.asList(userIds.split(",")));
        result.success("删除成功!");
        return result;
    }
    
    /**
         *  查询当前用户的所有部门/当前部门编码
     * @return
     */
    @RequestMapping(value = "/getCurrentUserDeparts", method = RequestMethod.GET)
    public Result<Map<String,Object>> getCurrentUserDeparts() {
        Result<Map<String,Object>> result = new Result<Map<String,Object>>();
        try {
        	LoginUser sysUser = (LoginUser)SecurityUtils.getSubject().getPrincipal();
            List<SysDepart> list = this.sysDepartService.queryUserDeparts(sysUser.getId());
            Map<String,Object> map = new HashMap<String,Object>();
            map.put("list", list);
            map.put("orgCode", sysUser.getOrgCode());
            result.setSuccess(true);
            result.setResult(map);
        }catch(Exception e) {
            log.error(e.getMessage(), e);
            result.error500("查询失败！");
        }
        return result;
    }

    


	/**
	 * 用户注册接口
	 * 
	 * @param jsonObject
	 * @param user
	 * @return
	 */
	@PostMapping("/register")
    public Result<JSONObject> userRegister(@RequestBody JSONObject request) {
        return accountRegistrationService.register(request);
    }

	/**
	 * 根据用户名或手机号查询用户信息
	 * 安全修复: 对返回的手机号进行脱敏处理，防止敏感信息泄露 (CVE-2021-37305)
	 * @param
	 * @return
	 */
	@GetMapping("/querySysUser")
	public Result<Map<String, Object>> querySysUser(SysUser sysUser) {
		String phone = sysUser.getPhone();
		String username = sysUser.getUsername();
		Result<Map<String, Object>> result = new Result<Map<String, Object>>();
		Map<String, Object> map = new HashMap<String, Object>();
		if (oConvertUtils.isNotEmpty(phone)) {
			SysUser user = sysUserService.getUserByPhone(phone);
			if(user!=null) {
				map.put("username",user.getUsername());
				map.put("phone", desensitizePhone(user.getPhone()));
				result.setSuccess(true);
				result.setResult(map);
				return result;
			}
		}
		if (oConvertUtils.isNotEmpty(username)) {
			SysUser user = sysUserService.getUserByName(username);
			if(user!=null) {
				map.put("username",user.getUsername());
				map.put("phone", desensitizePhone(user.getPhone()));
				result.setSuccess(true);
				result.setResult(map);
				return result;
			}
		}
		result.setSuccess(false);
		result.setMessage("验证失败");
		return result;
	}

	/**
	 * 手机号脱敏处理：保留前3位和后4位，中间用****替代
	 * @param phone 原始手机号
	 * @return 脱敏后的手机号
	 */
	private String desensitizePhone(String phone) {
		if (phone != null && phone.length() >= 7) {
			return phone.substring(0, 3) + "****" + phone.substring(phone.length() - 4);
		}
		return phone;
	}
	
	/** Only verifies a recovery code; never extends its TTL or returns it. */
	@PostMapping("/phoneVerification")
	public Result<String> phoneVerification(@RequestBody JSONObject jsonObject) {
		return passwordResetService.verify(jsonObject);
	}

	/** Passwords and codes must be supplied in a JSON body, never a GET query. */
	@PostMapping("/passwordChange")
	public Result<String> passwordChange(@RequestBody JSONObject jsonObject) {
		return passwordResetService.reset(jsonObject);
	}
	

	/**
	 * 根据TOKEN获取用户的部分信息（返回的数据是可供表单设计器使用的数据）
	 * 
	 * @return
	 */
	@GetMapping("/getUserSectionInfoByToken")
	public Result<?> getUserSectionInfoByToken(HttpServletRequest request, @RequestParam(name = "token", required = false) String token) {
		try {
			String username = null;
			// 如果没有传递token，就从header中获取token并获取用户信息
			if (oConvertUtils.isEmpty(token)) {
				 username = JwtUtil.getUserNameByToken(request);
			} else {
				 username = JwtUtil.getUsername(token);				
			}

			log.info(" ------ 通过令牌获取部分用户信息，当前用户： " + username);

			// 根据用户名查询用户信息
			SysUser sysUser = sysUserService.getUserByName(username);
			Map<String, Object> map = new HashMap<String, Object>();
			map.put("sysUserId", sysUser.getId());
			map.put("sysUserCode", sysUser.getUsername()); // 当前登录用户登录账号
			map.put("sysUserName", sysUser.getRealname()); // 当前登录用户真实名称
			map.put("sysOrgCode", sysUser.getOrgCode()); // 当前登录用户部门编号

			log.info(" ------ 通过令牌获取部分用户信息，已获取的用户信息： " + map);

			return Result.ok(map);
		} catch (Exception e) {
			log.error(e.getMessage(), e);
			return Result.error(500, "查询失败:" + e.getMessage());
		}
	}
	
	/**
	 * 【APP端接口】获取用户列表  根据用户名和真实名 模糊匹配
	 * @param keyword
	 * @param pageNo
	 * @param pageSize
	 * @return
	 */
	@GetMapping("/appUserList")
	public Result<?> appUserList(@RequestParam(name = "keyword", required = false) String keyword,
            @RequestParam(name = "username", required = false) String username,
			@RequestParam(name="pageNo", defaultValue="1") Integer pageNo,
			@RequestParam(name="pageSize", defaultValue="10") Integer pageSize) {
		try {
			//TODO 从查询效率上将不要用mp的封装的page分页查询 建议自己写分页语句
			LambdaQueryWrapper<SysUser> query = new LambdaQueryWrapper<SysUser>();
			query.eq(SysUser::getActivitiSync, "1");
			query.eq(SysUser::getDelFlag,"0");
			if(oConvertUtils.isNotEmpty(username)){
			    query.eq(SysUser::getUsername,username);
            }else{
                query.and(i -> i.like(SysUser::getUsername, keyword).or().like(SysUser::getRealname, keyword));
            }
			Page<SysUser> page = new Page<>(pageNo, pageSize);
			IPage<SysUser> res = this.sysUserService.page(page, query);
			return Result.ok(res);
		} catch (Exception e) {
			log.error(e.getMessage(), e);
			return Result.error(500, "查询失败:" + e.getMessage());
		}
		
	}

    /**
     * 获取被逻辑删除的用户列表，无分页
     *
     * @return logicDeletedUserList
     */
    @GetMapping("/recycleBin")
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    public Result getRecycleBin() {
        accountAdministration.requireAdministrator();
        List<SysUser> logicDeletedUserList = sysUserService.queryLogicDeleted();
        if (logicDeletedUserList.size() > 0) {
            // 批量查询用户的所属部门
            // step.1 先拿到全部的 userIds
            List<String> userIds = logicDeletedUserList.stream().map(SysUser::getId).collect(Collectors.toList());
            // step.2 通过 userIds，一次性查询用户的所属部门名字
            Map<String, String> useDepNames = sysUserService.getDepNamesByUserIds(userIds);
            logicDeletedUserList.forEach(item -> item.setOrgCode(useDepNames.get(item.getId())));
        }
        return Result.ok(logicDeletedUserList);
    }

    /**
     * 还原被逻辑删除的用户
     *
     * @param jsonObject
     * @return
     */
    @RequestMapping(value = "/putRecycleBin", method = RequestMethod.PUT)
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    public Result putRecycleBin(@RequestBody JSONObject jsonObject, HttpServletRequest request) {
        accountAdministration.recycle(AccountAdministrationService.ids(jsonObject.getString("userIds")), true);
        return Result.ok("还原成功");
    }

    /**
     * 彻底删除用户
     *
     * @param userIds 被删除的用户ID，多个id用半角逗号分割
     * @return
     */
    @RequestMapping(value = "/deleteRecycleBin", method = RequestMethod.DELETE)
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    public Result deleteRecycleBin(@RequestParam("userIds") String userIds) {
        accountAdministration.recycle(AccountAdministrationService.ids(userIds), false);
        return Result.ok("删除成功");
    }


    /**
     * 移动端修改用户信息
     * @param jsonObject
     * @return
     */
    @RequestMapping(value = "/appEdit", method = RequestMethod.PUT)
    public Result<SysUser> appEdit(@RequestBody UserProfileRequest request) {
        userProfiles.update(request);
        return new Result<SysUser>().success("修改成功!");
    }

}
