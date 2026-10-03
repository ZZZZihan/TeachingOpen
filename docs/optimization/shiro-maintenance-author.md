# Shiro Java 8 过渡维护作者记录

本次基于 `fix/course-update-outcome` 的 `3fb70f1919289d777ccffe936f3a7a8b889a749b`，只修改父 POM 与 `ShiroConfig`：使用 `shiro.version=1.13.0` 更新现有 starter，其实际传递的 12 个 Apache Shiro 模块均统一到 1.13.0；显式将手工 SecurityManager 的 rememberMe manager 设为 null；为同一个自定义过滤器工厂使用 `shiroFilterFactoryBean` 名称，同时保留旧 `shiroFilter` 别名。未新增过滤器工厂、覆盖官方 registration、重复导入 MVC 配置或关闭路径防护。

这是一项 Java 8 过渡维护。Apache 官方已经将 1.x、2.x 列为 EOL；1.13.0 不代表长期受维护，也不消除所有 2026 公告的条件风险。当前受维护的 3.x 需要另行进行 Java/Jakarta/Spring 平台迁移，本 PR 没有执行这项迁移。[官方 EOL 与平台说明](https://shiro.apache.org/blog/2026/06/apache-shiro-300-released.html)、[安全公告](https://shiro.apache.org/security-reports.html)。

名称兼容修复来自实际失败。1.7 的同坐标 starter 原来只有通用自动配置，1.13 合并了 Web/MVC 自动配置。其自动 registration 调用 `shiroFilterFactoryBean().getObject()`；原手工工厂按类型使自动 factory 回退，但只有 `shiroFilter` 名称，导致 registration 查找官方 bean 名失败。给现有工厂添加官方名称即可沿用同一个产物，不需要自己再注册一套过滤器。官方注册保留 REQUEST、FORWARD、INCLUDE、ERROR 四种 dispatcher、order 1；MVC 自动配置导入 `ShiroRequestMappingConfig`。有效容器/单一 Servlet filter 的检查由独立测试 Agent 与主 Agent 执行，不能由名称或源码检查替代。[官方 registration 源码](https://raw.githubusercontent.com/apache/shiro/shiro-root-1.13.0/support/spring-boot/spring-boot-starter/src/main/java/org/apache/shiro/spring/config/web/autoconfigure/ShiroWebFilterConfiguration.java)、[MVC 自动配置](https://raw.githubusercontent.com/apache/shiro/shiro-root-1.13.0/support/spring-boot/spring-boot-starter/src/main/java/org/apache/shiro/spring/config/web/autoconfigure/ShiroWebMvcAutoConfiguration.java)。

最终产物保留 Spring Boot 2.1.3、全部 14 个 Spring Framework 模块（含 spring-oxm） 5.1.5.RELEASE、Tomcat core/EL/WebSocket 9.0.122、shiro-redis 3.1.0 与 Jedis 2.9.1。认证 class major 52，符合 Java 8 编译目标。仅使用 starter 版本属性，不导入 Shiro BOM：该 BOM 的广义依赖管理曾将 spring-webmvc 提升到 5.3.30、其他 Spring 核心保留 5.1.5，实际启动缺类，已撤销。最终实际包没有这个混版本组合。

失败与修正分别记录，均不计入最终通过范围：

| 尝试 | 作者执行结果 | 主 Agent 隔离启动观察 / 修正 |
|---|---|---|
| 初次 POM 编辑 | Maven 解析退出 1，重复 dependencyManagement，未开始编译 | 合入原管理块后重试；属于作者编辑错误 |
| BOM 候选，JAR `257893ec…` | clean package 退出 0，但包内 Spring 混版本 | 启动因 `ApplicationStartup` 缺类失败；去掉 BOM |
| 仅版本属性与 rememberMe，JAR `3a80c0b8…` | clean package 退出 0，实际依赖已统一 | 启动因缺少 `shiroFilterFactoryBean` 名称失败；补同一工厂别名 |
| 最终 JAR `232508e5…` | clean package 退出 0，8.054 秒；ZIP 版本/major 检查退出 0；diff-check 退出 0 | 独立运行验证另记测试证据 |

上述实际启动均由主 Agent 在专用 `.devspace/shiro-1003` 执行，作者没有启动服务、登录或操作数据库。原始构建日志、两个失败 JAR/版本清单和最终 inventory 留在私有 `.devspace/artifacts/shiro-maintenance-build/`，启动失败日志由主 Agent 保存在专用 runtime。原始日志与 JAR 不进入 Git。`clean package` 使用 `-DskipTests`，工程本身也默认跳过 Surefire，因此作者构建成功不是 JUnit/真实接口通过的证明。

可复现的作者构建命令（在本工作树 `api` 目录运行）：

```sh
JAVA_HOME=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home \
  /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/apache-maven-3.9.16/bin/mvn \
  -s dev/maven-settings.xml \
  -Dmaven.repo.local=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/m2 \
  -DskipTests clean package
```

最终 JAR SHA256：`232508e514d6221fda0f64975936e22ed370e8fe7eb29eea7e1c3bbc798bda8e`。冻结的产品源码 SHA256：`api/pom.xml` 为 `6ba0b79046344e99378bb56fe597dd92535ee16abbe8df35f0a8e87c0d038aad`；`ShiroConfig.java` 为 `a8cb16f0ba40581dd8d97f7959eef9f41f356a397e779ea65413c504ecded8e0`。没有将升级后的版本命中情况表述为旧系统漏洞已可利用，也没有将源码/构建核对表述为浏览器、生产或人工验收。
