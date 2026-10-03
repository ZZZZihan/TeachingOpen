# Shiro 维护评估

2026-10-03，只读核查；未修改依赖、构建升级包、访问生产或建立空 PR。

当前候选 `2533f669909afdaa059a9ec91179cd4967e2a899` 对应的运行 JAR，SHA-256 为 `c2898fa71e75294fe03bc1401388a7c50126c2964030c3739dd949c840a9a364`。独立子 Agent 核对包内 12 个 Apache Shiro 模块均为 **1.7.0**，Spring Boot 为 2.1.3、Spring 为 5.1.5，仍使用 Java 8 / Servlet javax 架构。源码与该包构建树的认证配置一致；这是已存在产物核对，不是重新构建证明。

Apache 已宣布 Shiro 1.x、2.x 结束维护，3.x 要求 Java 17+ 和 Jakarta，并涉及新的 Spring/Boot 平台。因此不能在当前架构上简单替换为最新版本，也不能把 1.13.0 称为长期受支持版本。[官方 3.0 发布说明](https://shiro.apache.org/blog/2026/06/apache-shiro-300-released.html)

**下一独立维护项建议**：在隔离分支评估 Shiro 1.13.0 作为 Java 8 过渡修补，统一全部模块版本，并核对实际过滤器、MVC 路径适配及未使用的 rememberMe 功能。它可以移出多条旧认证路径公告的受影响版本区间，但不能据此声称本项目已证明可利用，或 2026 年的 session、cookie、大小写路径和 timing 风险全部解决。[官方安全公告](https://shiro.apache.org/security-reports.html)

已发现必须验证的兼容点：1.13 starter 合并了 Web 自动配置，可能改变手工 `shiroFilter`、SecurityManager 条件回退和 dispatcher 注册。需确认只有一个有效过滤器，保留 `jwt`、`optionalJwt`、`mediaJwt` 的顺序与行为。其上游 Spring/Boot 构建基线比当前项目新，尚未证明当前组合能编译、启动。[1.13 POM](https://raw.githubusercontent.com/apache/shiro/shiro-root-1.13.0/pom.xml)、[MVC 自动配置](https://raw.githubusercontent.com/apache/shiro/shiro-root-1.13.0/support/spring-boot/spring-boot-starter/src/main/java/org/apache/shiro/spring/config/web/autoconfigure/ShiroWebMvcAutoConfiguration.java)

本项目仅关闭 Subject session storage，默认 rememberMe manager 仍存在；应用的 `teaching_media` JWT Cookie 与它不同。非 Web starter 打包了 MVC 适配类，也不代表运行中已经加载。本次属于源码和字节码证据，没有读取运行 bean 或进行利用测试。

后续验收至少覆盖：干净构建与隔离启动；确切包版本和单过滤器注册；有效/失效/退出后的身份；三角色权限与 Redis DB 1 缓存；公开和私有资源；GET/HEAD/Range 与合法中文文件路径；只读合成路径和 dispatcher 拒绝；Cookie/session；共用 Realm 的通知及 Scratch WebSocket。不得为兼容测试通过而关闭全部路径检查。实施后仍保留 EOL 风险和 Java 17 / Jakarta / Shiro 3 的独立迁移待办。

完整私有核查在本机 `.devspace/artifacts/shiro-maintenance-audit/report.md`，报告 SHA-256 `45e5a7d52f490734fb5a492d29c8798a07b417faa6e4b7c5080d274939bb5e45`。此处只记录结论与实施前验证要求，不把审查建议记成已修复。
