# 重复校验按表单用途收口

用户验收发现，`GET /sys/duplicate/check` 接受客户端的 `tableName` 和 `fieldName`，并交由 `SysDictMapper` 的 `${}` 插值拼接查询。登录用户可指定敏感字段，或把布尔表达式写入字段名，通过“值已存在/可用”的结果推测数据库内容。

修复保留现有表单查重行为，把请求改为服务端已配置的 `purpose`。所有表和字段都直接写在 `DuplicateCheckMapper.xml` 中；候选值和排除 ID 只通过 `#{}` 绑定。旧的两条动态查重 SQL 和对应 Mapper 方法已删除。

## 请求与结果

请求示例：`GET /sys/duplicate/check?purpose=user_username&fieldVal=example&dataId=edited-user-id`。

- 只接受 `purpose`、`fieldVal`、可选 `dataId` 和前端时间戳 `_t`，每个参数只能出现一次。
- 出现 `tableName`、`fieldName` 或其他未知参数直接拒绝；旧参数为空，或同时提供合法用途，也会拒绝。
- `fieldVal` 须为 1 至 255 字符且不含控制字符。其内容作为数据绑定，不能选择字段或增加查询条件。
- 新增表单可省略 `dataId` 或传空字符串；编辑 ID 只能是 1 至 64 位字母、数字、下划线或横杠，并必须通过目标记录检查。
- 沿用 Jeecg 结果对象：可用 `success=true/code=200`；重复 `success=false/code=500`；无效参数或无效目标 `success=false/code=400`；权限不足 `success=false/code=403`。这些业务结果的 HTTP 状态仍为 200，匿名身份由现有认证过滤器拒绝。
- 不返回目标记录、数量或候选字段内容，也不记录候选值日志。

## 已配置用途

| 用途 | 固定数据 | 访问条件 |
| --- | --- | --- |
| `user_username`、`user_phone`、`user_email`、`user_work_no` | `sys_user.username/phone/email/work_no` | 当前数据库角色为 `admin` 或 `dev` |
| `role_code` | `sys_role.role_code` | 当前数据库角色为 `dev`，与角色写接口一致 |
| `dict_code` | `sys_dict.dict_code` | 当前数据库角色为 `admin` 或 `dev` |
| `permission_perms` | `sys_permission.perms` | 同上 |
| `position_code` | `sys_position.code` | 同上 |
| `depart_role_code` | `sys_depart_role.role_code` | 同上 |
| `message_template_code` | `sys_sms_template.template_code` | 同上 |
| `fill_rule_code`、`check_rule_code` | `sys_fill_rule.rule_code`、`sys_check_rule.rule_code` | 同上 |
| `data_source_code` | `sys_data_source.code` | 同上 |
| `profile_email` | `sys_user.email` | 活跃用户本人，必须提供与当前身份严格一致的 ID |
| `profile_phone` | `sys_user.phone` | 活跃用户本人，只能核对本人当前号码；个人设置页手机号由管理员维护 |

每次请求先读取当前用户记录，确认未删除且未冻结。管理用途每次读取数据库角色，不依赖 Shiro 或 Redis 中旧的授权结果，因此撤权后旧会话不能继续使用管理查重。

用户管理的排除 ID 必须对应未删除用户，且目标当前角色等级不得高于操作者。其他配置用途必须查到相应表中的目标，字典和权限目标还须未删除。目标 ID 与查询返回 ID 使用严格字符串比较，避免数据库不区分大小写时把别名当作合法目标。没有合法编辑对象的请求不会执行重复计数。

## 消费者与生成器

已迁移用户、角色、字典、权限、职务、部门角色、消息模板、填值规则、校验规则、数据源表单，以及个人资料页。共享函数签名为 `validateDuplicateValue(purpose, fieldVal, dataId, callback)`。个人资料页同时修正了缺失的查重函数导入，以及原来引用不存在的 `this.userId` 的问题。

网络失败会完成校验回调并提示重试；用户编辑器继续忽略旧会话回包。可选空工号不会发起查重。权限拒绝不会被显示为“值已经存在”。

代码生成器的唯一校验模板使用相同的固定用途映射。未配置的表/字段会在生成时明确停止，提示先增加服务端固定查询、访问权限和编辑对象授权，再更新模板；不会生成通用表/字段请求，也不会静默跳过唯一性。

## 验证与边界

- Java 8 Maven `clean package` 显式启用测试：15 类、130 项全部通过，无失败、错误或跳过；其中 `DuplicateCheckSecurityTest` 的 13 项覆盖每个管理用途的新增、重复和编辑，旧参数与混合请求、重复参数、未登录/不可用主体、实时撤权、无效/大小写/越级排除 ID、本人资料用途、实际 MyBatis SQL 参数绑定，以及真实 FreeMarker 模板渲染和未知用途拒绝。
- `node --test web/tests/duplicate-check-purpose.test.cjs`：28/28 通过。测试执行真实 SFC 校验函数及共享工具，覆盖全部 15 个用途、重复、权限拒绝、网络失败、用户新增及会话切换；此结果属于受控响应的前端行为测试。
- `npm --prefix web test`：791/791 通过，零跳过。`npm --prefix web run build` 成功，保留现有 CSS 顺序与包体积警告；`check:initial-assets` 通过，首屏资源为 3,323,039 字节，gzip 898,634 字节，均低于原门槛。使用相同 ESLint 配置逐文件对照 HEAD 原文，12 个相关文件的历史错误由 1,108 降至 1,090，所有文件的错误与警告均未增加；整文件 lint 仍不通过。
- `api/dev/verify-duplicate-check.py` 在独占合成 Spring/Shiro/MySQL/Redis 环境实际执行：379/379 通过，包含 188 个逐请求数据库不变断言，覆盖匿名、五种角色、全部用途、越权排除 ID、旧 SQL 参数和保留旧授权缓存后的实时撤权。清理后 12 张受保护表的摘要与起始值相同。最终报告为 `.devspace/duplicate-1011/duplicate-template-final.json`，候选 JAR SHA-256 为 `0b1962cffefe66c5198705e543956cb690daa2e085fd008d21ac86c6cf810937`。CI 同时接入此真实 HTTP 回归与 Java 测试结果检查。
- 未参与实现的 Agent 独立复核接口、SQL、授权、消费者及生成模板，并执行前端定向 28 项；所发现的模板遗漏已修复后复核通过。CI 工具自身的 Python 单元测试 19/19 通过。

这些检查限定于本地合成环境和代码验证。上线需同时更新后端与前端；旧浏览器仍使用旧请求合同时会得到明确拒绝，需要刷新。修复不替代各业务保存接口的唯一约束或事务校验，也不代表已经合并、部署或完成用户人工验收。
