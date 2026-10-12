# 全局规则与分类管理授权

独立于 H-07 的问题提交；复用前置提交的实时 `GlobalResourceAccessService`。

`SysFillRule`、`SysCheckRule`、`SysCategory` 的管理列表、详情、导出、增删改、批量删除及 Excel 导入统一要求数据库中仍有效的 admin/dev 账户。服务层普通保存、更新、删除、批量保存同样受控，禁止通过未使用的 wrapper/upsert 绕过校验。导入全部解析后统一预校验，并以事务写入；不再让分类 Excel 逐行部分提交。客户端审计字段不进入数据库，服务器维护作者和时间。

填值规则只支持源码实现的 OrgCodeRule 与 CategoryCodeRule；两个内建 ruleCode 必须匹配对应类。写入和执行均校验类名、参数、长度；执行端也拒绝历史不受支持配置，反射不会加载任意配置类。机构与分类编码的普通服务调用仍保留。没有将反射配置问题称为已验证的任意代码执行。

已核实 `web/src/api/api.js` 的 `checkRuleByCode` 普通表单消费者，因此保留 `/sys/checkRule/checkByCode`；值上限 256 字符，规则 JSON 上限 1024 字符、20 项，逐项校验位数、提示和正则形式。接受库内全部种子规则的常用字符/长度模式，排除分组、回溯引用、字符组外分支、多重可变长度重复。不运行压力测试，不据此声称课堂容量或任意正则性能保证。不受支持的历史自定义表达式会明确失败，需管理员按允许形式修订；本提交不迁移生产配置。

分类选择器的 `loadTreeData`/`loadOne`/树读取保持可用；父级存在性和环路检查在写入前，新增节点与父级标记在同一事务。填值执行接口保留普通登录调用，但仅能执行受控的两类生成器，批量上限 20。

验证：修改前 `evidence/global-rules-before-java.log` 中 3 条普通学生写入回归全部失败。修复后 `GlobalRuleAdministrationTest` 10 条通过（普通学生、教师、实时撤权、冻结账户、全部管理 mapping、admin/dev CRUD、三种真实 Excel 导入、无部分写入、普通表单校验、两个内建生成器及种子规则兼容）。与 ScratchAssetAdministrationTest、QuerySqlBoundaryTest 联跑共 26 条通过，证据 `evidence/global-rules-after-java-r4.log`。

真实 HTTP/MySQL 探针 `api/dev/verify-global-rule-boundaries.py` 由根代理在最终候选运行：全管理入口拒绝且表快照不变；三种管理员 CRUD/Excel、同 token dev 授予及撤销；普通表单与分类选择读取；拒绝删除机构规则后正常创建班级；非法类及混合 Excel 不部分入库；finally 清理所有合成数据并核对原快照。探针复用 H-07 的 POI fixture helper，报告绑定实际运行 JAR SHA；旧漏洞重放模式不支持。候选 HTTP、最终 CI 与独立 Pro 验收须以实际运行证据为准。

## 现有消费者兼容性复核

`validateCheckRule` 先调用 `encodeURIComponent`，`checkRuleByCode` 再经 `getAction` 交给 Axios 的 query serializer。Servlet 只解除外层传输编码，因此 `/checkByCode` 保留一次 `URLDecoder.decode`。修复前新增 MockMvc 回归在 `A+B% C中文` 上失败（`evidence/global-rules-encoding-before.log`）；修复后仅解码一次，字面 `%41` 不会被继续变为 `A`。编码文本先限制为 2304 字符，解码后限制为 256 个 Java UTF-16 单元；超长值和不完整百分号编码在规则查询前返回明确错误。前端调用语义未改变。

已逐一检查源码中的 `FillRuleUtil.executeRule` 调用：`SysDepartServiceImpl.saveDepartData` 传 `parentId`、期望 `String[2]`；分类新增传 `pid`、期望 `String`；管理测试传空表单；单个与批量执行端仍把调用者表单交给同一校验器。两类生成器只读取对应的单个参数，没有遗漏其他源码支持字段。默认配置参数、空表单回退、显式根节点及表单覆盖父级的行为均有回归。仓库未发现前端对通用单个/批量执行接口的调用；外部自定义消费者与配置不能由此推断兼容。

