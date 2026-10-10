# 上传目录静态资源旁路修复：作者记录

日期：2026-10-05（Asia/Shanghai）。分支 `fix/upload-resource-boundary`，基础提交 `328a021224521674654c8c6f03c01be7fbb7ae2f`。本项修复公开静态处理器读取上传根目录的第二入口；不是对某个路径大小写的单点补丁，也未将应用配置旁路套成某个 CVE 的复现。

## 问题证据与产品改动

独立测试 Agent 在旧冻结 #62 包 `f03ac420301977cea26e14d9de0bab03f0d8a5c0e7ec92854363ad07347060c0` 上放置自制 44 字节合成 PNG。匿名 `/api/sys/common/static/resource_boundary_minimal_canary.png` 返回 401、0 字节；匿名 `/api/resource_boundary_minimal_canary.png` 返回 200、`image/png`、44 字节，正文 SHA-256 为 `9671c8b87ff5a2fd0f59f958e19b11d511fcecf5842caacaa704371b16a2095d`，与目标文件完全一致。探针 finally 删除 canary，69 张表结构、68 张非审计表与附件前后相同。原始证据保存在私有 `.devspace/artifacts/upload-resource-boundary/minimal-old-response.json`。这是实际隔离 HTTP 证据；作者没有运行该探针。

源码原因是 `WebMvcConfiguration` 把 `jeecg.path.upload` 注册成 `/**` 的首个资源来源。`/<key>` 未命中控制器时可进入 Spring 的 `ResourceHttpRequestHandler`；Shiro 的通用后缀匿名规则允许 PNG 等请求，它们未经过专用控制器的 `localDownloadStatus`。即使去掉后缀匿名规则，普通已登录用户仍可能通过该别名绕过文件级授权，因此应移除这个资源来源。

产品只改 [WebMvcConfiguration.java](../../api/jeecg-boot-module-system/src/main/java/org/jeecg/config/WebMvcConfiguration.java)：删除不再使用的 upload 注入，从公开 `/**` 处理器删除 upload location，并留一句上传只经授权媒体控制器的注释。原 `/**`、webapp location、classpath locations、自定义 `spring.resource.static-locations` 键以及 Shiro/控制器/下载服务/前端/依赖均保留。

本项目使用的单数 `spring.resource.static-locations` 是 `@Value` 自定义键。旧冻结包内 Boot 2.1.3 的原生属性实际为复数 `spring.resources.static-locations`；本次没有借修复改变属性契约或公开资源来源。保留 webapp 支持现有简化前端部署，保留 classpath 支持 PDF `/generic/**`、大屏及演示资源。公共上传图片继续由 `/api/sys/common/static/<key>` 按当前课程、配置、新闻、头像和作品关系授权。部署配置须继续将公开 webapp/classpath 来源与上传存储分开；本作者没有检查或修改生产配置。

## 最终冻结与构建

最终冻结目录：`.devspace/artifacts/upload-resource-boundary/author-build-20261004T172848Z`，UTC 时间对应本地 2026-10-05 01:28。

| 对象 | SHA-256 |
| --- | --- |
| 最终 WebMvcConfiguration.java | `fd1e4a21022a6edbe50229c1055cbe71822808f4fbf6dfd2d1ea607a5c925dd5` |
| 最终 teaching-open-upload-resource-boundary.jar | `9eb18d42d365dd4fba7044d57ed33aaa0fdb543f8468dd67c10c9dc83de05869` |
| 对照旧 #62 JAR | `f03ac420301977cea26e14d9de0bab03f0d8a5c0e7ec92854363ad07347060c0` |

采用既有固定 Azul Zulu JDK8 `8u504`、Maven `3.9.16` 及 `.devspace/backend-runtime/m2`，在本工作树 `api` 执行 `clean package -DskipTests`。构建退出 0，Maven 报告 8.196 秒；日志两处实际显示 `Tests are skipped`。构建前后 1107 个 tracked API 文件的字节摘要完全相同，最终产品源码及 diff 已一并冻结。该清单限定 tracked API 文件；独立测试 Agent 后续新增的未跟踪探针另行冻结，未计入这一构建源码清单。

包内对照没有增删条目，唯一变化的应用 class 为 `BOOT-INF/classes/org/jeecg/config/WebMvcConfiguration.class`。209 个内嵌依赖中，208 个外部 JAR 逐字节相同；重新打包的 `jeecg-boot-base-common-2.8.0.jar` archive 摘要变化，但解包后的所有文件名、字节长度与 SHA-256 均相同。完整证据为冻结目录中的 `source-manifest-before.json`、`source-manifest-after.json`、`frozen-hashes.json`、`baseline-jar-inventory.json`、`candidate-jar-inventory.json`、`dependency-inventory.json`、`internal-dependency-comparison.json`、`jar-comparison.json`、`build-record.json` 和 `build.log`。

较早 `author-build-20261004T172656Z` 也编译成功；随后根 Agent 指出两行缩进，并要求补边界注释。该目录保留 `superseded.json` 与原包，最终源码重新干净构建到上面的新目录；旧构建没有交付给独立测试。没有失败构建被删除或改记为通过。

## 验证边界

作者自检包括源码差异检查、`git diff --check`、干净编译打包、1107 个 tracked API 文件前后摘要、旧新精确 JAR 与全部内嵌依赖对照。Java 单元测试被跳过，不能把 `BUILD SUCCESS` 记成产品行为通过。

旧包实际旁路由独立测试 Agent 复现；最终候选的别名拒绝、公共资产兼容及专用媒体授权/HEAD/Range/Unicode 行为由该 Agent 在专用合成 runtime 继续验证，本作者尚未收到最终 HTTP 结论。作者先做了路由静态审查，后按授权实现产品，二者由同一 Agent 完成，不将作者静态检查称为独立修复审查。

本作者没有启动、停止或访问服务，没有连接数据库/Redis，没有浏览器、生产副本或生产操作，没有修改测试、Shiro、前端、依赖，也没有提交、推送或创建 PR。当前候选仅作为可供独立验证的冻结包。
