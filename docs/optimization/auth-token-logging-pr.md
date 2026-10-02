# 认证事件日志不再记录登录令牌

`ShiroRealm` 原先在 DEBUG 级别的认证校验和 INFO 级别的在线会话刷新中拼接完整客户端令牌。后一条在常规日志级别也会执行；读取日志的人可能取得仍在使用的凭证。原工作区补丁只删除刷新日志，本 PR 同时处理两处，并保留不包含令牌、用户名或密码的事件文本。

此 PR 基于 #10；实现只改两条日志，不改变认证、刷新、过期和退出逻辑，不更新依赖或数据库结构。

## 真实对照

在已核实归属的五账号合成环境中，临时将 `ShiroRealm` 日志级别设为 DEBUG 并重启隔离后端。检查脚本实际生成验证码、登录、访问本班单元；随后只将本次测试会话的 Redis 缓存值替换为正确签名但已经过期的合成 JWT，实际请求触发现有刷新逻辑。检查新缓存有效期、后续访问、退出后缓存删除及旧凭证被拒绝。

脚本只读取本次请求新增的后端日志：

- 修复前 **13/13**：认证 DEBUG、刷新 INFO 事件实际出现，二者都含完整客户端令牌；刷新、退出和拒绝路径按预期工作。这是预期旧行为的复现。
- 修复后 **13/13**：同样的两个事件实际出现，但均不再包含令牌；整个捕获区间也未出现测试的客户端、过期缓存及刷新缓存令牌。认证、刷新、后续访问和退出仍通过，未发现合成密码或其用于签名的存储值出现在本次日志区间。
- 新 JAR 上重新执行学习单元 **80/80**、课程管理 **188/188**、权限缓存 **11/11** 组合检查，临时业务数据及角色恢复。重复结果不计作新增独立用例。
- Maven 三模块干净构建成功；Java 测试被父 POM 跳过。Python 语法、Git 差异和证据摘要通过自检。

结束后移除临时 DEBUG 配置，配置字节与测试前备份一致，并以原配置重启同一候选。所有测试会话退出，刷新测试的缓存项已删除。原工作区、原演示及首页预览服务未改动。

证据：[修复前](evidence/token-logging/before.json)、[修复后](evidence/token-logging/after.json)、[单元组合](evidence/token-logging/learning-units-combined.json)、[课程管理组合](evidence/token-logging/course-management-combined.json)、[缓存组合](evidence/token-logging/role-cache-combined.json)、[候选摘要](evidence/token-logging/candidate.json)。证据只保存判断、数量和源码/JAR 摘要，不保存 JWT、密码或原始日志片段。

## 复现与范围

按 [隔离运行说明](../../api/BUILDING.md) 启动合成环境，备份该环境的私有 `config/application-localtest.properties`，临时添加：

```properties
logging.level.org.jeecg.modules.shiro.authc.ShiroRealm=DEBUG
```

仅重启该隔离后端，然后执行：

```sh
python3 api/dev/verify-token-logging.py --runtime "$TEACHING_RUNTIME" \
  --output "$TEACHING_RUNTIME/token-logging-check.json"
```

基线检查使用同一脚本，传 `--jar` 指向实际运行的 #10 JAR 并添加 `--expect-legacy`。检查结束后恢复配置备份，重启该隔离后端；不要把临时 DEBUG 配置用于生产。脚本绑定隔离数据库、Redis 目录、候选 JAR 和私有日志路径，凭证仅在内存中使用。

本结果只覆盖两条认证日志及该请求区间，不代表所有业务日志、代理访问日志或异常消息已完成脱敏审计；不清理历史日志，也不更改日志保留策略。未合并、未部署、未修改生产。回退会重新记录令牌，应纳入回退风险判断。
