# 单元浏览统计的可重试事务

`unitViewLog` 原来先把 `(班级, 单元)` 写入 Redis 长期集合，再更新班级每日统计。统计失败后留下的标记会让重试直接返回成功，并发检查和写入也没有原子性。本修复保留每个班级对一个单元只累计一次的长期语义。

当前用户从数据库重新读取，严格保留原 `userIdentity == 2` 的计数条件：2 是上级身份，1 是普通成员（通常为学生）。仅有效的身份 2 账户进入统计；身份为空或为 1 的请求合法返回但不计数，未扩大统计到普通学生。单元必须存在且 ID 与保存值精确一致，课程、单元和班级未删除，并且当前账户所属班级已分配该课程。账户加入多个适用班级时沿用单班级计数模型，按班级 ID 选择第一个适用班级。未分配班级的共享课程可由原阅读流程打开，但不会通过此统计接口新增班级事件。

服务在已有的 `SysDepart FOR UPDATE` 锁下读取持久事件，保持与其他每日教学事件共用的串行边界。新事件 `COUNTED` 与 `teaching_depart_day_log.unit_open_count` 写入同一个数据库事务，失败时全部回滚；成功提交但响应丢失后，同一个请求重试读取事件，不再次增加计数。事件主键为 `(depart_id, unit_id)`，不包含用户或日期；计入日使用同一次上海业务日期计算。保证以事务和主键为依据，不以 Redis 成功或删除失败标记为依据。

新 `recordUnitView` 入口显式使用 `READ_COMMITTED`。真实 MySQL 的空事件表在默认 `REPEATABLE_READ` 下，对两个班级不存在事件的锁定查询会同时持有 gap lock，随后互相阻止插入；普通合法并发已经复现此死锁。局部 `READ_COMMITTED` 消除这种不存在记录的 gap lock，班级行锁仍串行同班级事件，锁定查询仍在等待后读取已提交事件，组合主键继续限制重复。已有 `addLog` 与其他统计入口的隔离级别不改。MySQL 对此隔离级别要求启用 binlog 时使用 `ROW`，`MIXED` 会自动选择行日志，不能假定目标的 `STATEMENT` 日志配置兼容；见 [MySQL 隔离级别说明](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html)。本轮合成环境确认为 MySQL 8.4.6、全局 `REPEATABLE-READ`、`log_bin=1, binlog_format=ROW`，没有检查或修改生产配置。

## 旧数据的边界

迁移只新增 `teaching_unit_view_event`，不清理旧 Redis 集合，不改变已有统计，不自动回填成功事件。

首次遇到没有持久事件的班级与单元组合时，以原来的 Redis key/成员序列化读取长期标记。查到旧标记时保存 `LEGACY_UNRESOLVED`，`counted_day=NULL`，不增减统计，并返回业务 `code=409, success=false`。后续即使 Redis 标记消失，该持久状态仍保留。Redis 查询异常或返回未知结果时不假装没有标记，整笔请求失败，可以在恢复后重试。

旧标记无法证明历史计数成功：原程序在统计前写标记。聚合计数也无法反推出某个单元究竟成功还是失败。因此需要另外保留可核对证据后单独处理历史事件；本轮不提供自动裁决、重新计数或清空状态的入口。曾在升级前丢失的 Redis 标记同样无法逆推，这个修复不能重建不存在的历史证据。新事务保证适用于切换后纳入持久事件的请求。

HTTP 继续沿用项目 `Result` 业务码约定，历史待核对返回 HTTP 200 内的业务 409。`UnitViewModal.vue` 在显示正文之后独立发起统计，并已有 `!res.success` 与 promise `catch` 处理，因此统计失败只显示提示，不阻断正文、视频或文件阅读。

## 迁移与发布边界

`api/db/unit-view-events.sql` 显式执行，支持 MySQL 8.0.16+ 的 MySQL 8 系列。先检查统计表和部门表使用 InnoDB；已有事件表必须匹配列、二进制 ID 排序规则、组合主键和强制 CHECK 定义，未知结构拒绝执行，不自动改表或删行。支持重复执行和共享升级脚本的只检查模式。

合成本地环境在导入 69 张原始结构表之后应用该迁移，再由 fixture seed 应用现有 registration profile 迁移，默认完整 fixture runtime 共 71 张表（不 seed 时为 70 张）。CI review 阶段重复应用两次。注册 CI 和候选/正式发布包把该迁移放在现有两项注册迁移之后，注册 profile 加事件表后共 71 张表。数据库容器初始安装包括第 05 项初始化脚本；已有数据库的升级清单包括第 03 项显式升级脚本，并保留校验、停止写入、私密备份与恢复验证的原有门禁。

升级必须停止旧版本写入，并使服务版本和数据库结构配套切换；旧进程不识别持久事件，混用旧、新版本仍可能重复计数。保留 Redis 历史集合直到有证据的核对另行完成。升级 DDL 隐式提交，不声称可由应用事务自动回滚。本轮只修改迁移源文件、打包接入并在独立合成环境测试，没有生产迁移或部署。

## 聚焦验证

`UnitViewStatisticsTest` 用真实 Spring 事务代理、JDBC 数据库和生产 Mapper SQL 验证事件与统计原子性、统计写入后失败回滚与重试、零影响行回滚、提交后重试、并发首访、跨日/跨成员长期去重、旧标记持久待核对、Redis 查询失败、有效账户/课程/单元/班级与成员关系边界及普通学生 no-op。H2 事务验证与真实 MySQL 迁移检查分开报告。

`TeachingDepartDayLogWriteBoundaryTest` 继续验证禁止人工写统计，并补充历史待核对的业务码与缺失 principal 的拒绝。

真实 MySQL 迁移回归仅在显式指定的独立合成环境运行：

```sh
UNIT_VIEW_TEST_RUNTIME=/绝对路径/.devspace/unit-view-retry-1011 \
  python3 -m unittest discover -s api/dev -p 'test_unit_view_migration.py' -v
```

该回归验证只检查不建表、重复执行保留历史计数和事件、主键与状态约束、生效的二进制 ID，以及不兼容主键、宽松替代 CHECK、多余 UNIQUE/CHECK、触发器、非事务统计表的拒绝。

`api/dev/verify-unit-view-statistics.py` 已接入 `ci/review_mysql.py`，用真实 Shiro HTTP 验证合法身份 2 成员首访、同班级与跨班级 12 并发、普通重试、普通学生不计数、旧 Redis 标记业务 409 与正文可读性。跨班级首次并发在其他事件插入之前执行；报告记录运行前事件数量，在新环境可直接证明覆盖空事件表。脚本备份并恢复受影响业务行和 Redis 长期集合，保留正常 audit，并核对恢复前后摘要。运行方式如下，`--output` 必须指向不存在的证据文件：

```sh
python3 api/dev/verify-unit-view-statistics.py \
  --runtime /绝对路径/.devspace/unit-view-retry-1011 \
  --output /绝对路径/.devspace/unit-view-retry-1011/validation/unit-view-http.json
```

本修复未重跑此前被平台中止的额外 HTTP 故障注入。方法与事务级合成异常验证、真实 MySQL 迁移验证、普通合法 HTTP 并发分别保留证据，不能据此声称生产迁移或部署完成。候选打包的 Nginx 固定摘要门禁在基线即不匹配当前文件，未改变该信任边界；迁移清单的独立通过不能代表完整候选包通过。
