# TeachingOpen 精确候选后端空缓存构建审计

本记录只确认从精确提交源码、私有空 Maven 缓存完成依赖解析、编译和打包，以及与现有冻结 JAR 的文件内容比较。Java 测试由父 POM 默认设置跳过；没有运行任何服务或业务验收。

- 源提交：`06ab2040780f33296e93c97d29d00e80cbcc2f65`
- api Git 树：`150a3a0b738c3e635c5bf1eb7be467c4d0ee2266`
- 源文件数量：1141；构建后摘要差异：0
- 原始候选 worktree HEAD 在构建前后均为上述提交；tracked 文件无改动，已有未跟踪 `.playwright-cli/`、`output/` 保留，归档没有包含它们。
- 初始 Maven 缓存：0 个条目，0 个文件（见 `pre-build.json` 和 `build-run.json`）。
- 项目 settings SHA-256：`e89e5d81032455d4dfe256e1fd905be42208697e072978a05886af89b9ed9021`
- 使用额外 `-gs empty-global-settings.xml`，覆盖全局 settings；`MAVEN_SKIP_RC=true`，本次移除可影响 JVM/Maven 的自定义参数变量。
- Maven/JDK 实际版本：见 `tool-versions.json`；本次未修改机器级配置。

## 构建命令

```sh
JAVA_HOME=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home MAVEN_SKIP_RC=true /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/apache-maven-3.9.16/bin/mvn -B -s dev/maven-settings.xml -gs /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/completion-audit-20261005/clean-backend/empty-global-settings.xml -Dmaven.repo.local=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/completion-audit-20261005/clean-backend/cache clean package
```

执行目录：`/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/completion-audit-20261005/clean-backend/api`
开始 UTC：`2026-10-04T21:26:24.088880+00:00`；结束 UTC：`2026-10-04T21:29:02.192428+00:00`。
退出码：`0`；耗时 158.103 秒。
Maven 日志 `BUILD SUCCESS`：True。日志 SHA-256：`0433fe9b69bc3374020f16f31bf2c891d95dd82d025fa2cc4516c8cb00d4acec`。
实际下载记录：983 条，仓库标识：central-https, jeecg。

## Java 测试状态

父 POM `skipTests=true`，Surefire 配置 `<skipTests>${skipTests}</skipTests>`。实际日志出现 `Tests are skipped.` 2 次。此轮 Java 测试未执行，不能将编译打包成功写成测试通过。

## JAR 与冻结产物比较

新 JAR：`/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/completion-audit-20261005/clean-backend/api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar`
字节数：112462842；SHA-256：`3f2347f87f270c126b24101998dfb47b4746c101488b483935e770cfc19c81e1`。
冻结 JAR：`/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/account-recovery-20261005/api-author/teaching-open-account-recovery.jar`
冻结 SHA-256：`67568eeaecea8e8d7342088767eeef2d7fcee45d61afffa0fb559b7808664016`。
整包字节相同：False。

`BOOT-INF/lib/` 共 209 个 JAR：外部依赖 208 个，项目 reactor 产物 1 个。路径集合相等：True。外部依赖按路径和字节与冻结包相等：208/208。全部版本、Maven 坐标与单文件摘要见 `dependency-inventory.json`。

`BOOT-INF/classes/` 945 个文件（class 362，resource 583），与冻结包路径集合和文件内容相等：True。比较没有排除任何 class/resource 文件；只忽略 ZIP 时间和目录条目的空 payload。

- 嵌入 JAR 字节差异：`BOOT-INF/lib/jeecg-boot-base-common-2.8.0.jar`；新 SHA-256 `533d344b11c969af9f963cf8880d55baad5d2d0ff37ed0da4d8815fed14fab80`；冻结 SHA-256 `324cca14df6202cec0950a9abea63ea3a3c4f8e7c07a9d7f256fb0ff03954c67`。
- 对上述项目 JAR 解包后：路径集合相等 True，全部 111 个文件 payload 相等 True；ZIP 元数据不同条目 148，字段为 `date_time`、`external_attr`。原因判定：嵌套文件路径与全部 payload 一致，差异位于 ZIP 时间和文件权限元数据；归档私有副本在构建前显式设为 0600，原始提交文件模式保留在 `source-api.tar`，实际唯一 `external_attr` 差异路径是内部 JAR 的 `META-INF/maven/org.jeecgframework.boot/jeecg-boot-base-common/pom.xml`，新包权限元数据 0o100600，冻结包 0o100644，与私有副本权限设置一致。

全 JAR 1,207 个文件路径相等，1,206 个文件 payload 相等；唯一不同 payload 即上述内部嵌入 JAR。完整内容摘要见 `jar-entry-manifest.json` 和 `result.json`，ZIP 元数据逐条比较见 `zip-metadata-comparison.json`；没有排除任何文件内容差异。

## 结论与边界

结论：`PASS_COMPILE_PACKAGE_AND_DEPENDENCY_REPRODUCTION`。

本次从新私有缓存解析依赖，没有复制现有 Maven 缓存、修改依赖版本、关闭 TLS、启动服务、连接数据库/Redis、执行登录/验证码/安全探针、运行浏览器或替换冻结产物。没有修改产品源码、创建分支/PR或推送。成功只针对本机 macOS arm64 固定工具和本次网络状态，不能推及其他机器或生产。原工具来源与下载归档摘要记录于精确提交的 `api/dev/toolchain.json`；本次复用了该指定工具，并独立记录实际版本，没有声称重新下载或再核验工具分发包。
