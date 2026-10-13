# 用户查询 SQL 边界（H-03 / M-04）

原始审查基线 `2cbd9c47`；本分支从 `a3f4e10c` 开始。源码核实了组织前缀、关系筛选和高级查询列进入 SQL 语法的路径，未据此声称生产注入已成功。

- QueryGenerator 只接受当前实体的持久化字段和实际列名；排除临时字段、视图模型字段，拒绝未知列、表达式、无效高级规则，错误不再吞掉后执行更宽查询。兼容 camelCase、snake_case、字典文本后缀及 asc/desc/ascend/descend。
- 组织分页及计数参数化；查询前要求真实、当前可管理的组织对象，普通学生或跨班教师无法使用任意组织前缀。角色与管理班级来自实时数据库。
- 列表、导出、旧部门 service 查询统一使用参数绑定的 EXISTS。角色及部门筛选不再引用未连接的列/表。合法导出继续使用稳定 100 行分页和完整性检查。
- 同类分类字典 loadOne/loadTreeData 列名入口使用同一实体白名单；未启用的旧表字典 keyword SQL 也改为绑定。

本地 Java 8 / 离线 Maven：QuerySqlBoundaryTest 7 项、PaginationBoundaryTest 6 项实际通过。测试解析真实 SysUserMapper XML，检查 BoundSql SQL 文本及参数映射；覆盖非法列、字面值、正常排序、实时组织授权与既有 101 行导出分页。HTTP/MySQL 探针 `api/dev/verify-user-query-boundaries.py` 已新增并通过 Python 编译，包含实际 Excel POI 读取、101 个合成用户及角色/部门组合筛选；需在根候选环境执行，本提交不宣称 HTTP 探针已通过。

保留的动态 SQL 经范围检查：`ew.customSqlSegment` 仅收服务端 wrapper；SysDict 的通用表 HTTP 查询已停用，命名字典有固定用途映射；NgAlain 表查询路由注释停用；`updateNullByEmptyString` 仅 email/phone 常量调用。没有改动部署或生产配置。
