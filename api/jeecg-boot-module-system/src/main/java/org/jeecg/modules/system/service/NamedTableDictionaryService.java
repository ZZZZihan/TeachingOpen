package org.jeecg.modules.system.service;

import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.apache.shiro.subject.Subject;
import org.jeecg.common.system.vo.DictModel;
import org.jeecg.modules.system.model.TreeSelectModel;
import org.springframework.stereotype.Service;

import java.util.Collections;
import java.util.List;

/** Client dictionary names select server-owned purposes, never SQL identifiers. */
@Service
public class NamedTableDictionaryService {
    private final ISysDictService dictionaries;

    public NamedTableDictionaryService(ISysDictService dictionaries) {
        this.dictionaries = dictionaries;
    }

    private enum Purpose {
        COURSES("course_options", "teaching_course", "course_name", "id", false),
        ROLES("registration_roles", "sys_role", "role_name", "id", true),
        CATEGORIES("category_tree", "sys_category", "name", "id", false),
        USERS("system_users", "sys_user", "realname", "id", false),
        USERS_WITHOUT_ADMIN("system_users_without_admin", "sys_user", "realname", "id", false),
        DEPARTMENTS("system_departments", "sys_depart", "depart_name", "id", false),
        PERMISSIONS("system_permissions", "sys_permission", "name", "id", false),
        DEMO("demo_options", "demo", "name", "id", false);

        final String name, table, text, code;
        final boolean adminOnly;

        Purpose(String name, String table, String text, String code, boolean adminOnly) {
            this.name = name; this.table = table; this.text = text; this.code = code; this.adminOnly = adminOnly;
        }

        String legacyCode() { return table + "," + text + "," + code; }
    }

    public boolean isTablePurpose(String name) {
        if (name == null) return false;
        if (name.indexOf(',') >= 0) return true;
        for (Purpose purpose : Purpose.values()) if (purpose.name.equals(name)) return true;
        return false;
    }

    public void validateScalarCode(String name) {
        if (name == null || !name.matches("[A-Za-z0-9_-]{1,100}")) {
            throw new IllegalArgumentException("字典名称不正确");
        }
    }

    private Purpose requirePurpose(String name) {
        Purpose selected = null;
        for (Purpose purpose : Purpose.values()) {
            if (purpose.name.equals(name)
                    || (purpose != Purpose.USERS_WITHOUT_ADMIN && purpose.legacyCode().equals(name))) {
                selected = purpose;
                break;
            }
        }
        if (selected == null) throw new IllegalArgumentException("未配置此字典用途");
        Subject subject = SecurityUtils.getSubject();
        if (subject.getPrincipal() == null || (!subject.hasRole("admin")
                && (selected.adminOnly || !subject.hasRole("dev")))) {
            throw new UnauthorizedException("无字典访问权限");
        }
        return selected;
    }

    public List<DictModel> items(String name) {
        Purpose purpose = requirePurpose(name);
        if (purpose == Purpose.USERS_WITHOUT_ADMIN) {
            // This demo's filter is owned by the server; callers cannot supply SQL.
            return dictionaries.queryTableDictItemsByCodeAndFilter("sys_user", "realname", "id",
                    "username!='admin' order by create_time");
        }
        return dictionaries.queryTableDictItemsByCode(purpose.table, purpose.text, purpose.code);
    }

    public List<DictModel> search(String name, String keyword) {
        Purpose purpose = requirePurpose(name);
        if (purpose == Purpose.USERS_WITHOUT_ADMIN) throw new IllegalArgumentException("此字典不支持搜索");
        if (keyword == null || keyword.length() > 100) throw new IllegalArgumentException("搜索内容不正确");
        return dictionaries.queryTableDictItems(purpose.table, purpose.text, purpose.code, keyword);
    }

    public List<String> labels(String name, String keys) {
        Purpose purpose = requirePurpose(name);
        if (purpose == Purpose.USERS_WITHOUT_ADMIN) throw new IllegalArgumentException("此字典不支持回显");
        if (keys == null || keys.length() > 5000) throw new IllegalArgumentException("字典值不正确");
        String[] values = keys.split(",", -1);
        if (values.length > 100) throw new IllegalArgumentException("字典值过多");
        for (String value : values) {
            if (value.isEmpty() || value.length() > 100) throw new IllegalArgumentException("字典值不正确");
        }
        return dictionaries.queryTableDictByKeys(purpose.table, purpose.text, purpose.code, values);
    }

    public List<TreeSelectModel> tree(String name, String pid, String pidField, String hasChildField, String condition) {
        Purpose purpose = requirePurpose(name);
        if (purpose != Purpose.CATEGORIES && purpose != Purpose.PERMISSIONS) {
            throw new IllegalArgumentException("此字典不支持树形查询");
        }
        if (pid == null || pid.length() > 100) throw new IllegalArgumentException("父节点不正确");
        String parentField = purpose == Purpose.PERMISSIONS ? "parent_id" : "pid";
        if ((pidField != null && !pidField.isEmpty() && !parentField.equals(pidField))
                || (hasChildField != null && !hasChildField.isEmpty())
                || (condition != null && !condition.isEmpty())) {
            throw new IllegalArgumentException("不支持自定义树形字段或条件");
        }
        return dictionaries.queryTreeList(Collections.emptyMap(), purpose.table, purpose.text, purpose.code,
                parentField, pid, "");
    }
}
