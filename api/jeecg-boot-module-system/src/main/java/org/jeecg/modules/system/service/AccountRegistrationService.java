package org.jeecg.modules.system.service;

import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.constant.CommonConstant;
import org.jeecg.common.util.PasswordUtil;
import org.jeecg.common.util.oConvertUtils;
import org.jeecg.modules.system.entity.SysRole;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.RegistrationProfileMapper;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.PlatformTransactionManager;

import java.util.Date;
import java.util.regex.Pattern;

/** Anonymous registration has an explicit input allowlist and never grants teacher privileges. */
@Service
public class AccountRegistrationService {
    private static final Pattern PHONE = Pattern.compile("^1[3-9][0-9]{9}$");
    private final ISysUserService users;
    private final ISysRoleService roles;
    private final ISysConfigService config;
    private final RegistrationProfileMapper profiles;
    private final TransactionTemplate transactions;

    public AccountRegistrationService(ISysUserService users, ISysRoleService roles,
            ISysConfigService config, RegistrationProfileMapper profiles, PlatformTransactionManager transactionManager) {
        this.users = users; this.roles = roles; this.config = config;
        this.profiles = profiles; this.transactions = new TransactionTemplate(transactionManager);
    }

    private static String text(JSONObject request, String field) {
        String value = PasswordResetService.string(request, field);
        return value == null ? null : value.trim();
    }
    private static boolean validText(String value, int maximum) {
        if (value == null || value.isEmpty() || value.length() > maximum) return false;
        for (int i = 0; i < value.length(); i++) if (Character.isISOControl(value.charAt(i))) return false;
        return true;
    }
    private static Result<JSONObject> failure(int code, String message) {
        Result<JSONObject> result = new Result<>();
        result.setSuccess(false); result.setCode(code); result.setMessage(message); return result;
    }

    public Result<JSONObject> register(JSONObject request) {
        String phone = text(request, "phone"), name = text(request, "realname"), school = text(request, "school");
        String identity = PasswordResetService.string(request, "identity");
        String password = PasswordResetService.string(request, "password");
        if (phone == null || !PHONE.matcher(phone).matches()) return failure(400, "请输入正确的11位手机号");
        if (!validText(name, 100)) return failure(400, "请填写姓名，最多100个字符");
        if (!validText(school, 256)) return failure(400, "请填写学校，最多256个字符");
        if (!"student".equals(identity) && !"teacher".equals(identity)) return failure(400, "请选择教师或学生身份");
        if (!PasswordResetService.validPassword(password)) return failure(400, "密码须为8至64位非空白ASCII字符，并包含字母、数字和特殊符号");
        try {
            if (!"1".equals(config.getConfigItem("allowReg"))) return failure(403, "未开放注册");
            if (profiles.countReservedPhone(phone) != 0) return failure(409, "该手机号已注册或已被账号使用");
            SysRole role = roles.getOne(new LambdaQueryWrapper<SysRole>().eq(SysRole::getRoleCode, "student"));
            if (role == null) return failure(503, "注册服务暂时不可用，请联系管理员");
            transactions.execute(status -> {
                // Do not bind SysUser from HTTP parameters: every security field is server-owned.
                SysUser user = new SysUser();
                String salt = oConvertUtils.randomGen(8);
                user.setUsername(phone).setPhone(phone).setRealname(name).setSchool(school)
                    .setSalt(salt).setPassword(PasswordUtil.encrypt(phone, password, salt))
                    .setUserIdentity(1).setDepartIds("").setStatus(CommonConstant.USER_UNFREEZE)
                    .setDelFlag(CommonConstant.DEL_FLAG_0).setActivitiSync(CommonConstant.ACT_SYNC_0)
                    .setCreateTime(new Date());
                if (!users.save(user)) throw new IllegalStateException("Registration save failed");
                if (profiles.insertProfile(user.getId(), identity) != 1) throw new IllegalStateException("Registration profile failed");
                users.addUserWithRole(user, role.getId());
                return null;
            });
            return new Result<JSONObject>().success("注册成功，请使用手机号和密码登录");
        } catch (DuplicateKeyException e) {
            return failure(409, "该手机号已注册或已被账号使用");
        } catch (RuntimeException e) {
            // Database exceptions can contain private values. Do not log them or return their text.
            return failure(503, "注册服务暂时不可用，请稍后重试");
        }
    }
}
