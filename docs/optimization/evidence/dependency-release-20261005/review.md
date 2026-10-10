# 冻结候选的依赖与发布条件核查

查询日期：2026-10-05，Asia/Shanghai。独立只读审阅；未安装依赖、运行服务/数据库/浏览器/测试或漏洞载荷，未访问生产，未修改产品与版本。官方来源均在本轮通过 web 工具访问；[来源元数据](official-sources.json) 保存 URL、页面日期、适用范围及无法取得日期的限制。

## 结论与目标 9 的真实剩余

实际解析版本和重点官方维护状态已核对。当前候选可以继续作为受限制的本地可评审版本；本轮没有新证明“可利用且阻断发布”的漏洞，也没有给出整体安全放行。已交付的 Tomcat 和 Shiro 过渡修复仍有效；Boot/Spring、Shiro、Vue 的社区维护问题没有因此消失。目标文件第 63 行要求核对实际版本、处理有关阻断并独立评估框架兼容性；版本/公告核对这一部分现在有当前证据，具体条件验证和受支持平台路线仍需收口。EOL 本身不等同已复现漏洞，也不能自动要求在小范围本地候选之前重写整个平台。

最有价值的下一步是一个小型 **Shiro 当前配置/资源入口验证切片**：围绕大小写文件系统、Servlet/native session 及 HTTPS 代理后的 Cookie 属性取得允许与拒绝证据。它不依赖浏览器验证码，也不需要重复原 49 条 dispatcher/认证专项。若没有发现可达问题，可登记“不适用/已有防护/有范围的待验”；若证实私有附件可匿名读或会话/凭据风险，再为具体缺陷建独立修复。重大平台迁移另行评审，不能把一次版本号改动记作完成。

## 当前交付物及精简机器清单

候选 `64cce174aac6cf3699985b4bc88a30cc70c2f67f`；API tree `92a0c8032ee4a94cebf95ee48b60dbfc7abb0068`，web tree `d35f4bf0d3cf203429cdd23b14c232116b34d734`。[inventory-summary.json](inventory-summary.json) 是可共享的精简清单；[inventory.json](inventory.json) 保留完整追溯详情，来自冻结 JAR 的 ZIP 条目/内嵌 Maven 元数据、锁文件、已有 node_modules 的 package.json 与构建记录，包含 **209 个内嵌库的 SHA-256（208 外部、1 内部）** 和 **15 个关注 npm 包的全部锁定实例**。这是完整后端包内库清单及选定前端清单，不声称是覆盖所有预打包编辑器/public 文件的完整 SBOM。无账号、令牌、连接串或数据正文。

- 冻结 #62 JAR：`teaching-open-class-membership-access.jar`，SHA-256 `f03ac420301977cea26e14d9de0bab03f0d8a5c0e7ec92854363ad07347060c0`。
- `web/package-lock.json`：lockfileVersion 2，SHA-256 `100033635ce1d01f5ee7b8cd1385bc958edde7ad5686d441d205b49ea7e78e74`。
- 构建记录结束于 `2026-10-03T15:58:21.447973+00:00`，`tests_skipped=true`。JDK release 文件为 Zulu `8.96.0.205-CA-macos-aarch64`、Java `1.8.0_504`；只证明该包的构建环境，不证明生产 JVM。没有在本轮重新构建。

