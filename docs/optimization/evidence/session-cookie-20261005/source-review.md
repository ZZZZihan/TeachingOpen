# 会话与媒体 Cookie 条件审阅（2026-10-05）

结论：当前只读证据未建立一个应立即修复的会话身份漏洞。`JSESSIONID` 可由数据权限变量解析创建，但现有登录身份来自 JWT/Redis；媒体 Cookie 的 `Secure` 依赖后端对请求安全协议的判断。仓库没有明确给出 TLS 终止与可信转发头契约，因此“HTTPS 代理后 Cookie 缺 Secure”目前是待确认的部署条件，不能写成已复现的漏洞，也不据此新建修复 PR。

## 证据范围

- 当前候选：`.devspace/worktrees/product-candidate`，HEAD `49bea7da3552c554a8412f777eeec48d9a5ac9f2`；工作树仅有原有未跟踪 `.playwright-cli/` 和 `output/`，均未改动。
- 指定冻结 JAR：`.devspace/artifacts/upload-resource-boundary/author-build-20261004T172848Z/teaching-open-upload-resource-boundary.jar`，重新计算 SHA-256 为 `9eb18d42d365dd4fba7044d57ed33aaa0fdb543f8468dd67c10c9dc83de05869`。
- ZIP 清单确认 Apache Shiro 1.13.0、Boot 2.1.3.RELEASE、嵌入 Tomcat 9.0.122。对包内相关应用类、Shiro 类执行 JDK 8 `javap -c -p`，下述关键调用与源码相符；没有重新编译或启动该 JAR。
- 未运行服务、HTTP、SQL 或浏览器，未访问外部生产系统，未读取运行凭据。只写本报告；PR 65 的静态上传映射不在本次复测范围。

## 身份与会话路径

`ShiroConfig.java:193–212` 手工构建 `DefaultWebSecurityManager`，配置自定义 Realm，显式 `setRememberMeManager(null)`，并将 `DefaultSubjectDAO` 的 `DefaultSessionStorageEvaluator` 设为 false。指定 JAR 的 `ShiroConfig.securityManager()` 字节码逐项确认这些设置；未调用 `setSessionManager`。其包内 `DefaultWebSecurityManager` 构造器创建 `ServletContainerSessionManager`，不是 Shiro `DefaultWebSessionManager` 原生会话。

