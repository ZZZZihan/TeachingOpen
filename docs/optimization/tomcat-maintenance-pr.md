# 更新内嵌 Tomcat 并核对核心请求兼容性

日期：2026-10-03。基于 PR #32 `fix/work-view-metadata`，产品提交 `26edc47a4ff91d8b2d8fe92f4a268668e7f7dff3`。此次实际应用变更只有父 POM 中的 `tomcat.version`；另增加两个可复现的本机探针。

## 问题与变化

运行 JAR 中的 Tomcat core、EL、WebSocket 仍为 9.0.16。Apache 官方的 [9.x 安全公告](https://tomcat.apache.org/security-9.html) 包含此后多次修复，其中 multipart 的分部数量和头部大小限制与平台文件上传有关。此次三件套统一更新为官方维护版 9.0.122；保留 Java 8、Servlet 4 和原 Spring Boot 2.1.3 架构。版本与兼容要求见 [Apache 版本表](https://tomcat.apache.org/whichversion.html)。没有据此宣称所有公告的利用条件都适用于本项目。

构建后的三个 Tomcat JAR 逐一与 Maven Central 发布的 SHA-512 一致，见 [产物核对](evidence/tomcat-maintenance/artifact-integrity.json)。解包比较确认只有三个 Tomcat 依赖替换；1,142 个同名条目字节不变。重打包的 common JAR 归档字节不同，但内部 111 个条目全部相同，见 [打包差异](evidence/tomcat-maintenance/packaged-diff.json)。应用类、配置和其他依赖内容未变，无数据库迁移。

## 请求兼容与行为边界

所有接口检查使用同一台机器的隔离 Java/MySQL/Redis 和合成账号。实际旧版/新版传输探针各 9/9 符合对应预期，每个请求均小于 10 KB：

- 普通两个分部的文件上传成功，文件字节一致。
- 60 个分部的上传及额外 600 字节分部头在旧版被接受，新版被拒绝，文件和记录均未增加。
- 被拒绝后再次正常上传成功。
- 实际 WebSocket HTTP 101、匹配的 accept、masked ping/pong 及正常 close 通过。没有发送业务消息、账号订阅、令牌或云变量；这只验证容器传输，不证明应用层 WebSocket 授权安全。

证据：[旧版](evidence/tomcat-maintenance/transport-before.json)、[新版](evidence/tomcat-maintenance/transport-after.json)。更严格的 multipart 边界是有意的兼容变化；没有验收任意超长文件名或自定义 multipart 客户端，也没有进行拒绝服务或 CVE 利用测试。

实际新版回归结果如下，全部绑定同一 JAR 摘要：

| 范围 | 通过数 |
| --- | ---: |
| 课程管理 / 学习单元 | 188 / 80 |
| 作业管理 / 保存提交 / 社区访问 | 134 / 95 / 235 |
| 本地上传 / 文件归属 / 下载与媒体 Cookie | 46 / 76 / 88 |
| 班级任务列表 / 权限菜单 / 角色缓存 | 48 / 34 / 11 |
| 浏览次数 / 认证状态 / 恢复后业务 | 56 / 7 / 29 |

合计 1,127/1,127；上传套件中有 3 项为直接调用打包 Java 类的流故障检查，其余为真实 HTTP、数据库、文件及导出内容检查。新增传输 9 项和延迟探针 21 项均通过，总计 1,157 项。详见 [回归汇总](evidence/tomcat-maintenance/regression-summary.json) 及同目录各套件。作业管理首次调用缺少 `--java-home`，在参数解析阶段退出 2，没有执行应用操作；补全后 134/134，未把首次调用算作通过。

Java 8u504 / Maven 3.9.16 三模块 `clean package` 成功。父 POM 仍跳过 Java 测试，不将构建等同于 Java 测试通过。[构建日志](evidence/tomcat-maintenance/build.txt)

## 有限的延迟对照

每个接口按 1/4 个并发工作线程各预热 4 次、计时 48 次，旧版和新版分别完成 384 次计时请求，全部成功。临时作品的访问次数与四个草稿内容实际落库并在最后清理，另验证 HTTP keep-alive 复用。计时包括响应体读取，每次使用新的 HTTP/1.1 连接。

| 接口 | 并发 | 旧中位 / P95 ms | 新中位 / P95 ms |
| --- | ---: | ---: | ---: |
| 首页课程 | 1 | 4.319 / 6.389 | 3.632 / 4.257 |
| 首页课程 | 4 | 5.724 / 8.975 | 4.487 / 5.239 |
| 已分配课程 | 1 | 3.878 / 5.953 | 2.678 / 3.073 |
| 已分配课程 | 4 | 5.176 / 7.661 | 4.283 / 13.027 |
| 作品详情 | 1 | 4.141 / 5.244 | 3.171 / 3.597 |
| 作品详情 | 4 | 5.831 / 7.635 | 4.317 / 4.821 |
| 草稿保存 | 1 | 3.298 / 5.347 | 2.955 / 3.810 |
| 草稿保存 | 4 | 4.432 / 5.373 | 4.389 / 12.809 |

这是 Mac14,14 / 24 CPU / 64 GiB 共享开发机上的单批 localhost 观察；原始数据仅 5 账号、2 课程、2 作品，外加 5 个临时作品。新版两个并发场景 P95 更高，不能宣称性能提升或已证明无延迟回归。没有重复交错运行、持续负载、大数据、网络限速、TLS、HTTP/2、浏览器渲染或生产容量验收。原始逐请求样本和方法保留在 [旧版](evidence/tomcat-maintenance/http-before.json) / [新版](evidence/tomcat-maintenance/http-after.json)。首次旧版探针使用了不支持的 HTTPConnection 上下文管理方式，清理后改用 `closing`，最终两份报告均使用本提交脚本。

## 数据与复现

新版 JAR SHA-256 为 `be388932d612c21e078a0fb29ab21fb99f4e1f01b4ccdc12da70b5f4b1c44c68`。冻结包 `candidate-tomcat-maintenance` 与构建字节一致；干净来源和包摘要见 [candidate.json](evidence/tomcat-maintenance/candidate.json)。

演练前后 69 表中只有正常认证审计 `sys_log` 从 3,134 增至 3,710 行；其他 68 表及全部附件摘要一致。原联调环境的全库/附件未变，原源码 5,634 文件摘要未变。专用演练环境的 13336/16409/18131/18132 端口均已停止，数据、旧包和新包保留。[数据](evidence/tomcat-maintenance/data-preservation.json) / [源码](evidence/tomcat-maintenance/source-preservation.json)

在已启动的本机合成环境，从本分支根目录执行；变量指定自己的合成目录和新输出文件。旧版传输对照增加 `--expect-legacy`；各套件顺序运行，不共享写入夹具并发执行。

```sh
python3 api/dev/verify-container-http.py --runtime "$RUNTIME" --jar "$JAR" --output "$TRANSPORT_OUTPUT"
python3 api/dev/benchmark-local-http.py --runtime "$RUNTIME" --jar "$JAR" --output "$LATENCY_OUTPUT"
python3 api/dev/verify-work-management.py --runtime "$RUNTIME" --jar "$JAR" --java-home "$JAVA_HOME" --output "$WORK_OUTPUT"
python3 api/dev/verify-local-upload.py --runtime "$RUNTIME" --jar "$JAR" --java-home "$JAVA_HOME" --output "$UPLOAD_OUTPUT"
```

本项未改 UI，无浏览器或人工验收。Shiro、Spring、前端依赖及应用 WebSocket 权限另列产品化待办，没有因本次更新认定它们安全。没有远端合并、生产升级或部署。证据完整性见 [manifest.json](evidence/tomcat-maintenance/manifest.json)。
