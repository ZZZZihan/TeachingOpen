# Scratch 云变量随本机冷备份恢复

旧备份只保存数据库和附件，却把全部 Redis 当成可丢弃缓存。Scratch 的 `scratch:cloud:<workId>` 保存的是作品业务值。root 在独立合成环境实际复现：69 张表、35 行和 2 个附件恢复一致，作品的 Java 云协议握手也成功，但原有 3 个云变量恢复后成为 0 个。

本改动为独立分支 `feature/scratch-cloud-recovery`，基于 PR #45 的 `5f896ac`。新格式 2 备份 Redis DB 1 中持久化 hash 类型的 Scratch 云变量，按原始键/字段/值字节保存，恢复到全新隔离环境。登录令牌、验证码、权限缓存及其他 Redis 键继续排除。只修改本机开发恢复工具，没有修改 Java、前端或生产配置。

## 实现与范围

`scratch_cloud_recovery.py` 使用标准库二进制 RESP2，认证口令不出现在命令行。核对配置与实际 Redis 目录、bind、端口后才选择 DB 1；Lua 单次原子读取允许的命名空间。在已停应用和其他写入方的前提下，与 MySQL 读锁期间的数据库、附件两次摘要检查配合。两次抓取不是跨 MySQL/Redis 事务。

私有 `cloud-values.json` 保存规范 base64，清单绑定文件摘要、字节数和键/字段数量。所有键必须对应已有作品；不按作品公开/删除标记筛掉业务值。过期键、错误类型、悬空键、异常格式与容量超限整份拒绝。实际 JSON 编码超过 32 MiB 时，在建立备份目录前失败。恢复只接受新目录和空目标 DB 1，SQL、附件、云字节全部回读相等才发布完成结果；失败可能保留部分新目标供诊断。

格式 1 旧快照可继续检查和恢复，但明确输出 `legacy_cloud_missing: true`、`cloud_data_present: false` 和 `cloud_equal: null`，不声称它包含云数据。原 Redis 的 `appendonly no` 和 `save ""` 临时配置保持不变；本项是显式备份恢复，普通停止再启动仍会丢失未备份云值。

## 已执行验证

证据集中在 [安全聚合记录](evidence/scratch-cloud-recovery/validation-record.json)，不包含 SQL、口令、令牌、真实生产内容或云业务值。

- **自动化工具回归：97 通过、1 跳过，共发现 98 项。** 跳过项为另一个生产副本工具的可选真实 MySQL 测试，未在这些合成环境启用。新增相关定向测试 46/46，由测试 Agent 执行；独立审查 Agent 又执行定向测试，无阻断发现。它们包含真实文件/格式操作和 mock 数据库/Redis，不能代替下面的实际演练。
- **旧版实际对照：** 原始 3 个云变量在格式 1 恢复后为 0 个，Java 握手仍 ACK OK；全库和附件保持一致。首次固定 120ms 接收窗口未等到冷启动 ACK，改为最多 5 秒且必须收到 ACK 后重新检查，未改变值断言，失败不计通过。[旧行为记录](evidence/scratch-cloud-recovery/old-behavior.json)。
- **新版实际恢复：** 69 表、35 行、2 附件、1 hash 的 3 个字段逐项一致。真实 Java/JAR 的匿名云握手恢复全部 3 个值；此前在源环境取得 HTTP 200 的合成管理员会话，在目标返回 HTTP 401。源有 4 个非云键，目标最初只有 1 个云 hash；验证读取前后 12 张业务表、附件和云字节不变。14/14 检查完成。[Java 实际结果](evidence/scratch-cloud-recovery/actual-java-recovery.json)。
- **实际拒绝场景：** 分别给自建源加入过期 hash、错误类型、悬空作品键，以及临时错误 Redis 库配置；4 种情况都拒绝且没有建立目标/完成清单。每次临时改动都还原，云字节、69 表、附件和配置与原基线相同。[边界结果](evidence/scratch-cloud-recovery/actual-boundary-checks.json)。
- **实际兼容及字节检查：** 用新工具恢复旧格式 1，69 表及附件相等、云缺失标记正确、Redis 为空。在这个新目标的自建探针键上，经真实 Redis 捕获/恢复确认空字段/值、NUL、无效 UTF-8、Unicode 和换行字节保留，探针随后删除；这不表示任意二进制都能作为 Java 云业务值。[兼容结果](evidence/scratch-cloud-recovery/legacy-binary-checks.json)。
- **资产保护：** 原源码 5,731 项文件摘要相同。[核对结果](evidence/scratch-cloud-recovery/original-source-protection.json)。没有连接或写入生产，没有 GitHub 合并、部署或浏览器登录。