| 组件 | 实际版本与证据 | 当前维护判断及日期 |
| --- | --- | --- |
| Java | POM `api/pom.xml:55` 为 1.8；构建 JDK 为 Zulu 8u504-b01 / 8.96.0.205 | Java 8 不能笼统写成 EOL。Azul 路线图仍列 Java 8 的 Production Support 至 2030-12，商业保障资格需另核。官方版本表把当前 build 对应到 2026-08；2026-09-15 的后续 build 仅针对 FIPS，不适用于本普通 CA 包。路线图无页面发布日期。[路线图](https://www.azul.com/products/azul-support-roadmap/)、[版本表](https://docs.azul.com/core/version-search) |
| Spring Boot | JAR 及 POM `api/pom.xml:11` 为 2.1.3.RELEASE | 2.1.x 维护结束于 2020-11-01；公告发布 2019-12-10。无法从当前构建成功推导仍有社区补丁。[官方公告](https://spring.io/blog/2019/12/10/spring-boot-2-1-x-eol-november-1st-2020/) |
| Spring Framework | JAR 中 14 个框架模块全部 5.1.5.RELEASE | 5.1.x 在 2020 年退出活跃维护；2019-12-03 路线图已说明，当前官方 wiki（最后编辑 2026-02-05）也未把它列入支持线。只升到已结束 OSS 维护的 5.3/6.2，不能据此声称解决长期支持。[原路线图](https://spring.io/blog/2019/12/03/spring-framework-maintenance-roadmap-in-2020-including-4-3-eol/)、[当前支持/平台](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions) |
| Apache Shiro | POM `api/pom.xml:57` 及 12 个 Apache 模块全部 1.13.0；另有 shiro-redis 3.1.0，不能混为 Apache Shiro 版本 | 2026-06-29 的官方 3.0 发布声明 1.x/2.x EOL；1.13 是过渡维护结果。[发布与 EOL](https://shiro.apache.org/blog/2026/06/apache-shiro-300-released.html) |
| Tomcat | POM `api/pom.xml:59` 与 core/EL/WebSocket 三模块全部 9.0.122 | 当前官方表仍列 9.x 支持、最新 9.0.122、Java 8+；安全页顶部为 2026-09-15 的 fixed-in 9.0.122（相关公告于 09-23 披露）。没有取得更晚影响本版本的条目，不等于没有漏洞。[支持表](https://tomcat.apache.org/whichversion.html)、[安全页](https://tomcat.apache.org/security-9.html) |
| Vue | 声明、锁文件和已装包均 2.7.16；compiler 同版 | 2023-12-31 EOL；2.7.16 为最终社区版本。页面无发布/更新时间；EOL 日期明确。不存在“升到最新 Vue 2 即恢复维护”的结论。[官方 EOL](https://v2.vuejs.org/eol/) |
| Ant Design Vue | `web/package.json:19` 声明 **^1.6.3**，锁文件和已装包实际 **1.7.8**；peers 为 Vue/compiler ^2.6.0 | 不能把 1.6.3 写成当前交付。当前官方 raw SECURITY.md 仍标 1.x 支持，但保留未填模板文字，无日期/SLA/补丁计划；不据此臆造 EOL 或保证近期更新。1.7.8 README 表示 Vue 3 从 2.x 起支持。[当前策略](https://raw.githubusercontent.com/vueComponent/ant-design-vue/main/SECURITY.md)、[版本 README](https://raw.githubusercontent.com/vueComponent/ant-design-vue/1.7.8/README.md) |
| Vue CLI | service/babel/eslint 主链均 3.12.1 | 当前官方站声明 Maintenance Mode，建议新项目 create-vue/Vite；页面无日期，也无 CLI 3 单独支持承诺或 EOL 日期。[官方站](https://cli.vuejs.org/) |
| webpack | 主构建链锁定且已装 4.47.0；vue-photo-preview 的嵌套锁定另有 3.12.0 | 官方 security policy 没有支持版本表或 4.x EOL 日期，不能把“旧”直接换算为特定停更日期。CLI/loader/plugin 与生成的浏览器 runtime 都要分开评估。[官方策略](https://github.com/webpack/webpack/security/policy)、[4→5 迁移](https://webpack.js.org/migrate/5/) |

## 公告与实际候选的关联

**已修复且保留的范围。** 包内 Shiro 1.13.0 已达到官方 CVE-2023-46749/46750 的修复版本；不再把旧 1.7.0 当当前版本。Tomcat 当前三模块 9.0.122 已达到官方顶部修复线，例如 CVE-2026-87022 的受影响范围止于 9.0.121。这里只确认版本/此前修复成果，未重跑旧维护专项，也未用其代替未知风险判断。[Shiro 公告](https://shiro.apache.org/security-reports.html)、[Tomcat 公告](https://tomcat.apache.org/security-9.html)

**仍需条件核实；未证明可利用。** 以下只保留与当前配置有交点或常被误判的几项，不作 CVE 数量清单。

| 条件 | 本轮实际证据 | 校准后的状态 |
| --- | --- | --- |
| Shiro 对受保护静态文件的大小写匹配，CVE-2026-23903 | 官方以大小写不敏感文件系统为前提。当前 `ShiroConfig.java:72` 先保护 `/sys/common/static/**`，`:102` 起另有按后缀 anon，`:184` 默认 JWT；`WebMvcConfiguration.java:57` 的 `/**` resource handler 仍将 upload/webapp 文件目录映射进来。当前 1.13 没有 2.1 新增的大小写选项。 | 有需要核实的实际资源路由交点，尚无“绕过并读到私有字节”证据；不能把存在 handler 当泄露复现。先用非真实内容的 canary 文件，对照匿名/有效身份、合法路径/大小写别名及目标 FS/proxy。源路径大小写、后缀匿名链、控制器自身授权均纳入判据。[官方条件](https://shiro.apache.org/security-reports.html) |
| Shiro 默认 session fixation / Secure-cookie 条件 | `ShiroConfig.java:198` 关闭 rememberMe；`:207` 关闭 Subject session storage。后者不能证明全部 Servlet/session 创建被关闭，common `JwtUtil.java:114` 仍有 getSession，QueryGenerator 有调用；本轮没有调用该路径。自有媒体 Cookie `MediaCookie.java:37` 根据 request.isSecure 添加 Secure。 | RememberMe 前提在当前配置未满足；native/Servlet session 与 HTTPS 终止代理仍须分别验证。不能把自有媒体 Cookie 等同 Shiro rememberMe，也不能将关闭 Subject storage 写成“所有 session 漏洞已消除”。记录实际 Cookie/session 是否产生及是否参与身份，不预设缺陷。[官方条件](https://shiro.apache.org/security-reports.html) |
| Spring 数据绑定 RCE，CVE-2022-22965（公告 2022-03-31） | 官方公开 exploit 前提为 JDK9+、Tomcat、WAR、MVC/WebFlux。当前是 Java8 构建的 Boot executable JAR，存在 MVC，但不符合该已公布组合。 | 公开 exploit 条件不匹配；不是 Spring 5.1 的整体安全结论。更换 JDK/部署形式时重新评估，官方也明确存在更一般的潜在利用形式。[官方公告](https://spring.io/security/cve-2022-22965/) |
| Vue 2 compiler ReDoS，CVE-2024-9506（2024-10-14） | Vue 官方维护伙伴 HeroDevs 的一手公告命中 >=2,<3 compiler/parser。当前 compiler 2.7.16 命中；CLI 已装代码 `lib/options.js:99` 默认 runtimeCompiler=false，`lib/config/base.js:54` 选择 runtime-only，vue.config 没覆盖；web/src 搜索未找到 Vue.compile/直接 full build 导入。 | 版本命中，但本轮没发现课程/用户输入在主应用被当 Vue 模板编译的证据。构建处理可信源码与浏览器可控输入是不同暴露面；public 预打包编辑器和外部依赖内部不是这次有界搜索的全部覆盖。需输入到编译器的链才判当前阻断。公告来自官方推荐伙伴，不冒称 Vue core-team 公告。[伙伴公告](https://www.herodevs.com/vulnerability-directory/cve-2024-9506)、[Vue 伙伴说明](https://v2.vuejs.org/eol/) |
| webpack emitted runtime DOM clobbering，CVE-2024-43788（2024-08-27） | 维护者公告发布范围 <5.93.0，并描述 AutoPublicPath runtime/可控 HTML 前提。CLI 默认 publicPath='/'；当前 `web/dist/js/app.fff8dd9f.js`（229840 bytes）静态读取为 `u.p="/"`，没有 document.currentScript/AutoPublicPathRuntimeModule 字符串。 | 不按数字直接判当前 webpack4 主 app 可利用；这里只排查这一份 app 的对应机制，不能扩为所有 chunks/public 编辑器安全。未来改用 auto publicPath 或新构建器时保持这条判据。webpack 是构建依赖，但生成代码可能进入浏览器，不能全部以 devDependency 为由排除。[维护者公告](https://github.com/webpack/webpack/security/advisories/GHSA-4vvj-4cpr-p986) |

Shiro 公告中的 Guice / Jakarta-EE integration / LDAP 条件，当前包没有 shiro-guice、shiro-jakarta-ee，源码 Realm 为 `AuthorizingRealm` 自定义 `ShiroRealm`；有界配置搜索未发现 DefaultLdapRealm。它们不能不加条件地转成当前风险。安全报告页未显示逐条公告发布时间；本报告不把 CVE 的年份当作发布日期。

**维护终止，但不据此证明漏洞。** Boot 2.1/Spring 5.1、Shiro 1.x 和 Vue 2 属这一类；CLI 的 Maintenance Mode、webpack 的旧构建生态是迁移理由，证据不足时不追加正式 EOL 日期。没有任何近期公告/路径证据能从旧 npm audit 的聚合数字推导当前可利用数量；本轮不执行 npm audit，也不把历史 155 当漏洞数。

## 最小可评审的迁移切片与约束

1. **先建立当前发布边界，随后论证后端平台。** 上述 Shiro 切片保留正常媒体字节、匿名/跨身份拒绝、JWT 身份、故障无泄露；在既有隔离环境和合成 canary 上取证，禁止生产载荷。版本迁移另设一个受限兼容分支：比较当前 Java8/javax 栈与当前仍受支持的 Java/Boot/Spring/Shiro 组合，只做 health、JWT 允许/拒绝、一个 MyBatis 读取、Redis 身份缓存、multipart 和授权媒体读取，再扩大到原核心回归。保持 schema、JSON/result code、JWT/Cookie、媒体 URL 与附件字节契约，不能借迁移扩权限。
2. **后端不能逐处改版本号。** 官方 Boot 2→3 指南以 2.7 为迁移准备点，Java17/Spring6/Servlet Jakarta 为共同边界；2.7/3.0 是历史迁移台阶，不是本轮长期支持终点。Shiro3 也要求新平台且改变匹配/默认 filter/API。当前 ShiroFilter/JwtFilter/MediaCookie 明确使用 javax.servlet，shiro-redis、MyBatis/Druid starter、Springfox、校验/邮件/定时任务等实际第三方集成必须评估兼容替换；仅新 JDK 启动旧包，不恢复 Boot/Shiro 支持。最终目标版本须按届时维护线和可接受商业支持分别选择。本轮未安装/验证某一新组合，不承诺特定版本组合已能运行。[Boot 迁移指南](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)、[Shiro3 平台](https://shiro.apache.org/blog/2026/06/apache-shiro-300-released.html)、[Spring 当前范围](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions)
3. **前端把构建器与 Vue 主版本分开。** 若先做现代构建器的短切片，保留 Vue2/AntD1 API，比较路由 lazy chunk、publicPath、主题 less、静态编辑器附件路径、gzip 和源码/产物摘要；这只能解决工具链，不解决 Vue EOL。Vue3 切片选择真实成员列表/选择器与共享编辑表单，覆盖受控选择、确认/迟到请求、表单校验、上传和普通 legacy 入口，原 64 条业务判据继续适用，再检查真实 DOM 三宽度/键盘。AntD1 peers 属 Vue2，不能假定 `@vue/compat` 能兼容全部内部 VNode/form/table 用法；同时核 @jeecg/antd-online-beta220 等实际组件依赖。保持 API/数据和已交付 #61–63 行为，暂不全站重写。付费 Vue NES 是官方列出的备选，需要独立成本/授权判断；本轮没有购买或采用。[Vue compat 限制](https://v3-migration.vuejs.org/migration-build.html)、[Vue CLI 当前建议](https://cli.vuejs.org/)、[webpack 迁移要求](https://webpack.js.org/migrate/5/)

## 限制与复核

本轮只对重点实际包/锁文件和上述公告进行静态关联；不构成全部 208 外部 Java 库、全部 npm 子依赖和全部 public 预打包代码的安全扫描。15 个 npm 包包括嵌套实例，能看到 vue-photo-preview 自带 webpack3/dev-server2，但不因 lock 中存在就证明它们在交付服务监听。已装依赖读的是现有共享依赖目录，未据此认证干净安装过程或全量每文件字节。版本清单不认证生产实际部署、供应商支持合同、TLS/proxy/目标文件系统、真实用户验收或生产容量。报告不能把静态判断替代这些状态。

写报告前候选 tracked 文件无改动，仅既有 `.playwright-cli/`、`output/` 未跟踪目录；已保留。只在本报告目录新增精简/完整 inventory、来源元数据和报告。JSON 重读/计数与摘要校验属于资料完整性检查，没有执行产品测试。
