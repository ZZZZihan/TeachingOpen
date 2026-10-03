# Scratch 云变量冷备份恢复记录

2026-10-03，工作树 `scratch-cloud-recovery`，分支 `feature/scratch-cloud-recovery`，起点 PR45 `5f896ac`。本记录为产品实现 Agent 自检；测试 Agent 的用例结果及 root 的实际环境演练分别记录，不作为用户验收。

原格式 1 明确排除全部 Redis，遗漏了 Scratch 作品存于 DB 1 `scratch:cloud:<workId>` hash 的业务值。Java 使用字符串字段和 Spring JSON 值序列化，本改动不改 Java、UI 或原环境配置。

改动仅为 `local_recovery.py`、新 `scratch_cloud_recovery.py`、`backup-local.py` 和 `api/BUILDING.md`：

- 新格式 2 绑定私有 `cloud-values.json` 的 SHA-256/字节数及云键/字段计数。键、字段和值按规范 base64 保存原字节，包括 NUL、换行、非 UTF-8 字节、Unicode、空字段/值；不重新解析或序列化 Spring 业务值。
- 使用标准库 RESP2 二进制连接；私有凭据只用于 AUTH，不进入命令行或输出。实际 Redis 的目录、bind、port 与本机 runtime 完全相符且配置 DB 1 后，才读取业务命名空间。
- 已停应用和其他业务写入程序的 MySQL 读锁期间，两次 Lua 原子抓取严格比较全部允许云键，再发布完整 manifest。失败不发布有效完成清单；不把双检查称为跨 MySQL/Redis 事务。
- 全新恢复目标要求 DB 1 为空，结构/摘要校验后仅恢复 `scratch:cloud:*` hash；数据库、附件、云字节一致才写 `restore-result.json`。不恢复登录令牌、验证码、权限缓存和其他 Redis 键，不覆盖已有目标。
- 旧格式 1 继续支持 inspect/restore，CLI 明确标记 `cloud_data_present: false`、`legacy_cloud_missing: true`，恢复 `cloud_equal: null`，不会宣称旧云值已恢复。

范围与拒绝策略：现有云代码没有 TTL，要求 `PTTL=-1`；正 TTL、错类型、悬空作品、异常/重复文档属性和超限数据整份拒绝，不静默过滤。保留所有已有作品 ID，不按发布状态或删除标记筛选。限 10,000 键、每 hash 64 字段，键/字段/值分别 1,024B/4,096B/1MiB，原字节总计 16MiB、实际编码文档另限 32MiB。root 审查发现缩进 JSON 可能超过文档限制，已在创建目标目录前检查实际编码长度；RESP 回复也有累计字节/节点上限。

本 Agent 已执行：三个 Python 产品文件 `py_compile`、`git diff --check`、CLI `--help`，均退出 0。`admin_tests` 编写并报告最终定向测试 46/46 通过、CLI 退出 0：28 项 cloud（24 文档及 4 传输分组）和 18 项 local_recovery（原 12 及新增 6 主流程）；覆盖实际编码文档超限/等限、旧格式、非空目标、SQL/cloud 失败与回读不同不发布完成结果。其核对的产品哈希与下列冻结版本一致。这是其他 Agent 的自动化测试结果；root 独占 source/restored 合成环境，实际 Lua/Redis/MySQL/JAR 云协议恢复与组合 suite 由其另行记录。本 Agent 没有启动服务或连接现有真实数据。

冻结 SHA-256：

- `api/dev/local_recovery.py`：`865bee663ca8e8d99626a96bc630a7d7a4e62bc763a5019cc1bc7361915f1942`
- `api/dev/scratch_cloud_recovery.py`：`b41486488d80d01a2430fc1530780f08585eced191fd3b1da435ab586be97e28`
- `api/dev/backup-local.py`：`421ce330e34794e77013e073420f69aed90d598be8b3127067d2cbe628e72317`
- `api/BUILDING.md`：`e9fbf230e5fe146573e4a15a3524d4ab82905a8e3c756ee778bddda89e8f502e`

限制：仅本机可信合成环境的冷备份，不用于生产/在线/跨版本迁移。既有 Redis 仍为 `appendonly no`、`save ""` 临时测试配置；只增加显式快照恢复，普通停止再启动不保证保留云值。系统或 Redis 写入错误可能留下新目标的部分数据供诊断，不自动跨库回滚或清理其他环境。没有提交、推送或创建 PR。
