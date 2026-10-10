# Shiro 1.13 维护专项测试记录

本次真实应用上下文及容器分派专项通过 **49/49**。实际候选 JAR 的新增 HTTP 专项为 **15/16**：唯一失败是已热缓存的身份在账号冻结后仍被旧 JWT 使用。正常管理员冻结接口在旧、新 JAR 上均复现，作为既有缺陷留给后续 PR；本报告不将该项改成通过，也不把本机工程验证等同于生产安全或人工验收。

候选 JAR SHA256 为 `232508e514d6221fda0f64975936e22ed370e8fe7eb29eea7e1c3bbc798bda8e`。旧 PR43 JAR 为 `c2898fa71e75294fe03bc1401388a7c50126c2964030c3739dd949c840a9a364`。测试仅使用获授权的 `shiro-1003` 合成运行环境；没有访问其他运行环境或生产。净化 JSON 不包含账户、JWT、响应正文或私有应用启动日志，比较记录中的本机项目根路径替换为 `$PROJECT_ROOT`。

| 证据 | 结果 | 实际覆盖与边界 |
| --- | --- | --- |
| [真实上下文](evidence/shiro-maintenance/context-final.json) | 49/49，launcher 正常 exit0 | 从精确 JAR 提取 classes、资源和依赖，启动真实 `JeecgApplication`，绑定随机 loopback port0；核查 BeanFactory、Tomcat、MVC 和真实 HTTP 分派。 |
| [新增 HTTP](evidence/shiro-maintenance/http-maintenance.json) | 15/16 | 常驻精确候选 JAR；空格、加号、百分号媒体文件返回授权的完整字节及 no-store；有限非法路径拒绝、optional JWT 拒绝无效输入、无害 rememberMe 输入不能认证且无 rememberMe Set-Cookie。已知账号缓存失败保留。 |
| [仅 SQL 状态复核](evidence/shiro-maintenance/disabled-account-sql.json) | 3/4 | 库中 status2 已确认，但旧 JWT 仍为 HTTP200/APIcode0/success=true；没有清用户缓存。状态在 finally 恢复。 |
| [正常冻结新包](evidence/shiro-maintenance/account-freeze-new.json)、[正常冻结旧包](evidence/shiro-maintenance/account-freeze-old.json) | 各 5/6 | 通过现有管理员 frozenBatch 接口冻结和恢复；两包均实际改库，冻结后均仍返回 200。不是只用 SQL 绕开正常入口得到的观察。 |
| [有界包切换与还原](evidence/shiro-maintenance/account-freeze-package-comparison.json) | 旧包与还原后的新包均 health UP | 使用已有 owned run-backend 守卫，仅暂切 18165；旧 PID42211 已停止，新候选恢复 PID42297。18166 与其他环境未改动。 |

上下文确认 `shiroFilter` 与 `shiroFilterFactoryBean` 是同一 FactoryBean 的别名且产出同一 filter；实际 Tomcat 仅一个 Shiro filter，官方 registration order1，映射 `/*` 和 REQUEST/FORWARD/INCLUDE/ERROR。filter、手工 `DefaultWebSecurityManager`、应用 `ShiroRealm` 与 advisor 使用原来的同一管理器，rememberMe manager 为 null，session storage 保持关闭。

真实已解析的每条 Shiro 链都以实际 `invalidRequest` 开头，media、optional JWT 和最终 JWT 三类规则的顺序与 filter 类型均保持。有限 traversal、分号、编码反斜杠等 proxy request 检查只作为补充；真正容器分派通过 test-only servlet 验证：匿名 `.js` 入口 forward/include 到最终 JWT 私有 servlet，418 ErrorPage 也分派到该 servlet。order0 测试观察 filter 只计数并继续 chain，不做授权决定。四种 dispatcher 均实际观察到，私有 servlet 执行数始终为零。direct、forward、error 返回 401；include 外层状态为 200，但正文是 JWT 拒绝且目标未执行。因此不能只拿 include 的外层状态判断授权。

