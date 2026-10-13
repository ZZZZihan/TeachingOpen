# 私有用户资料读取（M-03）

原始详情和批量入口直接返回 SysUser；部门入口允许通过请求部门扩大读取范围。源码已复核，不能将静态确认等同于生产泄露已发生。

- 单条和批量共用 UserProfileReadService。本人、当前管理员、当前管理班级的教师三种规则；批量 1–100 个目标先全部验证，再生成响应。缺失/大小写别名和混合未授权批次整体拒绝。
- UserProfileView 是显式字段契约。教师读取学生仅 id/username/realname/avatar 及列表已有的部门/角色显示名称；本人可读自己的联系方式；管理员保留账户表单所需管理字段。所有角色均无 password/salt/第三方标识/内部审计字段。
- 用户列表、部门列表、多部门选择别名使用同一范围和 DTO；角色列表与旧 appUserList 限管理员；用户角色/部门关系详情也先验证目标对象。表单 token 兼容入口只使用真实已认证 principal，不再解码请求 token 指定他人身份。
- 组织通讯录对非管理员移除联系方式。导出保留账号导入契约，但 ExportParams 明确排除密码列；教师导出还排除生日、电子邮件、电话和座机。QueryGenerator 不允许 WRITE_ONLY 的凭据字段查询/排序。

本地 Java 8 / Maven 实跑：UserReadAuthorizationTest 7、QuerySqlBoundaryTest 7、DepartmentSelectionTest 6、PaginationBoundaryTest 6，共 26 项通过，无失败/错误/跳过。DTO测试断言每类角色的精确字段集合，包括跨班/同班学生拒绝、整批拒绝、实时撤权和管理员字段保持。

真实 HTTP/MySQL 探针扩展了每角色 JSON 字段集合、别名入口、撤销管理班级后同 token 拒绝、实际 Excel 密码列/私密列排除。该探针由根最终组合候选执行，本提交只完成 Python 编译，尚不声称真实 HTTP 已通过。用户读取用途与管理员账户导入没有合并为同一 DTO，避免破坏合法导入密码输入。
