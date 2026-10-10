# 每日教学统计业务日期一致性

2026-10-11 的 GitHub backend 回归暴露了真实日期缺陷。PR #102 的 run `38068467038`、job `114260831354` 与 PR #103 的 run `38068501256`、job `114260933172` 都在“统计 UPDATE 失败应回滚新增作业”断言失败；此前 Java 核心测试分别 122/122、117/117 通过，账号鉴权分别 451/451、374/374 通过。PR #102 的人工写边界 helper 已在 GitHub 完整执行通过。

旧服务以 JVM 默认时区格式化查询日期，却将同一事件的 `java.util.Date` 经 `serverTimezone=Asia/Shanghai` 的 JDBC 写入 MySQL `DATE`。在 UTC JVM 的 `2026-10-10T16:41:24Z`，查询日为 `20261010`，实际 JDBC 日期为 `2026-10-11`。查询无法找到刚插入的同日行，后续事件继续 INSERT，故障回归里的 UPDATE 触发器也无法命中。

使用候选 JAR 内 MyBatis 3.5.1、MySQL Connector/J 8.0.28 和隔离 MySQL 8.4.6，执行了不写数据库的 `SELECT CAST(? AS DATE)` 复现。UTC、America/Los_Angeles 默认区在上海午夜前一秒与午夜后的结果发生差异，Asia/Shanghai 一致；原 JAR 在真实 UTC JVM 下还重现了与 GitHub 相同的 HTTP 失败断言。完整 CI 日志、上传结果和只读复现保留在 `.devspace/artifacts/day-stat-write-boundary-1011/backend-ci-pr102-pr103/`，入口为 `diagnosis.json`、`date-jdbc-readonly-probe.log`。

## 最终行为

`TeachingDepartDayLogServiceImpl` 在班级事务锁取得后，只计算一次明确的 Asia/Shanghai `LocalDate`。查询、首次插入和原子增量更新共用其 ISO 日期文本，首次插入的 Mapper 明确采用字符串参数绑定到 `DATE` 列，避免隐式时间戳转换。首次插入仍使用原有 `IdWorker` ID 类型；班级锁、当前读、事务回滚、7 类计数的初始化和原子增量保持原有行为。

既有 HTTP 探针使用 Python `ZoneInfo('Asia/Shanghai')` 生成同样的业务日，不依赖 MySQL 会话的 `CURRENT_DATE`。没有通过强制把 JVM 或数据库改成上海时区来隐藏问题。统计读取使用调用方传入的日期范围；缓存去重语义保持既有行为。这次不包含人工 CRUD 边界、全应用时区改造、数据结构迁移或历史统计修整；已有异常历史行不会自动合并。

## 实际验证

- `AdditionalWorkStatisticsTest` 12/12 与 `AdditionalWorkAuthorizationTest` 14/14，共 26/26，无失败、错误或跳过，Maven package 成功。统计测试包括 UTC/上海/洛杉矶 3 种 JVM 默认区，上海午夜前后、跨年、闰日的固定 Clock；断言查询/插入使用同一日，已有行查询/更新同一日，真实 Mapper 的日期参数为 `StringTypeHandler`。
- 实际 JVM 的 `user.timezone=UTC` 已由 `jcmd VM.system_properties` 核对，JDBC 仍为 Asia/Shanghai。原 JAR 重现 UPDATE 故障断言失败；修复 JAR 的真实 HTTP/MySQL/Redis 回归 80/80 通过，包括同班业务日统计、5 组真实 REPEATABLE READ 双写锁等待、首次日行、已有日行、NULL 计数、单元与作业混合事件，以及任务/统计数据库故障回滚与原数据恢复。
- `python3 -m py_compile api/dev/verify-additional-work-authorization.py` 与 `git diff --check` 通过。没有前端改动。主 Agent 负责最终 CI、提交、推送、PR 和整合验证。

真实 HTTP 在本轮执行时的上海业务日验证当前事件；跨午夜、跨年和闰日的精确时刻由固定 Clock 测试覆盖，不把本次真实 HTTP 宣称为等待实际午夜的验收。全部数据库写入只发生在既有隔离五账号、两班级合成实例，未连接生产。

## 复现命令与证据

工作树：`/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/day-stat-date-boundary`。JDK 与 Maven 使用本项目 `.devspace/backend-runtime/tools/` 已有工具，依赖缓存使用 `.devspace/backend-runtime/m2/`。

```sh
JAVA_HOME=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home \
  /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/apache-maven-3.9.16/bin/mvn \
  -B -ntp -s dev/maven-settings.xml \
  -Dmaven.repo.local=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/m2 \
  -DskipTests=false -Dtest=AdditionalWorkStatisticsTest,AdditionalWorkAuthorizationTest \
  -Dsurefire.failIfNoSpecifiedTests=false clean package

JAVA_TOOL_OPTIONS=-Duser.timezone=UTC python3 api/dev/run-backend.py start \
  --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/daylog-1011 \
  --java-home /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home \
  --log-name backend-date-candidate-utc.log

python3 api/dev/verify-additional-work-authorization.py \
  --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/daylog-1011 \
  --output /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/day-stat-date-boundary-1011/additional-work-authorization-utc.json
```

Maven 命令从工作树的 `api/` 执行，另两条从工作树根执行；启动前必须停止该隔离实例原有且已经核实归属的后端。原候选 JAR、运行元数据和证据哈希保留，未覆盖之前报告。

新证据目录：`.devspace/artifacts/day-stat-date-boundary-1011/`。

- `baseline-candidate.json`、`baseline-backend-process.json`、`baseline-jvm-timezone.log` 与 `baseline-additional-work-utc-ready.log`：原 JAR 和 UTC 真实失败。
- `maven-targeted-final.log`：26 项 Java 与完整打包结果。初次执行的参数类型断言失败日志也保留；最终 Mapper 已明确字符串绑定，最终构建与真实 HTTP 使用同一修复版本。
- `candidate-backend-process.json`、`candidate-jvm-timezone.log`、`additional-work-authorization-utc.log/.json`：修复 JAR、UTC 设置、80 项真实结果与回收断言。
- `source-manifest.json`：5 个实现、测试和探针文件哈希；最终交付记录还绑定说明文档。

此证据说明本地合成运行与技术复核范围，不能替代生产上线或真实师生人工验收。
