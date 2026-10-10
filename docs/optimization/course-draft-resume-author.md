# 课程作品恢复实现记录（2026-10-03）

实现工作树：`/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/course-draft-resume`，分支 `fix/course-draft-resume`，基础 HEAD `8f5bf1e272e57a3460c0414b506925c1395a18d2`（PR53 `fix/python-source-loading`）。实现 Agent 只改产品三份文件；测试由另一 Agent 负责，根 Agent 负责后续整合。未提交、推送、合并或部署；未访问浏览器、生产、数据库、凭据；未启停服务、安装依赖或修改 Git 历史。

## 改动及行为

- `web/public/scratch3/persistence.js`：Scratch 与 ScratchJr 共用状态机；课程入口没有显式 `workId` 时始终调用 `unit(unitId)`，不再因为 ScratchJr 已带 `workFile` 而跳过。`mineWorkId` 存在则调用 `info(mineWorkId)`，成功载入学生文件后绑定原作品 ID、学生作品名及记录中的 `courseId/additionalId/departId`。只有成功返回的单元确无已有作品时读取 `unit.courseWork_url`。
- `web/public/python/persistence.js`：同样先发现课程作品，再读取本人详情；课程入口携带的 `url/workFile` 不再直接决定打开模板。首次无已有作品使用单元返回的模板 URL 与单元名。
- `web/public/python/editor-bridge.js`：补充 `getUnitWorkInfo?unitId=...` 的真实单元读取适配器，复用既有 `request` 的授权头、超时及业务失败处理。无后端接口或模型改动。

正常显式 `workId` 入口优先读取指定作品，不再课程发现，也不按入口的旧单元/任务提示重绑定；记录自身的归属为准。

显式 `resetTemplate=1` 保留“打开老师模板、保存更新同一份作品”的语义。已有作品时先读取详情，保留原 ID 和记录归属；课程重做从对应单元读取当前权威模板；附加作业重做使用列表传入的模板文件。重做名称沿用原入口语义：入口 `workName` 优先，课程缺少该参数时取 `unit.unitName`。无原作品的附加作业重做仍可按已有模板入口首次创建。

## 失败与一致性边界

读取单元失败、返回空对象之外的空结果、已有作品详情失败、文件 URL 缺失/空白、类型错误、打开文件或 Python 应用失败，均不回退默认项目或老师模板；`ready=false` 使保存入口停用。UI 已有“重试加载”入口仍可用，Python 查询失败提示已明确可重试。

一致性检查包括：

- 单元返回非空 `id` 时必须等于查询的单元 ID；返回练习类型时必须匹配当前编辑器（Scratch 接受 1/2，ScratchJr 3，Python 4）。
- `mineWorkId` 若提供必须是字符串；发现后的详情 `courseId` 必须等于入口单元 ID。不要把单元自身 `courseId` 当作作品单元归属：前者是课程主表 ID，后者是单元 ID。
- 详情返回非空 `id` 时必须等于请求的作品 ID；沿用旧模块容许详情 mock 不提供 `id` 的兼容性。
- 显式重做若入口单元/附加作业提示与原作品归属冲突，拒绝打开和保存，避免拿另一单元模板更新原作品。

本次加载先使用局部 `workId` 和局部上下文，文件成功打开或代码成功应用后才写入持久化状态。首次课程发现或详情/文件失败时不会提前记住发现 ID，因此下一次重试会重新查询课程，避免沿用一次失败的绑定。

## 自检证据

三份目标文件的 `node --check` 和工作树 `git diff --check` 已通过。实现 Agent 运行以下四组既有 Node 回归，合计 **53/53 PASS**：

```text
node --test tests/scratch-persistence.test.cjs tests/scratchjr-bridge.test.cjs tests/python-source-loading.test.cjs tests/student-assignment-feedback.test.cjs
```

其中 Python 来源加载测试执行实际页面脚本与桥接适配器，但网络、DOM/编辑器与文件均为测试替身。该结果属于本实现的自检，不能称为独立审查或学生人工验收。另一 Agent 编写实际课程入口到三种持久化状态机的独立新测试，并将旧 Python persistence 的重做 mock 补成与真实适配器一致的单元查询能力；结果由其报告。

## 剩余验证及风险

- 实现 Agent 没有访问实际 API、数据库或编辑器引擎，因此尚未以真实保存/附件访问证明端到端更新；根 Agent 可用授权的隔离环境完成运行检查。
- 根 Agent 已回报独立代码审查通过，首轮隔离真实 HTTP/MySQL 恢复 **31/31** 通过，旧版 **17/31**；后续扩大对照及最终运行证据由根 Agent 单独记录。本实现 Agent 未运行该检查，不将首轮数字替代最终冻结运行证据。独立测试 Agent 尚在补真实适配器 mock 覆盖；根 Agent 负责最终整合构建与后端授权逻辑核查。
- 前端复用现有 `mineWorkId` 查询。如果真实数据库已有同用户同单元多份作品，查询选择及后端重复记录处理仍属于现有接口行为，本次没有新增后端去重或迁移。
- 已有作品即使显式重做，仍要求详情中有可用附件及正确类型；无法确认原记录时暂停，避免重做分支掩盖错误。额外作业已有记录重做缺少模板 URL 时同样拒绝默认文件兜底。
- 工作树中后来出现其他 Agent/根 Agent 的 `api/dev/`、`web/tests/course-draft-resume-live.cjs` 等测试资产；实现 Agent 未编辑这些文件，不应混称为自己的产品改动。

## 产品冻结

实现 Agent 确认产品可以冻结；冻结后不再修改产品，除非另有具体缺陷证据。重新核对三份文件 `node --check` 和 `git diff --check` 均退出 0。产品差异仅三份文件，**77 行新增、16 行删除**；以下 SHA-256 用于根 Agent 整合前后核对：

| 产品文件 | SHA-256 |
| --- | --- |
| `web/public/scratch3/persistence.js` | `a335e902d727401c5044cd99f2faea28c7f9c3e0210da537d07bcfdf00066b40` |
| `web/public/python/persistence.js` | `7305e2bd9ee18ddf8fa419a1ea436a7f14c23d6d0aa50b1e3d7d7829209499be` |
| `web/public/python/editor-bridge.js` | `7eec9c27025cde073c9f7a7ce717cbed14758c6ae5c5108339b01935aa3032d7` |
