package org.jeecg.modules.system.service;

import cn.hutool.core.util.RandomUtil;
import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.constant.CommonConstant;
import org.jeecg.common.util.PasswordUtil;
import org.jeecg.modules.system.entity.SysUser;
import org.springframework.stereotype.Service;

import java.util.UUID;
import java.util.regex.Pattern;

/** Bounded anonymous password recovery workflow. No passwords or codes are logged. */
@Service
public class PasswordResetService {
    private static final Pattern PHONE = Pattern.compile("^1[3-9][0-9]{9}$");
    private static final Pattern CODE = Pattern.compile("^[0-9]{6}$");
    private static final String SPECIAL = "~!@#$%^&*()_+`-={}:\";'<>?,./";
    private final ISysUserService users;
    private final PasswordResetCodeStore codes;
    private final PasswordResetSmsSender sender;

    public PasswordResetService(ISysUserService users, PasswordResetCodeStore codes, PasswordResetSmsSender sender) {
        this.users = users;
        this.codes = codes;
        this.sender = sender;
    }

    /** Unlike JSONObject.getString(), rejects arrays/numbers/objects instead of coercing them. */
    public static String string(JSONObject request, String field) {
        Object value = request == null ? null : request.get(field);
        return value instanceof String ? (String) value : null;
    }

    public static boolean validPassword(String password) {
        if (password == null || password.length() < 8 || password.length() > 64) return false;
        boolean letter = false, digit = false, special = false;
        for (int i = 0; i < password.length(); i++) {
            char c = password.charAt(i);
            // Legacy PasswordUtil uses the password as a PBE key and only
            // supports printable ASCII. Reject unsupported input before consume.
            if (c < '!' || c > '~') return false;
            letter |= (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
            digit |= c >= '0' && c <= '9';
            special |= SPECIAL.indexOf(c) >= 0;
        }
        return letter && digit && special;
    }

    private SysUser boundUser(String username, String phone) {
        if (username == null || username.trim().isEmpty() || username.length() > 100
                || phone == null || !PHONE.matcher(phone).matches()) return null;
        SysUser user = users.getOne(new LambdaQueryWrapper<SysUser>()
                .eq(SysUser::getUsername, username).eq(SysUser::getPhone, phone));
        if (user == null || !CommonConstant.USER_UNFREEZE.equals(user.getStatus())
                || !CommonConstant.DEL_FLAG_0.equals(user.getDelFlag())) return null;
        return user;
    }

    private static Result<String> failure(int code, String message) {
        return failure(code, message, null);
    }

    private static Result<String> failure(int code, String message, String recoveryState) {
        Result<String> result = new RecoveryResult(recoveryState);
        result.setSuccess(false);
        result.setCode(code);
        result.setMessage(message);
        return result;
    }

    /** Stable public state for the recovery UI; never contains an OTP or credential. */
    public static final class RecoveryResult extends Result<String> {
        private final String recoveryState;
        RecoveryResult(String recoveryState) { this.recoveryState = recoveryState; }
        public String getRecoveryState() { return recoveryState; }
    }

    public Result<String> sendCode(String username, String phone) {
        final SysUser user;
        final String reservation = "pending:" + UUID.randomUUID();
        try {
            user = boundUser(username, phone);
            if (user == null) return failure(400, "账号与手机号不匹配或账号不可用！");
            if (!codes.reserve(user.getId(), phone, reservation)) return failure(400, "验证码仍有效或正在发送，请使用现有验证码或稍后重试！", "code_active");
        } catch (RuntimeException e) {
            return failure(500, "验证码服务暂时不可用，请稍后重试！");
        }
        try {
            String code = RandomUtil.randomNumbers(6);
            if (!sender.send(phone, code)) {
                codes.consume(user.getId(), phone, reservation);
                return failure(500, "短信验证码发送失败，请稍后重新获取！");
            }
            if (!codes.publish(user.getId(), phone, reservation, code)) {
                return failure(500, "短信已发送但验证码保存失败，请重新获取验证码！");
            }
            return new Result<String>().success("验证码已发送，10分钟内有效！");
        } catch (Exception e) {
            // Provider/cache exceptions may contain phone numbers, template
            // parameters or credentials. Return a fixed response without logging.
            try { codes.consume(user.getId(), phone, reservation); } catch (RuntimeException ignored) { }
            return failure(500, "短信验证码发送或保存失败，请稍后重新获取！");
        }
    }

    public Result<String> verify(JSONObject request) {
        String username = string(request, "username"), phone = string(request, "phone"), code = string(request, "smscode");
        if (code == null || !CODE.matcher(code).matches()) return failure(400, "请输入6位短信验证码！");
        try {
            SysUser user = boundUser(username, phone);
            if (user == null) return failure(400, "账号与手机号不匹配或账号不可用！");
            if (!codes.matches(user.getId(), phone, code)) return failure(400, "短信验证码错误、已使用或已失效，请重新获取！");
            return new Result<String>().success("手机号验证成功！");
        } catch (RuntimeException e) {
            return failure(500, "验证码服务暂时不可用，请稍后重试！");
        }
    }

    public Result<String> reset(JSONObject request) {
        String username = string(request, "username"), phone = string(request, "phone"), code = string(request, "smscode");
        String password = string(request, "password");
        if (!validPassword(password)) return failure(400, "密码须为8至64位非空白ASCII字符，并包含字母、数字和特殊符号！");
        if (code == null || !CODE.matcher(code).matches()) return failure(400, "请输入6位短信验证码！");
        final SysUser user;
        final String salt = RandomUtil.randomString(8);
        final String encrypted;
        try {
            user = boundUser(username, phone);
            if (user == null) return failure(400, "账号与手机号不匹配或账号不可用！");
            encrypted = PasswordUtil.encrypt(user.getUsername(), password, salt);
            if (encrypted == null || encrypted.isEmpty()) return failure(500, "密码处理失败，请重新输入密码！");
            if (!codes.consume(user.getId(), phone, code)) return failure(400, "短信验证码错误、已使用或已失效，请重新获取！");
        } catch (RuntimeException e) {
            return failure(500, "验证码服务暂时不可用，状态不确定，请重新获取验证码！", "reset_unknown");
        }
        try {
            // Do not write an earlier full user snapshot back. The conditions
            // recheck binding/state against concurrent edits at UPDATE time.
            boolean updated = users.update(new SysUser().setPassword(encrypted).setSalt(salt),
                    new LambdaUpdateWrapper<SysUser>().eq(SysUser::getId, user.getId())
                            .eq(SysUser::getUsername, username).eq(SysUser::getPhone, phone)
                            .eq(SysUser::getStatus, CommonConstant.USER_UNFREEZE)
                            .eq(SysUser::getDelFlag, CommonConstant.DEL_FLAG_0));
            if (!updated) return failure(500, "密码重置失败，验证码已使用，请重新获取验证码！", "code_consumed");
        } catch (RuntimeException e) {
            return failure(500, "密码重置结果不确定，验证码已使用，请重新获取验证码或使用新密码登录！", "reset_unknown");
        }
        try {
            codes.clearUserCaches(user.getId(), user.getUsername());
        } catch (RuntimeException e) {
            return failure(500, "密码已重置，但登录状态清理失败，请使用新密码登录或重新获取验证码重试！", "reset_committed");
        }
        return new Result<String>().success("密码重置完成，请使用新密码登录！");
    }
}
