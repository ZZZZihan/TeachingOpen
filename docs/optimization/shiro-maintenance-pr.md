# Shiro Java 8 过渡维护

当前教学后端使用 Shiro 1.7.0，且纯 JWT 认证仍保留默认 rememberMe manager。本项将现有 starter 更新为 1.13.0，显式关闭不用的 remembered identity 入口，并保持原有 JWT、可选 JWT 和媒体 Cookie 认证契约。它基于 PR #43 的 `3fb70f1919289d777ccffe936f3a7a8b889a749b`，不包含后续前端成果。

## 最终实现

- POM 使用单一 `shiro.version` 属性。实际包内 12 个 Apache Shiro 模块全部为 1.13.0；未引入会改变 Spring 依赖管理的 Shiro BOM。
- 同一个自定义 FactoryBean 使用 `shiroFilterFactoryBean` 名称并保留 `shiroFilter` 别名，使 1.13 新增的 Web 自动注册继续使用应用原有过滤链。没有新增第二个工厂或自行覆盖官方注册。
- `DefaultWebSecurityManager.setRememberMeManager(null)` 关闭默认 rememberMe，原有 Subject session storage disabled 保留。业务 `teaching_media` JWT Cookie 与此不同，下载和退出回归单独验证。
- 保留全局路径检查、`/sys/common/static/**` 的优先级以及最终 `/** → jwt`，沿用新版的 MVC 路径适配和四种 dispatcher 注册。

正式产物 SHA-256：`232508e514d6221fda0f64975936e22ed370e8fe7eb29eea7e1c3bbc798bda8e`。Spring Boot 2.1.3、全部 14 个 Spring Framework 5.1.5.RELEASE、Tomcat 三模块 9.0.122 保持原版本。Shiro 的传递依赖 OWASP encoder 从 1.2.2 变为 1.2.3；其他 195 个外部库逐字相同。462 个应用/公共模块 class 中只有 ShiroConfig 改变。[包与源码清单](evidence/shiro-maintenance/final-inventory.json)、[库对照](evidence/shiro-maintenance/packaged-library-diff.json)、[class 对照](evidence/shiro-maintenance/application-class-diff.json)。

## 实际验证

使用全新 `.devspace/shiro-1003`、独立 MySQL/Redis/端口与五个合成账号，未使用生产数据库。Java 8 干净构建成功，实际普通启动健康 UP；环境检查 9/9，分支开发工具单元检查 42/42。Maven 构建跳过 Surefire，不计为 Java 单元测试通过。[构建摘要](evidence/shiro-maintenance/build-summary.log)、[环境](evidence/shiro-maintenance/environment.json)、[开发工具检查](evidence/shiro-maintenance/dev-unittest.log)。

在同一最终 JAR 上重新执行十组实际 HTTP/数据库/WebSocket 回归，共 752/752：

| 行为 | 通过 |
| --- | ---: |
| 无凭据、无效凭据、有效登录与退出撤销 | 7/7 |
| Redis DB 1 角色缓存与退出重登 | 11/11 |
| 按认证身份生成菜单、空菜单与故障恢复 | 34/34 |
| 课程管理及三角色边界 | 188/188 |
| 学习单元访问与隐藏资料 | 80/80 |
| 社区作品、可选 JWT 与交互权限 | 235/235 |
| 媒体 Cookie、GET/HEAD/Range、撤销与文件边界 | 88/88 |
| 通知 WebSocket | 44/44 |
| Scratch 云变量 WebSocket | 52/52 |
| JWT 刷新与认证日志不暴露凭据 | 13/13 |

[本轮逐套摘要](evidence/shiro-maintenance/regression-summary.json) 及同目录的十份 JSON 保留具体断言。Scratch 使用当前组合候选的本机代理 18166；该代理和前端 dist 没有在本项修改。测试使用合成账号的真实本地 HTTP 登录，不代表浏览器验证码操作、真实师生验收或生产验收。

专项真实应用 context **49/49**，同一最终 JAR 的手工 manager/factory、唯一 filter、四类 dispatcher 和主业务 MVC helper 均核对。实际 Tomcat 的 REQUEST、FORWARD、INCLUDE、ERROR 四条路径都观察到 JWT 拒绝，私有测试 servlet 从未执行；INCLUDE 的外层 HTTP 为 200、正文为 401 拒绝，不能将四条都写成 HTTP 401。主业务 mapper 有 602 个 handler；Swagger 自有注册表实际有 `/v2/api-docs` 一条，继承 getter 的零不能作为无路由证据。测试 servlet、observer 和 launcher 仅存在于独立短 context，未进入产品 JAR。新增 Cookie/媒体/账号 HTTP 专项 **15/16**，不是全绿：空格、加号、百分号媒体文件字节保持；无效可选 JWT、无凭据和无效 rememberMe Cookie 被拒，配置与文件清理通过。失败项为 SQL 禁用一个已热缓存的合成账号后，其原有效 JWT 仍返回 HTTP 200；定向复核 3/4 保留同一失败。随后通过正常管理员 `frozenBatch` 入口，旧 PR #43 与新 JAR 同样为 **5/6**：冻结 API 成功、库中状态为 2，而旧 JWT 仍返回成功；两次均已恢复账号和最终 JAR。相关八个应用类和 MyBatis 库旧/新逐字相同，`getUserByName` 缓存与冻结入口缺少缓存失效的链已核查。这是实际已存在的账号冻结缺陷，**尚未修复**，保留为下一独立 PR；不能把本次维护描述成账号禁用即时失效或全部鉴权问题已解决。

详见 [专项说明](shiro-maintenance-tests.md) 与 [独立静态审查](shiro-maintenance-review.md)。前两轮 context 的 39/40、43/49 和一次 120 秒测试程序退出超时记录均保留；最后短 context 的 49/49 与退出码 0 单列。源码、真实运行、作者测试及独立只读审查按证据区分。

## 兼容性与后续边界

一次仅导入 Shiro BOM 的候选虽然编译成功，却因 Spring 新旧混用缺少 `ApplicationStartup` 而启动失败；移除 BOM 后，原 factory 名称又导致新版自动注册缺 bean。两次都在独立测试服务中实际复现，最终版本采用上述最小修复。[净化后的失败记录](evidence/shiro-maintenance/startup-compatibility-failures.json)、[作者记录](shiro-maintenance-author.md)。原始日志、失败 JAR、凭据和数据均留在私有工作区。

**1.13.0 仍为 EOL 的过渡版本。** Apache 已结束 1.x、2.x 维护，3.x 要求 Java 17、Jakarta 与新的 Spring/Boot 平台；长期迁移仍是独立待办。本项不能被描述为所有依赖风险已经解决，也没有证明旧系统特定漏洞可利用。[官方 EOL 与平台说明](https://shiro.apache.org/blog/2026/06/apache-shiro-300-released.html)、[安全公告](https://shiro.apache.org/security-reports.html)。

旧 1.7 与新 1.13 的打包代码都默认启用非 ASCII 路径限制，最终候选实际拒绝中文媒体文件名；没有执行旧/新同路径 HTTP 对照，也未据此验收中文文件名支持。该限制单独保留，没有通过关闭路径防护使断言变绿。Servlet session、HTTPS 反向代理 Cookie 行为、生产文件系统、生产定制包、负载与完整三角色浏览器流程仍需对应环境验证。此处关闭的是 Shiro rememberMe，不声称消除了全部 Servlet session。
