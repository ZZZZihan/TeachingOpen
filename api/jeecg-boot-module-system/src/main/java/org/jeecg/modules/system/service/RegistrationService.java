package org.jeecg.modules.system.service;

import cn.hutool.core.util.RandomUtil;
import com.alibaba.fastjson.JSONObject;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.constant.CommonConstant;
import org.jeecg.common.util.PasswordUtil;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.entity.SysRole;
import org.jeecg.modules.system.entity.SysUser;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.Date;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.regex.Pattern;

@Service
public class RegistrationService {
    private static final Pattern USERNAME = Pattern.compile("^[a-zA-Z0-9_]{4,32}$");
    private static final String SPECIAL = "~!@#$%^&*()_+`-={}:\";'<>?,./";
    private final ISysUserService users;
    private final ISysConfigService config;
    private final ISysRoleService roles;
    private final ISysDepartService departs;
    private final TransactionTemplate transaction;

    public RegistrationService(ISysUserService users, ISysConfigService config, ISysRoleService roles,
                               ISysDepartService departs, PlatformTransactionManager manager) {
        this.users = users; this.config = config; this.roles = roles; this.departs = departs;
        this.transaction = new TransactionTemplate(manager);
    }

    public static String string(JSONObject request, String field) {
        Object value = request == null ? null : request.get(field);
        return value instanceof String ? (String) value : null;
    }

    public static boolean validPassword(String password) {
        if (password == null || password.length() < 8 || password.length() > 64) return false;
        boolean letter = false, digit = false, special = false;
        for (char c : password.toCharArray()) {
            if (c < '!' || c > '~') return false;
            letter |= (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
            digit |= c >= '0' && c <= '9';
            special |= SPECIAL.indexOf(c) >= 0;
        }
        return letter && digit && special;
    }

    private static Result<JSONObject> reply(boolean success, String state, String message) {
        Result<JSONObject> result = new Result<>();
        result.setSuccess(success); result.setCode(success ? 200 : 400); result.setMessage(message);
        JSONObject detail = new JSONObject();
        detail.put("registrationState", state);
        result.setResult(detail);
        return result;
    }
    private static Result<JSONObject> fail(String state, String message) { return reply(false, state, message); }
    private boolean open() { return "1".equals(config.getConfigItem("allowReg")); }

    /** Only server configuration chooses registration relationships. */
    private String defaults(String value, boolean role) {
        if (value == null || value.trim().isEmpty()) return "";
        Set<String> ids = new LinkedHashSet<>();
        for (String raw : value.split(",", -1)) {
            String id = raw.trim();
            if (id.isEmpty()) throw new IllegalArgumentException("Invalid registration default");
            if (role) {
                SysRole configured = roles.getById(id);
                if (configured == null || !id.equals(configured.getId())
                        || "admin".equalsIgnoreCase(configured.getRoleCode()) || "dev".equalsIgnoreCase(configured.getRoleCode())) {
                    throw new IllegalArgumentException("Invalid registration role");
                }
            } else {
                SysDepart configured = departs.getById(id);
                if (configured == null || !id.equals(configured.getId()) || !"0".equals(configured.getDelFlag())
                        || "0".equals(configured.getStatus())) throw new IllegalArgumentException("Invalid registration class");
            }
            ids.add(id);
        }
        return String.join(",", ids);
    }

    public Result<JSONObject> register(JSONObject request) {
        String username = string(request, "username");
        String password = string(request, "password");
        String name = string(request, "realname");
        if (username == null || !USERNAME.matcher(username).matches()) return fail("invalid_username", "账号需为4至32位英文字母、数字或下划线。");
        if (!validPassword(password)) return fail("invalid_password", "密码需为8至64位，包含字母、数字和特殊符号。");
        if (name == null || name.trim().isEmpty() || name.length() > 100 || name.codePoints().anyMatch(c -> c < 32 || c > 65535)) {
            return fail("invalid_realname", "请输入100字以内的姓名。");
        }
        final String roleIds, departIds;
        final SysUser user = new SysUser();
        try {
            if (!open()) return fail("closed", "平台暂未开放注册，请联系教师或管理员。");
            if (users.getUserByName(username) != null) return fail("duplicate", "账号已注册，请直接登录。");
            roleIds = defaults(config.getConfigItem("_defaultRole"), true);
            departIds = defaults(config.getConfigItem("_defaultDepart"), false);
            String salt = RandomUtil.randomString(8);
            String encrypted = PasswordUtil.encrypt(username, password, salt);
            if (encrypted == null || encrypted.isEmpty()) return fail("service_unavailable", "注册服务暂时不可用，请稍后重试。");
            // No model binding: ignore id, status, identity, roles, class and other client fields.
            user.setUsername(username); user.setRealname(name.trim());
            user.setPassword(encrypted); user.setSalt(salt); user.setSchool(""); user.setUserIdentity(1);
            user.setStatus(CommonConstant.USER_UNFREEZE); user.setDelFlag(CommonConstant.DEL_FLAG_0);
            user.setActivitiSync(CommonConstant.ACT_SYNC_0); user.setCreateTime(new Date());
        } catch (IllegalArgumentException e) {
            return fail("invalid_defaults", "平台注册配置不可用，请联系管理员。");
        } catch (RuntimeException e) {
            return fail("service_unavailable", "注册服务暂时不可用，请稍后重试。");
        }
        try {
            // The unique username index arbitrates concurrent registrations.
            // Exceptions escape the callback so role/class failures roll back the account.
            transaction.execute(status -> {
                if (!open()) throw new IllegalStateException("Registration closed");
                if (!users.save(user)) throw new IllegalStateException("Account save failed");
                if (!roleIds.isEmpty()) users.addUserWithRole(user, roleIds);
                if (!departIds.isEmpty()) users.addUserWithDepart(user, departIds);
                return null;
            });
            JSONObject detail = new JSONObject(); detail.put("username", username);
            Result<JSONObject> result = new Result<JSONObject>().success("注册成功，请登录。");
            result.setResult(detail);
            return result;
        } catch (RuntimeException e) {
            return fail("registration_failed", "注册未完成，请稍后重试，或尝试登录确认账号状态。");
        }
    }
}
