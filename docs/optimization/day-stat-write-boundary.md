# 班级每日教学记录人工写入口关闭

日统计由教学事件累计。旧 `TeachingDepartDayLogController` 的 `add`、`edit`、`delete`、`deleteBatch` 直接调用通用写服务，`importExcel` 调用基类批量导入；登录者可以绕过 `addLog` 的班级行锁和当天记录锁，伪造计数、删除记录或造出同班同日重复记录。

本次保留五个旧地址，全部返回 HTTP 403、`success=false`、`code=403` 和“班级每日教学记录由教学事件自动生成，不支持人工修改”。管理员也收到同样的拒绝。控制器不再调用通用写服务或 Excel 导入，自动 `addLog` 事件路径保持原有班级锁、当天当前读和原子计数。

当前源码消费核查覆盖 `api`、`web/src` 和开发探针：前端只有 `UnitViewModal.vue` 调用自动 `unitViewLog`，`TeacherReport.vue` 调用三个只读报告地址。未发现合法人工维护需求或人工 CRUD/import 页面，因此本次无需前端入口改动。列表、详情、导出及报告的读取权限不属于本次人工写入修复。

`TeachingDepartDayLogWriteBoundaryTest` 用真实 Spring MVC 映射核查五个写入口返回 403，验证日统计、课程和 Redis 服务均未调用。`api/dev/day_log_boundary.py` 接入已有 `verify-account-authorization.py`，通过五个合成角色真实登录后逐一发送五种请求；Excel 请求使用候选 JAR 内 POI 生成并重新打开的有效 XLS。每次拒绝均核对账号、权限、班级、任务和日统计表的摘要、相关 Redis 集合，以及同班同日的一条记录保持不变。探针保留原数据，只清理本次随机命名的合成记录；失败时仅恢复本次目标记录。

2026-10-11 本机实际验证使用独占 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/daylog-1011`，MySQL/Redis/后端/前端预留端口分别为 `13426/16489/18331/18332`。数据库仅导入 schema 和五个标准合成账号，没有连接或写入生产数据库。JDK 为现有 Azul Java 8u504，MySQL 8.4.6，Redis 7.2.9。候选 JAR SHA-256 为 `de800c0157ab60c23016e1cd33e581bca116dccc3f3d3ad88886f7ce66352b35`。

- Maven `clean package` 显式启用 `TeachingDepartDayLogWriteBoundaryTest,AdditionalWorkStatisticsTest`：15/15，无失败、错误或跳过。其中新增控制器检查 5 项，原事件统计检查 10 项。
- 完整 `verify-account-authorization.py`：451/451，其中新增日统计检查 77 项。
- `verify-additional-work-authorization.py`：79/79。真实 MySQL REPEATABLE READ 下，已有记录、当天首次记录、历史空计数、混合开课与布置事件等五个场景，均观测到两个 HTTP 写者等待同一班级锁，完成后当天只有一条记录，计数正确；故障回滚与原记录恢复也通过。
- 最终探针修改仅优化恢复逻辑，已存在记录未变化时不执行 `REPLACE`。最新 helper 再跑专项 77/77，摘要为 `87179b71c3be5e4295b3fc3adc61612acb88727aadcb1ee74ed628babe104c90`。这 77 项是重复核对，不与上述 451 项相加。
- 两个 Python 文件 `py_compile` 和 `git diff --check` 通过。未改前端产品文件，未运行前端构建。

实际日志、JSON 结果、四个实现/测试/探针文件摘要，以及最终执行探针均保存在 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/day-stat-write-boundary-1011/`：`maven-targeted.log`、`account-authorization-final.{log,json}`、`additional-work-authorization.{log,json}`、`manual-write-final.{log,json}`、`source-manifest.json`、`run-manual-final.py`。前两次 Excel 夹具编译因旧 POI 3.9 不支持 `AutoCloseable` 停止；兼容写法修复后完成以上成功结果，未把早期失败计入通过数。

未参与实现的 Agent 已独立复核产品代码、测试、真实 HTTP/DB/Redis 结果和同一 JAR 摘要，没有发现本次修复阻塞。以上结果属于本机合成环境和技术复核；本项未执行提交、推送、合并、部署或人工验收，主 Agent 统一推进 PR。

复现所用命令在本工作树执行：

```sh
cd api
JAVA_HOME=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home \
  /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/apache-maven-3.9.16/bin/mvn \
  -B -ntp -s dev/maven-settings.xml \
  -Dmaven.repo.local=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/m2 \
  -DskipTests=false -Dtest=TeachingDepartDayLogWriteBoundaryTest,AdditionalWorkStatisticsTest \
  -Dsurefire.failIfNoSpecifiedTests=false clean package
cd ..
python3 api/dev/prepare-local.py \
  --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/daylog-1011 \
  --tools /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools \
  --mysql-port 13426 --redis-port 16489 --backend-port 18331 --frontend-port 18332
python3 api/dev/run-backend.py start \
  --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/daylog-1011 \
  --java-home /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home \
  --log-name backend-daylog.log
python3 api/dev/verify-account-authorization.py \
  --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/daylog-1011 \
  --output /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/day-stat-write-boundary-1011/account-authorization-final.json
python3 api/dev/verify-additional-work-authorization.py \
  --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/daylog-1011 \
  --output /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/day-stat-write-boundary-1011/additional-work-authorization.json
python3 /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/day-stat-write-boundary-1011/run-manual-final.py
```

重新验证需要新的独占 runtime 和新的证据路径，不能覆盖本轮保留的结果。
