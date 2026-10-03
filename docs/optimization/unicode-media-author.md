# 中文本地媒体路径兼容修复：作者记录

本项支持直接 GET/HEAD 读取已有或新上传的中文本地媒体路径。专项 Agent 已在 PR55 的精确旧包上用独立合成课程封面复现：公开课程的 ASCII 文件返回 HTTP200、28 字节且正文匹配；同一目录的单次 UTF-8 百分号编码 `课程封面.txt` 返回 HTTP401、70 字节 JSON，未返回目标正文。该记录见 [旧包核心复现](evidence/unicode-media/core-baseline.json)。这份响应记录证明了中文路径读取失败，不单独证明失败发生在鉴权层。root 核对的生产数据副本中 297 个路径均为 ASCII，因此本项不声称现有生产课程的中文文件受到影响。

本次代码核对 [Shiro 1.13.0 的 InvalidRequestFilter](https://github.com/apache/shiro/blob/shiro-root-1.13.0/web/src/main/java/org/apache/shiro/web/filter/InvalidRequestFilter.java) 及本机实际依赖字节码，确认其默认 `blockNonAscii=true`，会同时检查原始 URI、已解码的 servletPath、pathInfo；UTF-8 百分号编码仍会在解码路径上被拦截。其 ASCII 检查还承担控制字符拒绝，直接关闭开关会扩大行为范围。

实现只在 ShiroConfig 的 filters map 中以同名 `invalidRequest` 替换该实例。Shiro 的默认 globalFilters 保持启用，既有 `/sys/common/static/** → mediaJwt` 顺序保持不变。新的 LocalMediaInvalidRequestFilter 对其它请求直接调用父类原有检查；仅 `DispatcherType.REQUEST`、GET/HEAD、原始 URI 含当前 contextPath 加字面 `/sys/common/static/` 前缀、且解码后的 servletPath+pathInfo 也匹配该路由边界时，才使用私有 Unicode 检查器。检查器只在构造时允许非 ASCII，不随请求切换共享开关；同时拒绝三种路径字段中的 C0/C1/DEL 控制字符，并保留 Shiro 的分号、反斜杠、遍历、编码点、编码斜线和重写遍历检查。该私有检查器未注册为 Spring Bean 或 Servlet Filter，避免重复注册。

此例外不执行二次 URL 解码、不做 Unicode 归一化、不增加匿名路由。通过路径检查后，仍执行既有 MediaJwtFilter 的凭据验证、CommonController 的路径键检查、LocalDownloadAccessService 的实时资源关系授权，以及 LocalFileDownload 的根目录/路径段/符号链接校验与 HEAD/Range 传输。上传命名策略、数据库表、依赖及 UI 均无需变化。

本项新增兼容范围只覆盖直接媒体请求；FORWARD、INCLUDE、ERROR、ASYNC 分派继续使用父类原有检查，没有新增内部分派的 Unicode 支持。路径异常的最终 HTTP 状态还可能受 Tomcat 和应用现有错误分派影响，应以实际负控响应及无目标/邻居字节为准，不能从状态单独推断拒绝层。构建与作者自检只证明源码和打包状态；实际 HTTP、上传闭环和拒绝边界由专项测试记录分别证明。人工师生试用、生产版本对应、合并和部署均不在本项作者自检范围。

## 当前作者自检状态

- 基础提交：`6235e7e2586a4ce914257faa11c7552bf628c04c`（PR55）；独立分支 `fix/unicode-media-paths`。
- 已核对专项旧包复现与实际 Shiro 1.13.0 实现。
- 使用 `api/BUILDING.md` 的固定 Zulu JDK8 `8u504`、Maven `3.9.16`、项目 `dev/maven-settings.xml` 与既有隔离 Maven 缓存执行 `clean package`，进程退出码 0，实际 `BUILD SUCCESS`，耗时 9.227 秒，完成时间 `2026-10-03T20:25:33+08:00`。
- 父 POM 跳过 Java 测试，构建日志有两处 `Tests are skipped`，不把打包成功称为 Java 测试通过。实际告警为原有 JeecgBootExceptionHandler 的 `com.sun.org.apache.xpath.internal.operations.Bool`、TeachingScratchBackpackController 的 `sun.misc.BASE64Decoder` 内部 API；原有 FreemarkerParseFactory、Swagger2Config、VerifyShiroMaintenance 有过时 API 提示，DataSourceCachePool、DictAspect 有 unchecked 提示。本次两份产品源码没有新的编译告警。
- 已自查 `git diff --check` 退出 0，JAR 内含新的外层/私有内层类和 ShiroConfig，实际 Shiro Web/Spring 依赖仍为 `1.13.0`。
- 产品代码与 JAR 已冻结；专项候选 HTTP 结果尚未完成，将由测试说明另行记录。作者未操作专项 runtime、未提交/推送或创建 PR。

冻结 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `api/jeecg-boot-module-system/src/main/java/org/jeecg/config/ShiroConfig.java` | `d4dc28a81d4b08c0e9594c48f917e47cc558bedb395b3aca2ca7116af6749af7` |
| `api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/shiro/authc/aop/LocalMediaInvalidRequestFilter.java` | `a30e660b8bb3f7eb2b9a53e1c300af543cedfb2ad5fd26735ed969364c617814` |
| `api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar` | `95d9ad3ad4ada70897974071fec283a0c29bb703e2cdcb41397e80f77ebbd7c7` |

本机私有构建日志保留在 `/tmp/teaching-unicode-media-build-20261003.log`，SHA-256 为 `b3d70f9200562b6b191e26702d556506b5b3eb5aa1e1b46f57e6eebefadf6ce8`；它不是对外持久交付的证据文件。