实际演练使用已验证的 #43 JAR，SHA-256 `c2898fa71e75294fe03bc1401388a7c50126c2964030c3739dd949c840a9a364`。本改动没有重新构建 Java，也没有把旧前端结果计作新测试。源会话证明、快照、SQL、日志和凭据只保留在私有 `.devspace`。源与新目标端口分别为 13347/16420/18143、13348/16421/18145；旧对照及兼容目标顺序使用 13349/16422/18147。各目标均从不存在的目录创建，未覆盖既有环境。

## 复现入口

完整冷备份/恢复用法见 [BUILDING.md](../../api/BUILDING.md)。从本分支执行工具测试：

```sh
python3 -m unittest discover -s api/dev -p 'test_*.py'
python3 api/dev/backup-local.py create --runtime "$TEACHING_SOURCE_RUNTIME" --snapshot "$TEACHING_NEW_SNAPSHOT"
python3 api/dev/backup-local.py inspect --snapshot "$TEACHING_NEW_SNAPSHOT"
python3 api/dev/backup-local.py restore --snapshot "$TEACHING_NEW_SNAPSHOT" \
  --runtime "$TEACHING_NEW_RUNTIME" --tools "$TEACHING_TOOLS" \
  --mysql-port 13348 --redis-port 16421 --backend-port 18145 --frontend-port 18146
```

变量必须指向自己建立的可信合成环境和未存在的新快照/恢复目录，不能直接覆盖本轮保留结果。使用新数据前先按工具约束准备五账户标准夹具，加入独立公开测试作品及三项字符串云值，在源通过真实 API 取得合成管理员会话并私有保存 HTTP 200 证明，然后停应用进行快照。后端健康以后、其他认证探针以前执行只读专项：

```sh
python3 api/dev/verify-cloud-recovered.py \
  --runtime "$TEACHING_NEW_RUNTIME" --source-runtime "$TEACHING_SOURCE_RUNTIME" \
  --snapshot "$TEACHING_NEW_SNAPSHOT" --jar "$TEACHING_JAR" \
  --old-session-record "$TEACHING_SOURCE_RUNTIME/old-session-record.json" \
  --project-id fixture_cloud_recovery_public \
  --output "$TEACHING_NEW_RUNTIME/cloud-recovered-readonly.json"
```

该检查不登录或注入浏览器凭据，只验证实际匿名云协议和旧会话拒绝。HTTP 读取可能使应用建立自己的新缓存，故恢复后键集合在探针之前核验。源证明文件含令牌，必须为权限 600 的本机私有文件，不提交 Git。

## 分工与剩余范围

按用户指定，产品实现、测试和独立代码审查均使用 GPT-6.1-sol / Ultra 子 Agent；工具无 Fast 参数，未声称切换 Fast。root 审查实际编码尺寸边界、独占执行真实 MySQL/Redis/JAR 演练和资产保护核查，整理本报告与 PR。详见 [实现记录](scratch-cloud-recovery-agent-notes.md) 与 [测试记录](scratch-cloud-recovery-test-notes.md)。独立代码审查与 root 工程自检均不等于人工验收。

演练结束后，源、新恢复、旧对照和兼容恢复环境的本任务服务均已停止，数据库文件、私有快照和证据保留。Redis 停止不保存临时缓存；成功恢复的业务云值仍保留在格式 2 快照内。原 18111/18141 后端及已有前端预览保留。

本项只适用于本机可信合成环境的停机冷恢复，不是生产灾备、在线一致性或跨版本迁移。生产来源课程副本、已打开页面和其他预览保留；认证三角色、编辑器/媒体完整浏览器流程、用户视觉评阅及其他产品化任务继续推进，Goal active。
