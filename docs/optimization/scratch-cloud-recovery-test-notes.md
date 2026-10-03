# Scratch 云值恢复测试记录

测试 Agent 使用 GPT-6.1-sol / Ultra。工作树为 `scratch-cloud-recovery`，基线为 PR45 `5f896ac`。测试 Agent 没有连接、启动或修改真实 runtime，没有提交代码。产品实现由 UI Agent 编写，真实恢复演练由 root 串行执行。

最终定向回归 **46/46**，两个 CLI 均退出 **0**：`test_scratch_cloud_recovery.py` 28 项；`test_local_recovery.py` 18 项（原有 12、新增 6）。新增共 34 项，`subTest` 的边界输入不重复计数。执行命令（在工作树根目录）：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 api/dev/test_scratch_cloud_recovery.py -v
PYTHONDONTWRITEBYTECODE=1 python3 api/dev/test_local_recovery.py -v
git diff --check
```

覆盖二进制、空字段/值、Unicode/换行，严格 base64/前缀/TTL/孤儿及容量拒绝，RESP 字节传输和错误 Redis 归属关闭连接；覆盖 format2 载荷绑定及重复 JSON 属性拒绝、format1 显式缺云、现有目标拒绝、源值变化和 SQL/Redis/回读失败时不发布完成标记。实际 JSON 编码大小用 patched 小上限检验，超限时快照目录不创建，等于上限允许。临时文件、权限、复制、SHA、格式解析和编码真实执行；数据库/Redis/准备流程使用 mock，不能替代真实恢复。

初次从工作树根目录使用 `python3 -m unittest api/dev/test_local_recovery.py`，因导入路径而出现 loader `ModuleNotFoundError`；改为上面的脚本命令后通过。这是调用方式失败，未计入通过数量。root 的旧工具对照初次固定 120ms drain 过早返回，保留诊断后改为有界 5 秒等实际 ack；该次数不计入本组回归，也不放宽值比较。

只读真实复验脚本为 `api/dev/verify-cloud-recovered.py`，输出仅固定检查名、数量和 SHA，不输出 token、云字段和值。先核对 source/target MySQL 与 Redis 归属、源/目标端口隔离、精确 JAR/profile/config/监听 PID，先读排除项再发匿名握手和旧 token HTTP 请求。握手等 ack/close，最多 5 秒，比较完整 3 个 `set` 值；HTTP 固定 loopback、不跟重定向。脚本不登录、登出、启动、清理或发送云写指令。

```sh
PYTHONDONTWRITEBYTECODE=1 python3 api/dev/verify-cloud-recovered.py \
  --runtime "$RECOVERY_TARGET" --source-runtime "$RECOVERY_SOURCE" \
  --snapshot "$RECOVERY_SNAPSHOT" --jar "$RECOVERY_JAR" \
  --old-session-record "$RECOVERY_SOURCE/old-session-record.json" \
  --project-id fixture_cloud_recovery_public \
  --output "$RECOVERY_TARGET/cloud-recovered-readonly.json"
```

上述四变量必须指向 root 创建的私有合成副本及精确 JAR。目标应刚恢复并启动到健康；执行排除检查前不得先登录/探测 permission，以免本地用户缓存影响初始空库证据。测试 Agent 冻结时真实执行仍待 root 进行；root 后续在冻结版本实际完成 14/14，另完成全部工具 97 通过/1 跳过，见 [交付报告](scratch-cloud-recovery-pr.md) 和 [实际结果](evidence/scratch-cloud-recovery/actual-java-recovery.json)。这些实测由 root 执行，不计作测试 Agent 的独立环境复验，也不声称浏览器或已发布 Scratch 编辑器验收。

最终字节绑定：

| 文件 | SHA-256 |
| --- | --- |
| `api/dev/local_recovery.py` | `865bee663ca8e8d99626a96bc630a7d7a4e62bc763a5019cc1bc7361915f1942` |
| `api/dev/scratch_cloud_recovery.py` | `b41486488d80d01a2430fc1530780f08585eced191fd3b1da435ab586be97e28` |
| `api/dev/backup-local.py` | `421ce330e34794e77013e073420f69aed90d598be8b3127067d2cbe628e72317` |
| `api/dev/test_local_recovery.py` | `03f8ed9c660500b7d0add5722307f7dea5864b3c713b689fe654eb900ba8d821` |
| `api/dev/test_scratch_cloud_recovery.py` | `0839f3f55e5bddaa0a88df5919bb3f0525347fe8c018fc98cee03b25384c7e1f` |
| `api/dev/verify-cloud-recovered.py` | `a7fba53d864ddd6a34691edac066cd972c6c59572413ebbd498c09d584c34f97` |

`git diff --check` 退出 0。产品实现是冷应用备份及全新目标恢复；Redis 原本不持久化，双捕获也不是 MySQL/Redis 跨库事务。异常恢复保留新的部分目标诊断、没有成功结果，不能据此启动业务。旧格式支持恢复 SQL/附件并明确云值缺失，登录/验证码/普通缓存始终不恢复。