Shiro 1.13 Web 自动配置的 `securityManager()` 受 `@ConditionalOnMissingBean` 保护。应用已经提供该类型的 bean；没有找到应用后续替换这个 SecurityManager/session manager 的入口。上游可能创建的独立 session/cookie/rememberMe bean，不等于它们已装入这个手工 manager。上述是装配源码/字节码判断；尚未在本轮读取实时 bean。固定上游依据：[DefaultWebSecurityManager 1.13](https://github.com/apache/shiro/blob/shiro-root-1.13.0/web/src/main/java/org/apache/shiro/web/mgt/DefaultWebSecurityManager.java)、[Web 自动配置](https://github.com/apache/shiro/blob/shiro-root-1.13.0/support/spring-boot/spring-boot-starter/src/main/java/org/apache/shiro/spring/config/web/autoconfigure/ShiroWebAutoConfiguration.java)、[Web 配置默认 Servlet manager](https://github.com/apache/shiro/blob/shiro-root-1.13.0/support/spring/src/main/java/org/apache/shiro/spring/web/config/AbstractShiroWebConfiguration.java)（2026-10-05 查阅）。

实际登录与请求链：

1. `/sys/login` 校验验证码、账户状态和密码，调用 `LoginController.userInfo()`；`/sys/phoneLogin` 也调用该方法。该方法签 JWT、写 Redis 的 token 生命周期并发媒体 Cookie（`LoginController.java:357–397`）。`/sys/mLogin` 有自己的签发分支（481–488）。这里没有创建或写入 HttpSession 身份。
2. 受保护请求由 `JwtFilter.isAccessAllowed()` 每次执行 `Subject.login(JwtToken)`；只有 Realm 成功才通过。`executeLogin()` 成功后重发媒体 Cookie（`JwtFilter.java:35–42,59–68`）。Realm 检查用户状态与 Redis token 生命周期（`ShiroRealm.java:109–173`）。没有按 `JSESSIONID` 或现有 `Subject.isAuthenticated()` 跳过 JWT 的分支。
3. `OptionalJwtFilter` 未带请求头时允许匿名；带请求头仍走完整 JWT 检查（11–16）。`MediaJwtFilter` 仅在 header 缺失时读取媒体 Cookie，最终仍走同一个 Realm（13–25）。Cookie 仅用于 `/sys/common/static/**`，不作为一般 API 认证输入。
4. `/sys/logout` 先清媒体 Cookie，再读取 `X-Access-Token`，删除 Redis 生命周期/授权缓存并调用 `Subject.logout()`（`LoginController.java:132–154`）。

全应用 Java 搜索找到唯一直接 Servlet `getSession()`：`JwtUtil.getSessionData()`，其 `getSession()` 会在没有会话时创建一个。调用方仅 `QueryGenerator.converRuleValue()`（532），先读会话变量，找不到再读当前用户系统变量（533–536）。即使规则是普通字面量，该非空 key 也进入会话读取。指定 JAR 内 base-common 的此方法同样调用无参数 `HttpServletRequest.getSession()`；“关闭 Shiro 身份保存”不能表述为“完全无 Servlet 会话”。

可达路径是 `@PermissionData` 控制器 → `PermissionDataAspect` 用 JWT 用户名/菜单查询现有数据规则并放到 request 属性（106–122）→ `QueryGenerator.installMplus()` 读取规则（100–121）→ 字符串/日期规则或 SQL 变量 → `converRuleValue()` → `JwtUtil.getSessionData()`。代表入口包括 `/sys/user/list`（`SysUserController.java:88–130`）、`/sys/user/departUserList`（943–951）、管理员/开发者 `/teaching/teachingCourse/list`（`TeachingCourseController.java:95–113`）、`/teaching/teachingWork/list`（`TeachingWorkController.java:272–289`）。是否在当前数据库实际触发取决于匹配菜单和已绑定数据规则，本轮未读取数据库，不能声称普通列表必然产生 JSESSIONID。

未找到应用向 HttpSession 写入用户身份、认证状态或数据规则变量的代码；`JeecgDataAutorUtils` 把规则和用户信息放在 request 属性。Shiro 包内 `DefaultSubjectDAO.save()` 在 storage=false 时不调用 `saveToSession()`，字节码确认。因此本轮不能从“有 JSESSIONID”推出“会话参与身份”，也不能从“登录未轮换 JSESSIONID”直接推出身份固定攻击成立。把 `getSession()` 改为 `getSession(false)` 可作为独立的减少空会话候选，但需要保留现有规则结果与已有会话变量兼容证据；此处未提实现或 PR。

## Cookie 与 HTTPS 代理条件

`MediaCookie.write()`（34–38）统一用于签发与清除，属性为 `Path=<contextPath>/sys/common/static; HttpOnly; SameSite=Strict`；只有 `request.isSecure()` 为 true 时追加 `Secure`，清除另外追加 `Max-Age=0`，响应加 `Cache-Control: no-store`。没有 Domain/普通签发 Max-Age。包内 `MediaCookie.write()` 字节码明确调用 `HttpServletRequest.isSecure()`。

可见部署材料的契约只有 HTTP：

- `README.md:222–246`：Nginx listen 80，HTTP 回源，设置 `X-Forwarded-For`。
- `资料/nginx.example.conf:3,58–65`：listen 80，HTTP 回源，设置 `X-Forwarded-For`。
- `web/nginx/default.conf:3,58–66,80–81`：listen 80，HTTP 回源，设置 `X-Forwarded-For` 与 `X-Scheme`，没有 `X-Forwarded-Proto`。应用未找到读取 `X-Scheme` 以改写请求安全协议的代码。
- `deploy/docker-compose.yml:28–50`：prod profile，web 暴露 80；没有 TLS 端口或转发头配置。对 `deploy/.env` 仅核对相关转发/session cookie 配置键存在性，没有命中，不保留其值。
- `application.yml:4` 默认 dev；dev/test/prod 的 server 段都是 HTTP port + `/api` context。相关源码/config 搜索未命中 `server.use-forward-headers`、protocol/remote-ip/internal-proxies、SSL、`ForwardedHeaderFilter` 或 `RemoteIpValve` 自定义入口。
- 开发代理文档明确本机服务器“不提供生产反向代理、TLS、HTTP/2 或连接容量承诺”（`docs/optimization/local-websocket-proxy-pr.md:9`）；现有匿名基准也明确没有 TLS（`production-read-benchmark-author.md:21`）。

Boot 2.1.3 官方说明：普通环境默认不使用转发头；使用可信代理的常规 X-Forwarded-Proto 契约需 `server.use-forward-headers=true` 或适当 Tomcat 配置。对应固定源码在显式 protocol/remote-ip header 或 use-forward-headers 生效时才添加 RemoteIpValve；不是把任意客户端发来的 XFP 自动当真。Cloud Foundry/Heroku 有平台默认差异，环境/启动参数可覆写仓库默认。因此本轮结论仅限保留源码默认与部署示例，不涵盖未读取的线上配置。[Boot 2.1.3 代理文档 §78.12](https://docs.spring.io/spring-boot/docs/2.1.3.RELEASE/reference/html/howto-embedded-web-servers.html#howto-use-behind-a-proxy-server)、[固定 Tomcat customizer 源码](https://github.com/spring-projects/spring-boot/blob/v2.1.3.RELEASE/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/web/embedded/TomcatWebServerFactoryCustomizer.java)（2026-10-05 查阅）。

可以推断：若新增 HTTPS 终止代理而仍以 HTTP 回源，且后端没有任何可信协议恢复配置，`isSecure()` 会看到内层 HTTP，媒体 Cookie 缺 `Secure`。这需要 TLS 拓扑/实际请求证据才能定为真实 HTTPS 部署问题。直接 HTTP Cookie 缺 Secure 符合当前代码分支；单凭该观察不构成安全漏洞证明。Servlet 容器 JSESSIONID 另由 Tomcat 发出；9.0.122 在配置 secure 或请求 secure 时设置 Secure，不属于 `MediaCookie` 或 Shiro native cookie 的实现。[Tomcat 9.0.122 cookie 源码](https://github.com/apache/tomcat/blob/9.0.122/java/org/apache/catalina/core/ApplicationSessionCookieConfig.java)（2026-10-05 查阅）。

## 上游公告范围

2026-10-05 查阅 [Apache Shiro 官方安全公告](https://shiro.apache.org/security-reports.html)：CVE-2026-43828 描述 Shiro native session 与 rememberMe cookies 的默认 Secure 问题；当前手工 manager 使用 Servlet 会话且 rememberMe=null，这两个已知发送路径前提未匹配。应用自定义 `teaching_media` JWT Cookie 必须独立按上节部署条件评估，不能把它直接记成该 CVE。

CVE-2026-43827 的公告是已有会话在成功登录后未替换 ID；包版本处于公告区间，但本应用关闭身份 session 保存并强制每次受保护请求 JWT 检查。尚未建立凭已知 JSESSIONID 获取/恢复用户身份的入口。版本匹配、可能创建空 HttpSession、实证身份固定可利用性是三个不同结论；本轮只确认前两者的静态条件。

## 最小后续验证建议（本轮未执行）

优先使用无凭据 `/api/sys/logout`：此 anon 路由在检查 token 前先调用同一个 `MediaCookie.write(clear=true)`。在冻结 JAR 的自有 loopback context，对直接 HTTP、仅携带 XFP:https 的 HTTP、显式启用可信 loopback 代理协议契约后的 HTTP+XFP:https 做分组，只保存 status、Cookie 名称/Path/HttpOnly/SameSite/Secure/Max-Age 属性布尔值，丢弃 Cookie 值。可在不触碰 CAPTCHA/登录的情况下验证协议恢复与清除分支；不能把此清除验证称为实际登录签发或真实 TLS 验收。

若后续正式承诺 HTTPS 终止支持，再通过自有本机 TLS 代理加 HTTP 回源核对登录签发、有效 JWT 读请求重发、无效 media cookie 清除、logout 清除四个入口，并确认转发头由可信代理覆盖。不要仅为了让 Cookie 多出 Secure 就信任所有网络来源或让应用直接信任任意 XFP。

会话身份最小验证：先在实际 context 仅输出有效 SecurityManager 的 session manager 类名、rememberMe 是否 null、sessionStorage=false；随后用一个自有合成数据规则走现有 `@PermissionData` 列表入口，观察是否创建 JSESSIONID及规则结果。跨请求只带该 JSESSIONID、撤销/缺失 JWT 的受保护只读请求必须拒绝。初始 fixtures 是否有匹配规则须由运行测试方先确认；无规则时未出现 JSESSIONID不足以否定源码可达性。所有上述运行步骤由主 Agent 另行安排，本报告不实施。
