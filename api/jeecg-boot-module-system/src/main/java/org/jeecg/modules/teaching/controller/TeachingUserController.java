package org.jeecg.modules.teaching.controller;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import lombok.extern.slf4j.Slf4j;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.constant.CommonConstant;
import org.jeecg.common.system.api.ISysBaseAPI;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.common.controller.BaseController;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.service.ISysDepartService;
import org.jeecg.modules.system.service.ISysUserService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.Date;

@Slf4j
@RequestMapping("/teaching/user")
@RestController
public class TeachingUserController extends BaseController {
    @Autowired private org.jeecg.modules.system.service.UserProfileService userProfiles;

    @Autowired
    private ISysBaseAPI sysBaseAPI;

    @Autowired
    private ISysUserService sysUserService;

    @Autowired
    private ISysDepartService sysDepartService;

    @RequestMapping("/info")
    Result<SysUser> info() {
        Result<SysUser> result = new Result();
        LoginUser loginUser = getCurrentUser();
        SysUser user = sysUserService.getById(loginUser.getId());
        result.setResult(user);
        return result;
    }

    @RequestMapping("getUserRootDept")
    public Result userRootDept(@RequestParam(required = false) String userId){
        Result result = new Result();
        String orgCode = null;
        if (userId == null){
            LoginUser user = getCurrentUser();
            orgCode = user.getOrgCode();
        }else{
            SysUser user = sysUserService.getById(userId);
            orgCode = user.getOrgCode();
        }
        if (orgCode == null){
            result.setSuccess(false);
            result.setMessage("获取不到当前用户的组织机构");
            return result;
        }
//        List<SysDepart> list = sysDepartService.queryUserDeparts(user.getId());
        QueryWrapper<SysDepart> queryWrapper = new QueryWrapper<SysDepart>();
//        String parentCode = orgCode.substring(0, orgCode.length()-3);
        String rootCode = orgCode.substring(0,3);
        queryWrapper.eq("org_code", rootCode);
        SysDepart depart = sysDepartService.getOne(queryWrapper);

        result.setResult(depart);
        return result;
    }

    @RequestMapping(value = "/edit", method = RequestMethod.PUT)
    public Result<SysUser> edit(@RequestBody org.jeecg.modules.system.model.UserProfileRequest request) {
        userProfiles.update(request);
        return new Result<SysUser>().success("修改成功!");
    }

}
