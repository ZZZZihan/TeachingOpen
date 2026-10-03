# 班级课程上下文：实际 HTTP / DB 专项

2026-10-03，独立测试 Agent 用同一组行为判据、同一 Node 方法探针及同一冻结后端 JAR，对旧前端源与最终冻结的三个新 SFC 执行实际方法 → HTTP → MySQL 检查。旧源为 **8/20**，新源为 **20/20**，最终 Node 方法探针与 Python 工具均退出 0。旧源的失败仍是失败，没有使用“预期旧行为”反转判据。

旧源 `253f3fb4c44b500b6e4824adbf89da51ac89d50c` 的两种旧批量删除路径各发出一次 DELETE，并实际删除 A 的课程关系。A 的选择弹窗切换到 B 后确认，以及关闭后在 B 重开而未重新选择这两条路径，各发出一次 POST，实际把 A 的旧课程加入 B。冻结的新源在这四条路径均没有发出写请求，实际数据库中的 A 关系和 B 课程归属均满足判据。

| 同判据执行 | 方法 / HTTP + DB + 收束检查 | 证据 |
| --- | --- | --- |
| 旧源对照 | 8/20，退出 1 | [method-http-before.json](evidence/class-course-context/method-http-before.json) |
| 冻结新源 | 20/20，退出 0 | [method-http-after.json](evidence/class-course-context/method-http-after.json) |
| 自有服务最终收束 | 全部端口关闭、全部自有 PID 退出 | [runtime-cleanup-final.json](evidence/class-course-context/runtime-cleanup-final.json) |

20 项的分母包括 12 项实际组件方法及 HTTP 行为、6 项直接 SQL 读回、1 项启动器正常运行检查、1 项完整数据/附件恢复检查；不是 20 条独立用户故事。正常 B 查询、从新弹窗添加课程、通过共享表单修改开课时间、删除 B 的新关系四项在旧、新源均通过。开课时间另有 SQL 读回，新关系删除另有 SQL 计数，验证了新防护没有阻断这些正常动作。

## 方法和运行归属

测试工具为工作树 `class-course-context` 中的 `api/dev/verify-class-course-context.py` 与 `web/tests/class-course-context-live.cjs`。后者读取实际 `DeptCourseInfo.vue`、`SelectCourseModal.vue`、`TeachingCourseDeptModal.vue`、`JeecgListMixin.js` 和真实 `filterObj` 函数；旧源通过 `git show` 读取指定提交，新源读取冻结磁盘文件。原 Mixin 中的 JSX 用项目已有 Babel 依赖转译，没有删掉代码或复制待验证的上下文算法。

执行真实方法时，确认框、AntD 表单和 nextTick 使用调用夹具；GET/POST/PUT/DELETE 则向独立后端实际发送。合成管理员通过已有 FixtureApi 正常登录，Token 只经 stdin 传给 Node，未写入日志或共享 JSON。没有浏览器认证注入，也没有把方法夹具称为 Vue/AntD 渲染、复选框缓存或键盘/布局验收。这些实际 UI 项由根 Agent 单独验证。

后端精确 JAR SHA256 为 `4578567dcedc18bf8a5f69758f8209d9b7bc74fc24f24f0d50196ec97e684c42`。本项没有改后端产品代码、POM 或重新打包。新源实际运行与作者冻结哈希逐一一致：

- DeptCourseInfo：`818140750a44fd642d58e62a481a38fec147af5dce3a713c6f2913cf227ef42a`。
- SelectCourseModal：`367bdc581930e997f42a372a923ad543bb9389feeca97f0330da9db652e90f41`。
- TeachingCourseDeptModal：`a2f0808da084747ee810a7f3d07c32c0d0847745fb7328cc9829577ad0a849b8`。

工具哈希、产品哈希及全部净化证据哈希在 [live-tests-manifest.json](evidence/class-course-context/live-tests-manifest.json)。产品实现、离线专项测试、根 Agent 实际 UI 检查与本项独立真实 HTTP/DB 测试各有明确归属；本报告只对最后一类证据负责，不声称人工验收或生产交付。

## 数据恢复与保留的失败

本 Agent 自行创建并独占 `.devspace/class-course-context-1003`，使用 MySQL 13371、Redis 16444、后端 18175，前端 18176 留空。沿用现有运行工具核对数据库/Redis 归属、配置、PID 与 JAR；未访问其他 runtime 或生产。每轮只增加独立随机前缀的六门课程和三个初始关系，正常端点产生的课程关系也只指向这六门课程。

公共种子的两个班级 `org_category` 为 2，而真实班级课程控件要求 3。测试将这两个自有班级临时设为 3，使用对应的真实数据库记录，随后恢复完整 `sys_depart` 行快照。五个 `sys_user` 完整行快照留在内存并在登出后恢复，包含首次登录初始化的 `org_code`；HEX 空字符串正确还原为 SQL `''`。没有将密码、salt、Token 或原始身份快照写入共享证据。

旧、新两轮均确认：69 个表结构一致、68 个非 `sys_log` 表的全部行集一致、原始附件文件与字节一致；没有残留临时课程和关系。`sys_log` 排除的是本轮正常请求产生的审计记录，不是隐藏业务变更。各自结果 JSON 包含全部表集合、结构差异、非审计表行差异与附件比较结果。

第一次准备夹具在组件运行和登录之前失败，生成的一个课程标题为 33 字符，而实际列是 `varchar(32)`；标题已缩短。该准备诊断单独保留在 [method-http-initialization-failure.json](evidence/class-course-context/method-http-initialization-failure.json)，不能作为产品失败或通过项。原工具 finally 清理了已写入的部分课程并恢复快照，但该首次异常没有产出完整恢复比较，报告不补造这一证据。后续工具遇到启动器未输出 JSON 或夹具异常，也会保存清洗后的失败与恢复检查。

停止时的即时检查发现 MySQL 监听已关闭，但自有进程尚在正常退出收尾，该 false 结果仍保留在 [runtime-cleanup.json](evidence/class-course-context/runtime-cleanup.json)。随后有限等待并复核，最终后端 PID 42061、MySQL PID 41488、Redis PID 41492 全部退出，13371/16444/18175/18176 均无监听。runtime 目录及私有配置/证据保留，没有删除或操作其他环境。

复现应在授权串行窗口内使用现有 prepare-local/run-backend 归属守卫启动本项 runtime 和上述精确 JAR，再以新的输出名运行：

```sh
NODE_PATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/web/node_modules \
PYTHONPATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/encoded-media-references/api/dev \
python3 api/dev/verify-class-course-context.py \
  --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/class-course-context-1003 \
  --jar /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/encoded-media-root/author-build-20261003T131119Z/teaching-open-2.8.0.jar \
  --source /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/class-course-context \
  --output /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/class-course-context/method-http-rerun.json
```

加 `--ref 253f3fb4c44b500b6e4824adbf89da51ac89d50c` 可运行旧源对照。工具拒绝覆盖既有证据并以 0600 输出。依赖复用已有 `node_modules`，没有安装或升级依赖；本 Agent 未提交或推送。
