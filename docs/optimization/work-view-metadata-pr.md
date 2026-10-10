# 浏览作品保持修改记录，并可靠累计浏览次数

日期：2026-10-03。基于 PR #31 的 `feature/local-candidate-switch`；产品提交 `03297e3e9153b079663981a73a07c04eb3ab5c2b`。本项仅修改作品详情的浏览计数写入及相关验证，不修改 UI、数据库结构、依赖或普通编辑行为。

## 问题与最终行为

原 `studentWorkInfo` 先读取浏览次数，再创建 `TeachingWork` 实体调用 `updateById`。`MybatisInterceptor` 在实体更新时填写 `updateBy` 和 `updateTime`，导致浏览被记录为编辑；先读后写还会覆盖其他请求刚增加的计数。此次在专用合成环境重新复现：已登录学生浏览后成为最后修改人；并发 8 个客户端的 64 次成功请求只增加 8 次，16 个客户端的 96 次成功请求只增加 10 次。

详情接口仍先检查现有作者、教师班级、管理员及公开状态权限，然后读取详情。计数改用带参数的单条 `UPDATE teaching_work SET view_num = view_num + 1 WHERE id = ? AND del_flag = 0`，只写浏览次数字段。没有匹配到有效作品或写入失败时不返回成功详情。现有非空 INT 计数字段保持不变，没有扩展为去重访问、独立访客或防刷统计。

接口路径、附件地址、返回结构和返回的读取时计数保持兼容；响应中的计数仍是本次递增前读取的值，不能用并发响应顺序判断最终数据库计数。正常作品编辑继续走原有更新与历史记录流程。权限检查与发布/删除操作之间的竞态不在本项验收范围。

## 实测结果

所有 HTTP 检查连接实际 Java/MySQL/Redis，使用 `recovery-a` 合成环境及临时作品，不是模拟 Mapper。登录通过既有 CLI 合成夹具，不代表真实浏览器登录。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 旧 JAR 对照 | 43/43 符合旧缺陷预期 | [legacy.json](evidence/work-view-metadata/legacy.json) |
| 新 JAR 专项 | 56/56：允许/拒绝、返回兼容、所有非计数字段不变、并发、失败与恢复、清理 | [fixed.json](evidence/work-view-metadata/fixed.json) |
| 恢复后业务 | 29/29；补充修改记录检查及全作品清理核对 | [recovery-fixed.json](evidence/work-view-metadata/recovery-fixed.json) |
| 社区权限回归 | 235/235：私有/公开/删除、评论、点赞和认证 | [community.json](evidence/work-view-metadata/community.json) |
| 作业保存提交回归 | 95/95：作者、任务、审计字段、版本历史和失败回滚 | [submission.json](evidence/work-view-metadata/submission.json) |

新 JAR 共 415 项真实检查通过。浏览专项分别以 1、8、16 个并发客户端完成 16、64、96 次成功请求，数据库分别增加 16、64、96；每组均核对全部非浏览计数列不变。这是受控计数正确性检查，不是生产容量结论。

故障路径通过临时作品达到 INT 最大值来触发实际数据库写入失败，确认无成功详情、全作品数据未变；移除该临时条件后正常读取计数。没有更改数据库全局设置或原有作品。

强化后的恢复验证在旧 JAR 上为 27/29，两个修改记录断言确实失败，证明检查能发现该回归；脚本在检查后恢复原始计数及审计字段，即使遇到旧缺陷也保留测试开始时数据。旧演练的 26 项结果保持原证据，不据此改称当时已通过新检查。见 [recovery-legacy.json](evidence/work-view-metadata/recovery-legacy.json)。

后端使用 Java 8u504 / Maven 3.9.16，三模块 `clean package` 成功。父 POM 跳过 Java 测试，不能把构建称为 Java 测试通过；上述业务结果来自真实 API。仍有既有内部 API/弃用警告，见 [build.txt](evidence/work-view-metadata/build.txt)。

## 数据、产物与复现

- 新 JAR SHA-256：`3ac73c633fd337d85f15e388182d37f2928939f2ba67cccc6765cd2074865b37`，运行的冻结包与构建 JAR 字节一致。旧对照为 PR #24 JAR `85f7746a3ae4b143f1a4ca4e5c043e11c81bf7d69f32c72b7dbaa190f6a0e85c`。
- 冻结包 `.devspace/candidate-view-fix` 配合既有前端构建；清洁源码提交、文件摘要与停止状态见 [candidate.json](evidence/work-view-metadata/candidate.json)。包装不会自行证明源码与构建对应，本次对应由干净构建记录及文件摘要提供。
- 演练前后 69 张表中只有 `sys_log` 增加正常登录/退出记录（3,071 → 3,134）；其余 68 张表及全部附件摘要一致，包含原作品所有修改字段。[数据核对](evidence/work-view-metadata/data-preservation.json)
- 原 `course-role-runtime` 数据与附件未变，主源码已有 5,634 项摘要未变。[原环境核对](evidence/work-view-metadata/source-preservation.json)
- 演练服务 13336/16409/18131/18132 均已停止，恢复数据与冻结包保留；原演示服务未改动。没有生产操作、远端合并或浏览器验收。

在按既有说明启动的隔离合成环境中，从本分支仓库根目录执行；`RUNTIME`、`JAR` 和输出路径须指向任务自己的环境，输出文件须不存在：

```sh
python3 api/dev/verify-work-views.py --runtime "$RUNTIME" --jar "$JAR" --output "$OUTPUT"
python3 api/dev/verify-community-work.py --runtime "$RUNTIME" --jar "$JAR" --output "$COMMUNITY_OUTPUT"
python3 api/dev/verify-work-submission.py --runtime "$RUNTIME" --jar "$JAR" --output "$SUBMISSION_OUTPUT"
python3 api/dev/verify-recovered-business.py --runtime "$RUNTIME" --jar "$JAR" --snapshot "$SNAPSHOT" --output "$RECOVERY_OUTPUT"
```

首项可增加 `--expect-legacy` 运行旧行为对照。最后一项要求同一恢复快照与成功的 `restore-result.json`。各套件顺序执行，避免同时修改共享夹具；工具均限制为本机合成环境并清理自己创建的数据。所有交付证据摘要在 [manifest.json](evidence/work-view-metadata/manifest.json)。
