# 百分号媒体引用：根代理审查

本记录区分实现 Agent 的构建、测试 Agent 的 HTTP 对照和根代理的代码/产物审查。它不是师生人工验收，也不是生产部署证明。

根代理在产品冻结前审查了候选查询与 `references`、`exact` 的调用关系。原查询仅匹配原始 key 和一种 `encodePath` 表示，不能穷举 URL 合法的部分编码及十六进制大小写。追加字面百分号候选后，仍按原逻辑解析字段，完整匹配配置的 origin 和路径，然后检查当前课程、单元、作业或发布状态。表/列仍是代码常量，key 仍使用 JDBC 参数。未增加数据库迁移、依赖、缓存或文件读写路径。

扩大候选范围会使之前预筛不到的非法 UTF-8 引用进入匹配。Java 8 [URI 文档](https://docs.oracle.com/javase/8/docs/api/java/net/URI.html#getPath--)说明解码错误使用替代字符 U+FFFD；因此不能只扩大查询。根代理提出此风险后，实现 Agent 用固定 JDK 复现，并在冻结包中加入严格 UTF-8 检查：仅验证原始 URI 路径的连续 `%HH` 段，不把 `+` 变空格，不重新解码所得 key。URI 构造已检查转义语法，严格 decoder 拒绝非法字节；合法 `%EF%BF%BD` 仍能表示真实替代字符文件名。当前相对 `staticDomain` 的配置以 null scheme/authority 对照；绝对引用与配置不一致时仍拒绝。

独立读取两个实际 JAR 后确认：新旧包没有增删条目；唯一变化的顶层应用 class 为 `LocalDownloadAccessService.class`。内部 common JAR 容器摘要变化，但解包内容逐字相同；208 个外部依赖 JAR 逐字相同。新包 SHA-256 为 `4578567dcedc18bf8a5f69758f8209d9b7bc74fc24f24f0d50196ec97e684c42`，旧 PR #56 包仍为 `95d9ad3ad4ada70897974071fec283a0c29bb703e2cdcb41397e80f77ebbd7c7`。这是针对精确冻结包的核对，不是仅凭源码推断产物。

根代理执行本分支 `python3 -m unittest discover -s api/dev -p 'test_*.py'`，42/42 通过，退出 0；它验证既有开发工具，不替代本次实际 HTTP 媒体行为。作者的 Java 8 `clean package -DskipTests` 是构建证据，未执行 Surefire 测试。本次 HTTP 对照及数据恢复结果见 [独立测试记录](encoded-media-tests.md)，最终相关回归和组合候选见 [交付记录](encoded-media-pr.md)。

候选集合扩大可能增加 Java 解析与授权查询工作。真实数据副本只读计数显示 83 条单元中 9 条含字面百分号；这只是该副本的候选上界信息，不代表固定新增 9 条，更不是延迟或容量测试。真实副本包含课程内容，仅聚合结果进入交付记录。

范围限于直接保存的百分号 URL。把百分号再次表示成 HTML 数字实体或 JSON Unicode 转义，且原始 key 和标准编码 key 均不出现的情形，仍可能被旧预筛限制；本次不以无差别全表候选扩大范围。PR #56 的重复斜杠断言记录也不在本次改写。本次无界面变更，无新增浏览器视觉验收。
