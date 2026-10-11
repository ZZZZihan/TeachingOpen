# 文件首次引用与删除竞争

基于 `93d4cfe8e911bccbaf1d20094357fa0b88076a86`，处理 Pro 首轮报告的文件删除一致性 Medium。未改变生产配置或持久访问设置。

## 复现与最终行为

`FileDeletionConcurrencyTest` 使用真实 H2 行锁、Spring 事务、JDBC mapper 适配器，执行实际 `SysFileServiceImpl` 和 `TeachingWorkAttachmentAccessService`。同步屏障固定“引用写方持有文件行锁、删除方开始删除”顺序。修复前断言 `a held reference lock must protect the physical bytes` 失败：删除请求在等待文件行锁前已经删除字节。[原始失败日志](evidence/file-delete-reference-20261012/before.log)。这不是生产攻击验证。

删除现在以相同的 `sys_file FOR UPDATE` 行锁检查引用。一个独立的 READ COMMITTED 事务先提交 `del_flag=1` 待清理记录，第二个独立事务才清理物理对象和元数据。引用先提交，删除看到已提交引用并拒绝；删除先取得锁，新引用看到待清理记录或文件缺失并拒绝。追加作业本地 URL 引用也锁定注册文件，按 ID 排序，并拒绝待清理记录。

物理 I/O、元数据 DELETE 或提交失败均返回清理未完成；已提交的待清理记录允许同一所有者重试。首个事务回滚不会删除字节。元数据清理失败后再次遇到已缺失的物理对象，可完成幂等清理。本地字节与文件详情拒绝待清理记录，包括管理员直接读取；所有者和管理员的管理列表保留待清理记录以便重试。

`/system/sysFile/delete`、`deleteByPath`、`deleteBatch` 延用所有者/管理员授权。批量仍限制 1–100 个 ID，先授权全部记录，再逐条清理；失败结果说明已清理数量与重试方式。清理失败的业务响应为 HTTP 200、`success=false/code=409`，不宣称字节已清理。未扩展普通用户的文件管理范围。

## 验证

- [修复后原始日志](evidence/file-delete-reference-20261012/after.log)：54 项 Java 测试通过，无失败、错误或跳过。
- 新增 `FileDeletionConcurrencyTest` 6 项：双向竞争、物理清理失败、首个事务回滚、元数据清理失败及重试、正常本地删除。
- 新增 `FileDeletionReadBoundaryTest` 2 项：待清理字节拒绝匿名/所有者/管理员，所有者可重试但不能读取详情，其他所有者不可重试。
- 扩展 `LocalFileReferenceAuthorizationTest`，连同 `WorkAttachmentAuthorizationTest`、`WorkCloneServiceTest`、`AdditionalWorkAuthorizationTest` 验证合法写引用兼容性。
- `python3 -m py_compile api/dev/verify-file-deletion-concurrency.py` 和 `git diff --check` 通过。

命令：Java 8 下在 `api/` 执行 Maven `-pl jeecg-boot-module-system -am -DskipTests=false -Dtest=FileDeletionConcurrencyTest,FileDeletionReadBoundaryTest,WorkAttachmentAuthorizationTest,LocalFileReferenceAuthorizationTest,WorkCloneServiceTest,AdditionalWorkAuthorizationTest -Dsurefire.failIfNoSpecifiedTests=false test`。

新增 `api/dev/verify-file-deletion-concurrency.py --runtime <isolated-runtime> --jar <candidate.jar> --output <report.json>`：真实教师 HTTP edit/delete，临时 MySQL 触发器与命名锁固定屏障，读取 `performance_schema` 证明真实行锁等待；双向顺序各重复三次；本地目录拒绝 unlink 和元数据 DELETE 故障均验证待清理记录及所有者重试。`--expect-legacy` 仅演示旧候选的竞争。临时目录、行、触发器、锁均在 finally 清理，并比对原业务行和上传字节。HTTP 探针在本提交时尚未执行，等待共享合成运行环境。H2 不替代 MySQL 验收；Qiniu 调用仅 mock，未访问真实外部存储。