`JCategorySelect` 使用 `loadTreeData` 和 `loadDictItem`；`JTreeDict` 使用 `loadTreeRoot`、`loadTreeChildren` 和 `loadOne`。这些读取及 `loadAllData` 保留普通登录访问和原返回字段。`JTreeSelect` 使用独立的 `/sys/dict` 读取，不经过本次分类管理门禁；`rootList`、`childList` 为管理页接口。普通学生读取五个选择器接口和 `loadAllData` 已经过 MockMvc 回归。

兼容性验证：`GlobalRuleAdministrationTest` 14 条，连同 Scratch/SQL 回归共 30 条通过，记录 `evidence/global-rules-compat-java.log`。`web/tests/check-rule-wire-contract.test.cjs` 执行实际 util/API/getAction 源码和锁定 Axios 0.34.0 的 serializer，6 条通过，记录 `evidence/global-rules-compat-node-r2.log`。第一次 Node 运行误用旧缓存 Axios 0.18.1，其失败日志保留；不作为当前候选验证。HTTP 探针新增相同特殊字符、Unicode 长度及错误编码场景，需在最终候选重新执行。

## 本地导出配置预检

预检只检查操作者提供的本地 JSON 导出，不能证明生产已核对。先按单独授权从目标数据库取得完整的 `sys_fill_rule`、`sys_check_rule` 只读导出，记录来源与时间，避免凭据和无关表数据。脚本本身没有数据库连接参数，也不执行 SQL。以下为 MySQL JSON 导出的 SELECT 示例，**本次未在生产执行**：

```sql
SELECT JSON_OBJECT(
  'fill_rules', (SELECT COALESCE(JSON_ARRAYAGG(JSON_OBJECT(
    'id', id, 'rule_code', rule_code, 'rule_class', rule_class,
    'rule_params', rule_params)), JSON_ARRAY()) FROM sys_fill_rule),
  'check_rules', (SELECT COALESCE(JSON_ARRAYAGG(JSON_OBJECT(
    'id', id, 'rule_code', rule_code, 'rule_json', rule_json)),
    JSON_ARRAY()) FROM sys_check_rule)
);
```

将单个 JSON 对象保存为 UTF-8 文件（不含 SQL 客户端表头），使用已固定 SHA 的候选 JAR 和本地 JDK：

```sh
python3 api/dev/preflight-rule-config.py \
  --input /path/to/rules-export.json \
  --jar /path/to/teaching-open-2.8.0.jar \
  --output /path/to/new-rules-preflight-report.json \
  --java-home /path/to/jdk8
```

脚本在临时目录解开依赖并编译小型检查器，调用**该 JAR 的** `FillRuleUtil.requireSupported/parameters` 与 `CheckRuleValidator.rules`。它不启动 Spring、不调用 `executeRule`、不对值执行正则匹配、不更改任何配置。检查内建规则缺失、重复 ruleCode、类及参数白名单、校验规则结构；最多每表 5000 行、输入 20 MiB。报告包含输入/JAR/脚本 SHA、逐行兼容状态及固定原因码，不复制规则正文或参数；已有报告禁止覆盖。退出码 0 表示导出内这些检查通过，1 表示配置需修订，2 表示格式/工具错误，不能将 2 当作已通过。

出现不兼容配置应停止相关上线检查并逐项核对；不自动回写旧数据，不提供放宽白名单开关。自定义 Java handler 必须单独审查后决定实现方式，不能仅为通过预检允许任意反射类。检查器不验证导出完整性、默认父级记录存在性、实时权限、实际生成/导入、并发和课堂容量；这些仍由目标版本对应核验和合成候选回归负责。

仅合成数据的脚本验证：`evidence/rule-preflight/supported-report-r2.json` 与 `needs-review-report-r2.json` 记录兼容和拒绝结果；`evidence/global-rules-preflight-r2.log` 验证原导出字节不变、JAR SHA 绑定、缺少机构规则/自定义类/不支持表达式/重复 code 准确报告及拒绝覆盖证据。没有声称生产自定义配置已完成预检。
