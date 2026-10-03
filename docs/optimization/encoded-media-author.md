# 百分号编码媒体引用：作者实现与构建记录

同源存储 URL 使用合法百分号编码时，原本的下载授权候选查询可能漏掉对应课程或单元。例：实际存储键含 `+`，字段保存 `%2B`；`UriUtils.encodePath` 保留路径中的 `+`，因此两个 `LOCATE` 条件都没有命中，即使后续 `URI.getPath()` 的精确路径比较本来能识别该资源。

本次产品实现位于 `LocalDownloadAccessService`，包含两项共同冻结的改动：

- 保留原始键、`encodePath` 键的候选条件，追加 `LOCATE('%', CONCAT_WS(...)) > 0`。字段中出现字面百分号的行交给现有引用解析与授权检查，不枚举 `%2B` 或特定编码形式。合法百分号 URL 中的保留字、未保留字、UTF-8 字符、十六进制大小写与部分编码都不会仅因不等于某一种标准编码而被这一预筛条件遗漏。
- 在 URI 的精确路径匹配前，校验 raw path 中每个连续 `%HH` 字节段是严格有效的 UTF-8；使用 Java 8 标准库 `CharsetDecoder` 和 `CodingErrorAction.REPORT`，随后仍由 `URI.getPath()` 的结果进行完整路径相等比较。校验结果不作为第二次解码的输入。

原始存储键直接相等仍按字面处理。绝对 URL 仍须与配置的 scheme、raw authority 相同，完整路径须等于配置路径加当前 key；`+` 保持加号，`%252B` 一次解码后的字面 `%2B` 不会被当成 `+`。候选命中不产生授权，当前课程访问、删除状态、单元显示条件及其他模块已有授权仍由原有代码判定；没有修改数据库内容、schema、依赖或文件资源。

严格 UTF-8 检查是在 root 审查提出新候选可达范围的风险后加入。作者用项目固定 Zulu Java 8 实际探针确认：`a%FF.txt` 与合法 `a%EF%BF%BD.txt` 的 `URI.getPath()` 都产生 `a�.txt`；`%C0%AF`、`%ED%A0%80` 和被普通字符中断的多字节段也产生替代字符。单纯追加百分号候选条件会使这些非法字节进入原有替代解码路径，因此最终实现须同时拒绝非法 UTF-8，并保留合法编码的真实 `�` 字符。Java 8 的 [URI 官方文档](https://docs.oracle.com/javase/8/docs/api/java/net/URI.html)明确说明解码错误会使用 U+FFFD，严格解码处理见 [CharsetDecoder 官方文档](https://docs.oracle.com/javase/8/docs/api/java/nio/charset/CharsetDecoder.html)。探针保留在作者私有产物目录的 `UriEncodingProbe.java` 与 `uri-java8-probe.log`；它证明固定 JDK 的行为，不等同于最终业务测试。

候选查询继续使用常量表名和列名，资源键继续通过 JDBC 参数绑定。原查询已对拼接元数据进行 `LOCATE` 扫描；这次增加常量百分号判断，并扩大回传给 Java 引用解析和授权检查的候选集合。若某张表大量字段含百分号，则每次查该表都可能回传大量额外候选；本次没有测量规模、延迟、内存或生产容量。

root 对当前私有真实数据副本只读统计得到：5 条课程中的百分号行为 0；83 条单元中为 9；`teaching_additional_work`、`sys_config`、`teaching_news` 当前均为 0 行。这里单元表的额外候选上界是 9 行，具体新增数量取决于这些行与原来某个 key 的命中集合是否重叠，不能声称每次固定新增 9 行。7 张业务表前后核对一致。聚合记录是私有产物目录中的 `private-candidate-counts.json`；没有将业务内容写入此文档。

本次候选完整性说明针对字段中直接保存的百分号 URL。HTML 把百分号额外写成数字实体，或 JSON 使用 Unicode 转义隐藏百分号，属于额外表示层；若整段原始 key 和标准编码 key 也都不出现，则不由本次字面百分号条件保证可达。这一边界已告知 root，最终验收范围由独立检查记录明确。

作者构建使用固定工具清单中的 Zulu `1.8.0_504` / `8.96.0.205-CA-macos-aarch64` 和 Maven `3.9.16`；本轮还只读核对两份已下载工具归档的 SHA-256 与 `api/dev/toolchain.json` 相符。命令在本 worktree 的 `api/` 执行：

```sh
JAVA_HOME=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home \
  /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/apache-maven-3.9.16/bin/mvn \
  -B -s dev/maven-settings.xml \
  -Dmaven.repo.local=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/m2 \
  clean package -DskipTests
```

2026-10-03 21:11:30（Asia/Shanghai）完成，退出码 0，`BUILD SUCCESS`。**本命令和父 POM 均跳过 Java 测试运行；日志明确出现 `Tests are skipped.`。这只证明 Java 8 编译、打包成功，不是测试、运行、角色授权、浏览器、人工验收或生产交付证据。** 没有单独配置或声称启用 fast 参数。

准确构建记录保存在本机私有目录 `.devspace/artifacts/encoded-media-root/author-build-20261003T131119Z/`，包括 `clean-package.log`、`tool-versions.log`、`backend-source-manifest.json`、`product.diff`、`build-record.json` 与新的冻结 JAR。源清单覆盖两个后端模块的 main/test 文件、POM 与本次 Maven settings，并确认构建前后清单相同。此目录未包含运行环境配置或登录凭据。

| 项目 | SHA-256 / 来源 |
| --- | --- |
| 源 worktree base | `152aaef2231c1282df39055350db93aafe89a818`（PR #56 分支提交） |
| 产品 Java 文件 | `4d52841396608e5ed7d0ff51ce33c4a58956d6e6c2fbf1730a052256919c7aca` |
| backend-source-manifest.json | `17f0d6e3b652791d25d9ff3331f83d9a5a3fde2de528f14a3d6e799ff3ab30a3` |
| clean-package.log | `5a6a0352d7c5051a462d98f71335202d73e9547126d0f3d6296cf2fb123329d8` |
| 冻结 teaching-open-2.8.0.jar | `4578567dcedc18bf8a5f69758f8209d9b7bc74fc24f24f0d50196ec97e684c42` |
| PR #56 原 JAR（构建前后） | `95d9ad3ad4ada70897974071fec283a0c29bb703e2cdcb41397e80f77ebbd7c7` |

新冻结 JAR 与本 worktree 构建出的 JAR 摘要相同，私有冻结副本设为只读。PR #56 原 JAR 仅做摘要核对，路径为 `.devspace/worktrees/unicode-media-paths/api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar`，前后内容相同。作者没有启动应用、登录运行环境、写数据库、操作生产、提交或推送。独立测试与 root 包内差异核查另行记录，不与作者探针或 `BUILD SUCCESS` 合并表述。
