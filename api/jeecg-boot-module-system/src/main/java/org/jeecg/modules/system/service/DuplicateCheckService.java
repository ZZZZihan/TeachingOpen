package org.jeecg.modules.system.service;

import java.util.List;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.DuplicateCheckMapper;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.system.mapper.SysUserRoleMapper;
import org.jeecg.modules.system.model.DuplicateCheckVo;
import org.springframework.stereotype.Service;

/** A duplicate probe has the same actor/object boundary as its form. */
@Service
public class DuplicateCheckService {
    private final DuplicateCheckMapper checks;
    private final SysUserMapper users;
    private final SysUserRoleMapper assignments;

    public DuplicateCheckService(DuplicateCheckMapper checks, SysUserMapper users, SysUserRoleMapper assignments) {
        this.checks = checks; this.users = users; this.assignments = assignments;
    }

    private enum Purpose {
        USERNAME("user_username", true), PHONE("user_phone", true), EMAIL("user_email", true), WORK_NO("user_work_no", true),
        PROFILE_PHONE("profile_phone", true), PROFILE_EMAIL("profile_email", true),
        ROLE("role_code", false), DICT("dict_code", false), PERMISSION("permission_perms", false),
        POSITION("position_code", false), DEPART_ROLE("depart_role_code", false),
        TEMPLATE("message_template_code", false), FILL_RULE("fill_rule_code", false), CHECK_RULE("check_rule_code", false),
        DATA_SOURCE("data_source_code", false);

        final String name;
        final boolean user;
        Purpose(String name, boolean user) { this.name = name; this.user = user; }
        boolean profile() { return this == PROFILE_PHONE || this == PROFILE_EMAIL; }
        static Purpose require(String name) {
            for (Purpose purpose : values()) if (purpose.name.equals(name)) return purpose;
            throw new IllegalArgumentException("未配置此校验用途");
        }
    }

    private SysUser requireActor() {
        Object principal = SecurityUtils.getSubject().getPrincipal();
        if (!(principal instanceof LoginUser)) throw new UnauthorizedException("请先登录");
        String id = ((LoginUser) principal).getId();
        if (id == null || id.isEmpty()) throw new UnauthorizedException("账户不可用");
        SysUser user = users.selectById(id);
        if (user == null || !id.equals(user.getId()) || !Integer.valueOf(0).equals(user.getDelFlag())
                || !Integer.valueOf(1).equals(user.getStatus())) throw new UnauthorizedException("账户不可用");
        return user;
    }

    public boolean available(DuplicateCheckVo input) {
        if (input == null) throw new IllegalArgumentException("校验参数不能为空");
        Purpose purpose = Purpose.require(input.getPurpose());
        String value = input.getFieldVal();
        if (value == null || value.isEmpty() || value.length() > 255 || value.matches("(?s).*\\p{Cntrl}.*")) {
            throw new IllegalArgumentException("校验值格式不正确");
        }
        String dataId = input.getDataId();
        if ("".equals(dataId)) dataId = null; // New forms have no persisted object yet.
        if (dataId != null && !dataId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("数据ID格式不正确");
        }
        SysUser actor = requireActor();
        if (purpose.profile()) {
            if (!actor.getId().equals(dataId)) throw new UnauthorizedException("只能校验本人的资料");
            // Phone is read-only in the personal form; it cannot become a phone enumeration endpoint.
            if (purpose == Purpose.PROFILE_PHONE && !value.equals(actor.getPhone())) {
                throw new UnauthorizedException("手机号由管理员维护");
            }
        } else {
            // Read current DB grants on every request; a Shiro/Redis cached role cannot retain access.
            List<String> roles = assignments.getRoleByUserId(actor.getId());
            boolean dev = roles != null && roles.contains("dev");
            if (!dev && (purpose == Purpose.ROLE || roles == null || !roles.contains("admin"))) {
                throw new UnauthorizedException("没有此表单的管理权限");
            }
        }
        if (dataId != null) {
            if (purpose.user) {
                SysUser target = users.selectById(dataId);
                if (target == null || !dataId.equals(target.getId()) || !Integer.valueOf(0).equals(target.getDelFlag())) {
                    throw new IllegalArgumentException("校验目标不存在或不可用");
                }
                if (!purpose.profile()) {
                    Integer actorLevel = assignments.getUserRoleLevel(actor.getId());
                    Integer targetLevel = assignments.getUserRoleLevel(dataId);
                    if ((targetLevel == null ? -1 : targetLevel) > (actorLevel == null ? -1 : actorLevel)) {
                        throw new UnauthorizedException("不能管理更高权限的账户");
                    }
                }
            } else if (!dataId.equals(checks.targetId(purpose.name, dataId))) {
                throw new IllegalArgumentException("校验目标不存在或不可用");
            }
        }
        Long count = checks.count(purpose.name, value, dataId);
        if (count == null) throw new IllegalStateException("重复校验未完成");
        return count == 0;
    }
}
