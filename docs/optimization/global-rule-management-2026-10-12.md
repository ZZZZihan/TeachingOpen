# 全局规则与分类管理授权

独立于 H-07 的问题提交；复用前置提交的实时 `GlobalResourceAccessService`。

`SysFillRule`、`SysCheckRule`、`SysCategory` 的管理列表、详情、导出、增删改、批量删除及 Excel 导入统一要求数据库中仍有效的 admin/dev 账户。服务层普通保存、更新、删除、批量保存同样受控，禁止通过未使用的 wrapper/upsert 绕过校验。导入全部解析后统一预校验，并以事务写入；不再让分类 Excel 逐行部分提交。客户端审计字段不进入数据库，服务器维护作者和时间。

填值规则只支持源码实现的 OrgCodeRule 与 CategoryCodeRule；两个内建 ruleCode 必须匹配对应类。写入和执行均校验类名、参数、长度；执行端也拒绝历史不受支持配置，反射不会加载任意配置类。机构与分类编码的普通服务调用仍保留。没有将反射配置问题称为已验证的任意代码执行。

已核实 `web/src/api/api.js` 的 `checkRuleByCode` 普通表单消费者，因此保留 `/sys/checkRule/checkByCode`；值上限 256 字符，规则 JSON 上限 1024 字符、20 项，逐项校验位数、提示和正则形式。接受库内全部种子规则的常用字符/长度模式，排除分组、回溯引用、字符组外分支、多重可变长度重复。不运行压力测试，不据此声称课堂容量或任意正则性能保证。不受支持的历史自定义表达式会明确失败，需管理员按允许形式修订；本提交不迁移生产配置。

分类选择器的 `loadTreeData`/`loadOne`/树读取保持可用；父级存在性和环路检查在写入前，新增节点与父级标记在同一事务。填值执行接口保留普通登录调用，但仅能执行受控的两类生成器，批量上限 20。

验证：修改前 `evidence/global-rules-before-java.log` 中 3 条普通学生写入回归全部失败。修复后 `GlobalRuleAdministrationTest` 10 条通过（普通学生、教师、实时撤权、冻结账户、全部管理 mapping、admin/dev CRUD、三种真实 Excel 导入、无部分写入、普通表单校验、两个内建生成器及种子规则兼容）。与 ScratchAssetAdministrationTest、QuerySqlBoundaryTest 联跑共 26 条通过，证据 `evidence/global-rules-after-java-r4.log`。

真实 HTTP/MySQL 探针 `api/dev/verify-global-rule-boundaries.py` 由根代理在最终候选运行：全管理入口拒绝且表快照不变；三种管理员 CRUD/Excel、同 token dev 授予及撤销；普通表单与分类选择读取；拒绝删除机构规则后正常创建班级；非法类及混合 Excel 不部分入库；finally 清理所有合成数据并核对原快照。探针复用 H-07 的 POI fixture helper，报告绑定实际运行 JAR SHA；旧漏洞重放模式不支持。候选 HTTP、最终 CI 与独立 Pro 验收须以实际运行证据为准。