实际主 `requestMappingHandlerMapping` 的 602 个 handler 使用 `ShiroUrlPathHelper`。官方 [ShiroRequestMappingConfig 1.13 源码](https://raw.githubusercontent.com/apache/shiro/shiro-root-1.13.0/support/spring/src/main/java/org/apache/shiro/spring/web/config/ShiroRequestMappingConfig.java) 给构造器注入的单个 mapping 设置 helper，并没有遍历所有辅助 mapper。Springfox mapper 保留普通 `UrlPathHelper`；其 superclass registry 为零，但私有活跃 registry 有 `/v2/api-docs` 的 `Swagger2Controller`，已只读列出，不能从 getter 零推导“没有活跃路由”。Actuator `ControllerEndpointHandlerMapping` 的 superclass registry 为零。实际 Swagger 文档按原匿名规则返回 200，`/actuator/metrics` 无 JWT 返回 401；二者分号路径初始被 invalidRequest 发出 400，随后 ERROR 分派再次被 JWT 拒绝，最终为 401。没有观察到辅助 mapper 绕过保护的行为，本专项不穷举所有辅助路由的 canonicalization。

中文媒体文件名属于既有限制：补充 proxy request 在 decoded path 上被 invalidRequest 以 400 拒绝，常驻新包实际请求最终为 401，文件字节未返回。`blockNonAscii` 未关闭，这些 observations 不计作中文文件名支持通过。身份缓存缺陷也明确保留：独立只读审查确认相关旧、新产品 class 同字节，且冻结路径没有逐用户 cache eviction；本次真实 old/new 正常入口对照进一步证实两包都存在该行为。后续修复应单独验证提交后缓存一致性，不能通过在本测试中清缓存把失败变绿。

早期误断言、观察 filter 次序和 JVM 收尾失败见 [夹具过渡记录](evidence/shiro-maintenance/context-fixture-transitions.json)。完整净化原记录留在私有 `shiro-1003/logs/shiro-context*.json`。定位标记证明 49 项完成且 context.close 完成后 JVM 未自动退出，但没有定位滞留线程来源；最终 test launcher 仅在 close 和结果输出完成后显式退出。wrapper 有 120 秒上限、回收自有进程，并拒绝将非零 exit 与全真 checks 合并成绿。

所有新增媒体文件及引用行均已清理、sys_config 原快照一致；每次账号禁用均在 finally 恢复并复核恢复后旧 JWT 返回正常；FixtureApi 关闭时退出测试登录。短 context PID39344 正常退出，新包恢复且 health UP 后释放串行认证与写库测试窗口。最终冻结测试源码见 [SHA 清单](evidence/shiro-maintenance/test-source-inventory.json)。后续仅加了非零 launcher exit 守卫、明确未知线程来源的注释及恢复请求异常时的 finally 保护，未重跑无关的 752 项既有回归。

可复现入口为 [verify-shiro-maintenance.py](../../api/dev/verify-shiro-maintenance.py) 和 [test-only Java launcher](../../api/jeecg-boot-module-system/src/test/java/org/jeecg/maintenance/VerifyShiroMaintenance.java)。从本分支根目录运行；变量指向已有、具 owned 元数据的合成运行环境和 Java8，不创建账户或修改生产：

```sh
python3 api/dev/verify-shiro-maintenance.py --phase context \
  --jar api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar \
  --java-home "$SHIRO_JAVA_HOME" --runtime "$SHIRO_FIXTURE_RUNTIME" \
  --output "$SHIRO_FIXTURE_RUNTIME/logs/shiro-context-recheck.json"

python3 api/dev/verify-shiro-maintenance.py --phase http \
  --jar api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar \
  --runtime "$SHIRO_FIXTURE_RUNTIME" --actor "$SYNTHETIC_ACTOR" \
  --output "$SHIRO_FIXTURE_RUNTIME/logs/shiro-http-recheck.json"

python3 api/dev/verify-shiro-maintenance.py --phase frozen \
  --jar api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar \
  --runtime "$SHIRO_FIXTURE_RUNTIME" --actor "$SYNTHETIC_ACTOR" \
  --manager-actor "$SYNTHETIC_MANAGER_ACTOR" \
  --output "$SHIRO_FIXTURE_RUNTIME/logs/shiro-frozen-recheck.json"
```

context 和 HTTP 阶段必须与该环境的认证/写库测试串行；已知冻结缺陷存在时，`http --actor` 与 `frozen` 返回非零是预期保留的失败信号。
