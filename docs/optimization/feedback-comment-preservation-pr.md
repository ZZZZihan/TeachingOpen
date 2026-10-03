# 批改与局部编辑保留未提交的评分和讨论

现有教师批改表单只提交 `teachingWorkCorrectList`，不提交讨论列表。旧后端仍无条件删除两个子表，再插入请求里的数据，导致一次正常批改就能删掉全部讨论；只改作品名称也会同时清空评分和讨论。已在 #36 精确 JAR 的隔离合成数据上实际复现。

本项基于 [PR #36](https://github.com/ZZZZihan/TeachingOpen/pull/36)，产品提交 `f791c31a8788e3dc7b85c074955fa1bf48d778bb`。`updateMain` 现在分别处理两个集合：未提供或 `null` 保留原行、ID 和审计字段；`[]` 明确清空；非空列表按原契约整组替换。替换仍在原事务中，任何一次插入失败都会回滚父表及两个子表。创建接口、角色范围、表结构和依赖没有改动。

## 验证

Java 8u504 / Maven 3.9.16 三模块干净构建成功。父 POM 跳过 Java 单元测试；本项证据来自实际合成 HTTP、MySQL、Redis、文件读取与数据库失败注入。最终 JAR SHA-256 为 `b87319a8e411d8f48c37de9e5589c486460c5c5f0306d8f5026281b5737a9b09`。

- 旧行为 **7/7** 按预期复现数据丢失；这是问题重现，不是通过修复验收。
- 新专项 **31/31**：零分保存、只改名称、显式 null、教师打开后学生新发讨论、本人读取、学生/跨班教师/匿名拒绝且数据不变、明确替换或清空一个/两个集合。分别让评分和讨论的第二次插入主键冲突，确认父表与全部子表逐列恢复。
- 同一新 JAR 的相关回归：作品管理 **134/134**、社区 **235/235**、学生提交 **95/95**。合计当前新行为与回归 **495/495**，不是 495 个不同用户流程。
- JAR 解压对照只改变该服务 class；内嵌 common JAR 因重新打包导致外部摘要变化，但解压后内容全部一致。没有其他应用、配置或库内容变化。
- 69 表核对仅 `sys_log` 增加（新候选验证前后 3,977 → 4,086）；其余 68 表与附件摘要恢复。测试前后原联调环境全库与附件相同；原源码跟踪及非忽略文件 5,731 项摘要一致。四个临时服务端口均已确认关闭，合成数据和冻结包保留。

第一次新专项在鉴权断言处停止：它误以为已登录 Shiro 拒绝使用 HTTP 401/403。实际与既有管理测试一致，为 HTTP 200、`success:false`、`code:510`；匿名为 HTTP 401/code 401。只修正测试的精确断言，未放宽产品授权。失败记录和后续完整通过结果分别保留，没有计入通过次数。

前端复用组合 `8ca9e35` 的 4,887 项既有产物；本次没有页面改动、重新构建前端或重复历史前端检查。旧/新冻结包的前端版本不同，对照结论只针对同一后端接口的数据行为。冻结新包 manifest SHA-256 为 `04baa03cc5a7f5d812a5979381e5aca452f50be077faa83a5239d0138ee67da1`。准确来源与停机记录见 [候选记录](evidence/feedback-preservation/candidate.json)，逐项证据见 [摘要清单](evidence/feedback-preservation/manifest.json)。

## 重跑与边界

在本地独立合成环境启动本 PR 的精确 JAR，从仓库根执行。脚本检查环境与运行包，不覆盖已有同名探针数据，结束时清理本次创建的数据。

```sh
python3 api/dev/verify-feedback-preservation.py --runtime "$runtime" --jar "$jar" --output "$output/feedback.json"
python3 api/dev/verify-work-management.py --runtime "$runtime" --jar "$jar" --java-home "$java_home" --output "$output/management.json"
python3 api/dev/verify-community-work.py --runtime "$runtime" --jar "$jar" --output "$output/community.json"
python3 api/dev/verify-work-submission.py --runtime "$runtime" --jar "$jar" --output "$output/submission.json"
```

显式列表继续采用整组替换语义；本项没有增加版本号或解决两个明确替换请求之间的并发覆盖。教师界面的零分序列化、加载失败/迟到响应和排版仍需下一项改造。本项是当前 Agent 工程自检，不代表完整认证浏览器流程、人工验收或产品化目标完成。没有远端合并或生产变更。旧包仅供必要的本地回退；它包含已复现的数据丢失行为，不应作为修复版本交付。
