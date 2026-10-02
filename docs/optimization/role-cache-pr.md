# 权限缓存使用配置指定的 Redis 数据库

当 `spring.redis.database=1` 时，Spring 的缓存清理使用 DB 1，但现有 `ShiroConfig` 创建的 `RedisManager` 没有设置 database，仍将权限缓存写到 DB 0。真实对照中，将合成管理员的角色改为教师后，调用实际退出接口并重新登录，旧管理员权限仍被使用。

现在 Shiro 读取 `spring.redis.database` 并传给 `RedisManager.setDatabase`；未配置时默认 0。沿用项目当前 `shiro-redis 3.1.0`，通过实际依赖的 `javap` 签名核对该方法并完成编译，没有升级依赖或修改 Redis 服务。此 PR 基于课程管理权限 PR #8。

## 验证及边界

使用独立合成环境的实际后端、HTTP 登录/退出、数据库角色行和 Redis 缓存读回。对照前后各 11 项检查：

- 修复前：DB 0 出现权限缓存；配置指定的 DB 1 没有该缓存；角色改为教师并退出重登后，管理列表仍返回成功。这些是预期旧行为的重现，不是旧版本安全通过。
- 修复后：权限缓存写入 DB 1；实际退出删除该条缓存；角色改为教师后重新登录，管理列表被业务码 510 拒绝。恢复管理员角色并退出重登后重新允许。
- 被测的“角色变更 → 退出 → 重登 → 访问”过程中没有直接删除缓存。只在测试开始和结束时清理指定合成账号的缓存；不清空 Redis 数据库，也不修改其他账号。
- 原角色恢复，临时测试会话退出；检查脚本绑定已核实的隔离数据库、Redis 实例及实际候选 JAR。

结果：修复前预期旧行为 **11/11**，修复后 **11/11**，新 JAR 上的课程管理组合回归 **188/188**。证据：[修复前](evidence/role-cache/before.json)、[修复后](evidence/role-cache/after.json)、[与课程管理的组合回归](evidence/role-cache/course-management-combined.json)、[源码和 JAR 摘要](evidence/role-cache/candidate.json)。组合回归在新 JAR 上重新执行；前置 PR 的旧结果不代替新候选结果。

干净 Maven 三模块构建成功；Java 测试被父 POM 跳过，权限行为由上述独立实际检查验证。Python 语法及 Git 差异检查通过。本轮实测配置为单机 Redis DB 1；没有验证 Redis Cluster、生产角色编辑器或所有业务权限立即撤销路径。

## 复现

按 [独立运行说明](../../api/BUILDING.md) 构建、启动含五个合成账号的新隔离环境，然后执行：

```sh
python3 api/dev/verify-role-cache.py --runtime "$TEACHING_RUNTIME" \
  --output "$TEACHING_RUNTIME/role-cache-check.json"
```

基线复现使用同一脚本，传 `--jar` 指向实际运行的 PR #8 JAR，并加 `--expect-legacy`。脚本只支持已确认数据库配置为 1 的合成环境。

## 配置与发布影响

数据库结构不变，业务和缓存继续使用原有配置。采用非零数据库的环境在升级后会重新建立权限缓存，旧 DB 0 中的同名缓存不再用于该候选；不要把旧权限缓存复制过去。未在生产执行升级、缓存清理或重启。回退到前置代码会恢复数据库不一致的问题，需要作为安全风险判断，不能仅以服务启动成功判断回退可用。
