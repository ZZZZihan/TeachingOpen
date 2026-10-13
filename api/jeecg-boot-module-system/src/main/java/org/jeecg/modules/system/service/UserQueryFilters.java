package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import java.util.Collection;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

/** Fixed relationship SQL; every requested ID is a MyBatis parameter. */
public final class UserQueryFilters {
    private UserQueryFilters() { }

    public static void departments(QueryWrapper<?> query, Collection<String> ids) {
        relationship(query, "sys_user_depart", "dep_id", ids);
    }

    public static void roles(QueryWrapper<?> query, Collection<String> ids) {
        relationship(query, "sys_user_role", "role_id", ids);
    }

    private static void relationship(QueryWrapper<?> query, String table, String column, Collection<String> ids) {
        if (ids == null || ids.isEmpty()) { query.apply("1 = 0"); return; }
        String placeholders = IntStream.range(0, ids.size()).mapToObj(i -> "{" + i + "}").collect(Collectors.joining(","));
        query.apply("EXISTS (SELECT 1 FROM " + table + " user_relation WHERE user_relation.user_id = sys_user.id"
                + " AND user_relation." + column + " IN (" + placeholders + "))", ids.toArray());
    }
}
