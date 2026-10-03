# 账号冻结专项测试记录

2026-10-03，独立测试 Agent 对根 Agent 创建并启动的本机合成环境执行了账号冻结专项。最终候选 JAR 的 38 项行为检查全部通过，进程退出码为 0；旧 PR54 JAR 的 38 项对照检查只有 10 项通过。旧失败、夹具修正前的失败以及候选首次失败都保留在本报告关联的 JSON 中，未改为预期失败后计入通过。

产品实现及构建由 author Agent 执行。本文作者只编写测试和记录证据；根 Agent 负责协调构建窗口、启动/切换 JAR、运行既有回归与有限延迟基准，独立 reviewer 负责源码和打包内容核查。本文没有把这些不同证据来源合并成人工验收或生产验证。

| 本机实际运行 | JAR SHA256 | 结果 | 净化证据 |
| --- | --- | --- | --- |
| 旧包初轮 | `232508e514d6221fda0f64975936e22ed370e8fe7eb29eea7e1c3bbc798bda8e` | 9/36，退出 1 | [baseline-initial.json](evidence/account-freeze-state/baseline-initial.json) |
| 旧包补完整行恢复、缓存失效观察后的对照 | 同上 | 10/38，退出 1 | [baseline-final.json](evidence/account-freeze-state/baseline-final.json) |
| 新包初轮 | `bca9e5c8f1aa78ab536901e92e2ae3d96433ad0eb4c7599bdaf12174c2c785af` | 37/38，退出 1 | [candidate-initial.json](evidence/account-freeze-state/candidate-initial.json) |
| 新包纠正权限业务码判据后的最终专项 | 同上 | 38/38，退出 0 | [candidate-final.json](evidence/account-freeze-state/candidate-final.json) |

测试入口为 [verify-account-freeze.py](../../api/dev/verify-account-freeze.py)，最终 SHA256 为 `5f887bfc5c576a14a6b7e16fdab2312482391ecb2ff0dafc1c5f432bf21e579f`。证据文件的 SHA256 与分母校验在 [specialist-manifest.json](evidence/account-freeze-state/specialist-manifest.json)。

## 实际覆盖与判据

测试只接受 `account-freeze-1003` 的固定独立端口 13367/16440/18167/18168；沿用已有 FixtureApi 的数据库、Redis 目录、应用 PID、配置、JAR 路径与哈希守卫。只操作原来的五个合成账号。登录凭据和 JWT 留在内存中，缓存身份原值通过 Redis stdin 回填，完整用户行快照留在私有内存中，均未写入本报告或共享证据。

- 先预热正常身份缓存并验证业务成功、实际通知 Socket 认证，再通过正常管理员 `frozenBatch` 冻结。DB 状态变为 2，原 JWT 返回 401；已建立的 Socket 在心跳重查时以 1008 关闭。HTTP 返回后用户缓存为空，直接观察到本次成功调用的缓存失效。
- 冻结后回填真实预热的 status=1 旧身份缓存，实际 HTTP 和新 Socket 仍拒绝。通过正常端点解冻至 DB 状态 1 后，再回填由原值构造的 status=2 变体，原 JWT 的业务请求和新 Socket 均成功。解冻调用返回后也观察到用户缓存为空。
- 只给合成管理员临时授予 `user:status`。同等级、缺该权限的普通操作者被拒绝，返回 HTTP 200 / `success=false` / 业务码 510，五个账号的完整行摘要均未改变。
- 数字/字符串合法状态、trim、重复 ID、空片段和尾逗号按既有字符串契约处理；同状态请求成功且完整行不变。字面 null 请求体、缺/空 ids、数组 ids、缺/null/非法状态均拒绝且完整行不变。
- 含有效目标与缺失目标的批次全部拒绝。临时提高非操作者目标角色等级后，有权限但等级不足的混合批次也全部拒绝。短暂把非登录目标的存储用户名改为精确 `admin`，冻结和解冻两个目标状态都拒绝，混合批次完整行不变，随后还原。
- 专属 MySQL `BEFORE UPDATE` 触发器在第二个目标上抛有限合成 SQL 错误。非事务 MyISAM 记录表只存目标槽位，实际得到 `[1,2]`，证明第一目标更新已进入后才触发第二目标失败。候选返回业务失败且不回传合成 SQL 细节，五个合成账号的完整行摘要与调用前完全相等，包括 `update_by`/`update_time` 等审计字段。此路径经过实际 HTTP、应用的 Spring service 和真实 MySQL，没有测试代理或生产诊断接口。
- finally 恢复五个账号完整行、角色等级、权限关联，关闭所有 Socket、登出、删除专属触发器与记录表。最终候选和最终旧包对照均确认全部原有数据库行和表结构相等（仅排除正常新增的 `sys_log`）。

## 保留的修正与证据边界

旧包初轮的恢复项失败，原因是原夹具只恢复状态、用户名及登录自动初始化的 `org_code`，没有保存 MyBatis 更新时自动填入的 `update_by`/`update_time`。已核对 `MybatisInterceptor` 的真实更新行为，改为五个账号完整行内存快照，并把所有“拒绝不变”和“回滚不变”判据改成完整行摘要。初轮 9/36 仍保留；修正后的旧包 10/38 完成了完整恢复检查。首轮审计元字段变化不能被描述成“全量数据已恢复”。

候选初轮唯一失败是测试预设缺权限业务码为 403。实际 `JeecgBootExceptionHandler.handleAuthorizationException` 调用既有 `Result.noauth`，而 `CommonConstant.SC_JEECG_NO_AUTHZ` 明确为 510。测试已据此修正并独立记录 `success=false` 和完整行不变，未改产品。旧对照记录的业务码是 200，按正确 510 判据仍然失败，旧 10/38 数量不变；但旧对照与最终候选的脚本并非完全相同字节版本，不能作此声称。

两向 Redis 回填是确定性的陈旧缓存输入测试，没有复现自然并发调度、未提交事务期间的缓存命中或并发 miss 的迟到 put。测试观察的是正常 HTTP 调用返回后的缓存为空，没有追踪 Spring `afterCommit` 回调内部时间。实际通知 Socket 与普通 JWT 都调用 ShiroRealm；未发现产品调用 `TokenUtils.verifyToken`，没有把此专项称为 TokenUtils 直接调用验证。没有独立 Java context/代理 harness，也没有额外测试数据库身份 status=null、逻辑删除或身份不存在。请求参数 null 与数据库身份 null 是不同范围。

本专项未运行浏览器/CAPTCHA 人工交互、真实用户、生产环境、压力测试或容量验收。新增每次认证查询的有限本机延迟对照与 249 项相关既有回归由根 Agent 独立记录，不从本专项的 38/38 推导性能或全产品结论。

复现需先由环境所有者按现有运行守卫启动相应精确 JAR 并授予串行测试时段，使用新的输出文件名：

```sh
python3 api/dev/verify-account-freeze.py \
  --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/account-freeze-1003 \
  --jar /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/account-freeze-state/api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar \
  --output /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/account-freeze-1003/logs/account-freeze-rerun.json
```

输出文件采用 0600 且拒绝覆盖已有证据；脚本不启动/停止后端，不访问其他 runtime，不增加产品后门或依赖。
