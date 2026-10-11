# 作品提交与批改的持久统计（M-01）

旧链条的日统计依赖 Redis 集合。教师作品/反馈先提交，Redis 先标记，日统计后失败，导致失败响应与已保存内容不同，重试永远缺计；学生提交后的 Redis 标记缺失也会重新累计。普通作品改名同样会被误认为首次批改。

现在使用 MySQL `teaching_work_event`，主键为 `(work_id,event_type)`，事件类型是 `SUBMIT` 或 `CORRECT`。作品、历史/反馈、事件、日统计处在同一业务事务；SQL 失败全部回滚。批改仅在请求包含至少一条非空评分/评语时记事件，零分有效，改名/状态变更/空反馈集合不算批改。同一作品重新评分不新增首次批改计数，提交和批改是独立事件。日统计与事件共享同一个北京时间业务日期。

学生提交按当前用户行→作品行→班级行→事件→日统计锁顺序执行；无 ID 的并发首次提交也由用户行锁序列化为同一作品。克隆先固定排序锁接收用户，再锁源/目标作品，与提交顺序一致。教师修改已存在作品从作品锁开始。Redis 不再参与作品事件读写，丢失/错误类型/统计缓存故障都不能决定是否累计。登录会话仍依赖 Redis，因此这里不宣称全 Redis 停机时登录仍可用。

## 旧库迁移是上线前置条件

`api/db/work-events.sql` 只允许受支持的 MySQL 8/InnoDB，验证已有表结构、二进制主键、CHECK 约束及触发器边界；不会自动修复不兼容结构。先停所有应用和管理写入、做私有独立恢复点并验证恢复，再显式运行升级。DDL 不是事务性操作。事件基线和唯一切换凭证在同一 SQL 事务中创建，重复迁移不会把切换后新作品重新标成旧事件。没有切换凭证时业务计数拒绝执行。

对切换前每个绑定班级与任务的作品，分别建立 `SUBMIT`、`CORRECT` 两条 `LEGACY_REVIEW`。不根据“目前是草稿”或“目前没有反馈”擅自推断从未提交/批改，也不把所有旧作业当成已批改。现有 Redis 标记可能早于失败 SQL，删除的标记也不能证明从未累计；旧日统计不能直接对应到每份作品。脚本不清 Redis、不修改原聚合、不补记历史日期。

在维护窗口使用包内 `work_event_review.py export --mysql <client> --option-file <private.cnf> --database <db> --review <new-private.json>` 导出完整待核对集合。导出事实仅含作品状态、反馈/历史行数等索引线索；需独立核对真实作品、历史和 Redis 备份并在每项 `evidence` 写明确证据引用。逐事件选择：

- `READY`：有充分证据确认这一事件从未计入旧聚合。下一次真实提交/批改会在事务中转为 `COUNTED` 并新增一次统计。例如确认未评分的旧作业，首次正常评分仍应计数。
- `LEGACY_UNRESOLVED`：已有旧事件事实或旧标记/聚合存在无法排除的关联。保留旧聚合，后续重试不补计；`counted_day` 保持空，不伪造已计数日期。差异需要后续单独按证据校正，不宣称已消除历史统计误差。
- 证据不足以作出上述决策：保持 `LEGACY_REVIEW`。相关提交/真实批改会失败并完整回滚；这是一项明确上线阻断，不应在未核对的环境中开放该流程。

应用核对用 `work_event_review.py apply` 加相同连接和 `--review`，并提供 `--backup <private-nonempty-backup>`、`--writes-stopped`。工具要求完整、未变化的待核对快照和每项证据，全部决策一个事务应用；输出备份与核对文件 SHA256，不更改旧聚合。保存原始报告、填写后的决策、输出回执；结束前确认 `SELECT COUNT(*) FROM teaching_work_event WHERE event_state='LEGACY_REVIEW'` 为 0。不能自动给真实旧库全部设置 READY。

新空库在创建 schema 后即执行迁移，然后再写新合成 fixtures；新候选包按 `01-schema.sql → 01a-work-events.sql → 02-fixtures.sql` 初始化。正式旧库/包含历史数据的恢复包按显式迁移与核对流程处理。事件表和切换凭证必须随作品及历史统计一同备份恢复，不允许仅恢复作品后清空事件。

## 验证范围

- Java 8：`WorkEventStatisticsTest` 使用实际 Spring 事务、H2 SQL 和生产事件/日统计 mapper，覆盖评分零值、批改/提交 SQL 失败回滚、并发同作品重试、Redis 无参与、提交/批改独立键、北京日期、附加作业、旧事件明确核对和缺失切换凭证。
- 原有 `UnitViewStatisticsTest`、`WorkCloneServiceTest` 回归锁顺序和不相关统计行为。
- MySQL 8.4：`WORK_EVENT_TEST_RUNTIME=<owned-new-runtime> python3 -m unittest discover -s api/dev -p test_work_event_migration.py -v` 在独立 `workevent_test_*` 库中验证 9 项迁移约束、幂等、历史保留和核对决策，完成后只删除这些随机测试库。
- `verify-feedback-preservation.py` 新增真实任务绑定、日统计 SQL 故障回滚、8 并发批改、Redis 错误类型与标记丢失；`verify-work-submission.py` 新增事件状态比较、8 并发已有作品重试及 8 并发无 ID 首次提交。
- HTTP/MySQL 整合、真实浏览器教学闭环及最终候选 CI 由组合候选统一执行，不能将本地 H2 或迁移测试当作这些已通过。生产迁移和生产历史核对未执行。
