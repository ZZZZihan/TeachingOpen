# H-06 审计与通用版本历史管理边界

本修复从独立 Pro 复核的不可变候选 `d88f439205d21fb489785c3ee228e4482f5b7d65` 开始。Pro 最终报告将审计日志越权读删列为 H-06 High，将通用版本历史读取缺少对象授权列为 Medium。本地验证仅在独占的合成运行时执行，没有生产访问或生产利用结论。

## 已核实的路由和数据链

| 路由 | 原行为 | 修复后 |
| --- | --- | --- |
| `GET /sys/log/list` | 登录即可读取完整 `SysLog`，包括旧 `requestParam` | 当前有效 `admin`/`dev` |
| `DELETE /sys/log/delete` | 登录即可删除指定日志 | 当前有效 `admin`/`dev` |
| `DELETE /sys/log/deleteBatch`，包括 `ids=allclear` | 登录即可批删或清空整个审计表 | 当前有效 `admin`/`dev` |
| `GET /sys/dataLog/list` | 登录即可读取通用版本 JSON | 当前有效 `admin`/`dev` |
| `GET /sys/dataLog/queryCompareList` | 仅凭历史行 ID 即可对比 | 当前有效 `admin`/`dev` |
| `GET /sys/dataLog/queryDataVerList` | 仅凭业务表名/对象 ID 即可读取版本 | 当前有效 `admin`/`dev` |

这两个控制器均不继承通用 CRUD 控制器，没有独立的 `queryById`/`exportXls` 映射。默认 JWT 过滤器只验证登录；基础设施管理拦截器匹配 Online/数据源/Quartz 控制器，不覆盖审计控制器；服务的通用查询与 `removeAll` 原先也不附加管理或业务对象授权。`/sys/loginfo` 和 `/sys/visitInfo` 仅返回汇总数量，没有原始请求或版本 JSON，保留其原流程。

真实基线验证在原候选 JAR `7fc5d65069f9b04ab0d4285bff50a2e19d16b67f43ac2d51e76ea582c25e9ba3` 上执行：教师通过实际批改 API 写入唯一合成评分/评语；另一班的学生和教师通过作品详情及评分接口被拒绝，但经审计列表和三种版本读取接口取得相同标记。普通账号的单删、批删和 `allclear` 也实际生效。`evidence/h06/http-before-d88.json` 与对应 `.log` 保留 42/42 对照检查及完整清理结果；这里的“通过”是漏洞反例按预期复现，不表示基线安全。

## 修复和合法流程

新增 `AuditLogAccessService`，每次检查当前数据库账号状态与角色，不依赖旧主体中的角色。六个现有管理方法在查询、参数处理和任何删除之前调用它；版本对比的检查放在既有异常捕获外，避免权限错误被改成空的成功响应。清空操作独立处理，不再继续将 `allclear` 当作普通 ID 批删。

通用版本管理页面只位于系统管理界面；没有发现学生或教师业务界面直接依赖这些通用历史路由。学生更新作品仍通过内部 `addDataLog` 记录旧版本，批改和登录审计写入仍可用。通用历史没有直接开放给普通用户；如将来需要业务历史界面，应通过所属作品的对象授权提供专用读取接口。

既有敏感日志仍受读取边界保护，不依赖清理旧记录或修改新写入策略。审计采集最小化和已提交业务后的日志失败响应由另一个独立修复处理，本提交不修改 `AutoLogAspect`。

## 验证和剩余门槛

`AuditLogAuthorizationTest` 为 7 项：未执行守卫时有 5 项按预期失败，执行守卫后 7/7 通过。覆盖学生/教师拒绝、管理员与开发角色允许、同主体撤权、失效账号、删除前无持久化调用，以及真实版本服务在普通学生业务流程中仍写入历史。

```sh
cd api
mvn -s dev/maven-settings.xml -DskipTests=false \
  -Dtest=AuditLogAuthorizationTest -Dsurefire.failIfNoSpecifiedTests=false \
  -pl jeecg-boot-module-system -am test
cd ..
python3 api/dev/verify-audit-log-authorization.py \
  --runtime /path/to/exclusive-synthetic-runtime --jar /path/to/candidate.jar \
  --output /path/to/new-report.json
```

HTTP 探针会实际运行管理员 `allclear`，仅可在 `FixtureApi` 约束的独占合成数据库执行。它在内存保存完整原审计表，结束时先退出合成会话，再还原审计、业务/版本、统计和角色数据并比较所有相关表哈希。脚本不输出凭据或原审计内容，拒绝覆盖既有报告。修复模式包含普通账号/匿名拒绝、历史标记隔离、全部拒绝前后 DB 不变、同 token 角色授予/撤销，以及合法管理员读删。

修复后完整 HTTP、最终组合 CI 和下一轮 Pro 验收由统筹绑定新的不可变候选执行。这里的 Java 自检和基线对照不替代这些完成门槛。
