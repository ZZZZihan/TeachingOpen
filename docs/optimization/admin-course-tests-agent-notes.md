# 管理员课程与单元工作台：测试 Agent 记录

记录日期：2026-10-03。执行 Agent：`/root/admin_tests`，按用户指定使用 GPT-6.1-sol、Ultra。隔离工作树为 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/admin-course-workbench`，分支 `feature/admin-course-workbench`，旧基线为 `fbf8097f0616cb865ce6ee109ca806b42f4767ef`（PR 42 课程表单恢复候选）。开始与中断恢复时均先核对现有文件、进程与证据，继续使用本任务独立的 `admin-course` 浏览器 session。

本 Agent 只编写测试、实际组件合成预览与本记录；产品的两个列表及样式由 `/root/admin_ui` 修改。root 独占 `web/tests/admin-course-preview/verify_backend.py`，负责真实隔离 API 检查、最终审查和交付。本 Agent 没有修改产品源码、依赖或锁文件，没有访问真实后端或数据库，没有提交、推送、开 PR、合并或部署。没有独立 Fast 开关，不声称已启用。

## 冻结结果与统计范围

最终证据目录为 `docs/optimization/evidence/admin-course-workbench/`。测试已经冻结，未因计数好看而扩大范围。

| 证据类别 | 实际结果 | 执行阶段与退出状态 |
| --- | --- | --- |
| 真实 SFC 脚本与共享 mixin 行为 | 57/57 | 最终产品文件；Node 退出 0。其中 9 项复现旧基线，48 项核对候选行为 |
| 实际 Vue/Ant 合成浏览器主检查 | 62/62，意外渲染异常 0 | 最后一次旧批删确认失效修复之前；CLI 退出 0 |
| 旧批删确认受影响流程的实际 DOM 复验 | 4/4，浏览器异常 0 | 最终产品文件；CLI 退出 0 |
| 旧基线实际组件截图及初始路由请求观察 | 6 张截图、6 个尺寸观察 | CLI 退出 0；确认单元旧页存在 1 次无课程条件和 1 次带课程条件请求 |

这些是不同证据层与执行阶段，**不相加为单一通过总数**。主浏览器 62 项覆盖的布局未在最后修复中改变；最后修复只涉及批删确认上下文和回调身份，实际 DOM 专项重新执行了受影响流程。没有宣称 62 项都在最终哈希上重跑，也没有将旧失败算入通过项。

最终产品 SHA-256 与合成构建清单一致：

| 文件 | SHA-256 |
| --- | --- |
| `web/src/views/teaching/TeachingCourseList.vue` | `082b0fd45c5c0e036380130b8c3e282c599581b4d8c5d2da642808d6e777e353` |
| `web/src/views/teaching/TeachingCourseUnitList.vue` | `543c88b64dade17faa0366e4e19fbb6e97e82f8f53c95f7d1343589b9e7ce1d7` |
| `web/src/views/teaching/course-workbench.less` | `51986d75dc6db0270be6fa856e536af8c8289cc4813cda6b0c0b87c40c2b4ded` |

结构化汇总为 `admin-course-test-summary.json`；最终构建来源为 `admin-course-final-preview-source-manifest.json`；57 项原始结果为 `admin-course-behavior-final.txt`。两个浏览器阶段分别保存在 `admin-course-after-browser.json` 与 `admin-course-stale-confirm-browser.json`。

## 先复现的旧行为与实际修复回归

`admin-course-workbench.test.cjs` 执行实际组件 `<script>` 与实际 `JeecgListMixin`，请求使用可独立完成或拒绝的 Promise。它没有复制产品查询/删除算法，也没有仅断言源码字符串或模板形式。9 项旧基线行为包括两页各自的未提交输入进入分页请求、旧响应覆盖新查询、业务失败静默保留旧行、连续删除发出两个请求，以及单元初始课程路由同时发出无条件与带条件请求。

48 项候选行为检查覆盖：查询/重置回第一页且保留每页数量；未提交输入与已应用条件隔离；分页、排序、重试、导出沿用已应用条件；网络/业务/畸形响应清理和恢复；旧成功或失败响应不能改写当前结果；选择仅对应当前行；删除防重复与错误恢复；删空末页回有效末页；批删确认和快照；组件销毁后的晚响应；原新增、编辑、字典、单元路由入口；导出 JSON 拒绝及 OLE2 签名判断；导入失败/成功/201 报告；跳页合法性；资源 URL 与封面降级；已应用条件名称快照；单元路由切换。

root 在最终审查指出旧批删确认仍可能在同组件课程路由变化后删除旧 IDs。本 Agent 先用真实方法留下 3 项失败，分别是两页查询/重置变化与单元课程路由变化后旧确认仍发 DELETE（`admin-course-stale-confirm-before.txt`）。UI Agent 增加列表请求版本、选择集合与确认身份检查。本 Agent 随后核对同集合顺序改变仍沿用原快照、变化后的旧确认发 0 个 DELETE、旧回调不能解锁新确认。最终 57 项全部通过。

实际 Ant 确认框专项打开课程 1 的批删确认，再通过地址栏 hash 在同一 Vue 组件切换到课程 2，点击仍打开的旧确认。实际观察：旧选择清空、0 个 DELETE、新课程的 9 行仍显示、浏览器异常为空。没有注入 Vue 内部状态、真实 token 或真实服务。请求轨迹与截图保存在专项 JSON 及 `admin-course-after-unit-stale-confirm.png`。

## 浏览器行为与视觉观察

使用已阅读的 `/Users/xuzihan/.codex/skills/playwright/SKILL.md` CLI 方法，`npx` 已核对可用；浏览器通过独立 session 的 CLI `run-code` 执行可提交脚本。预览加载实际两个列表、实际 Vue、Ant Design Vue 及共享列表 mixin。62 项主要覆盖两页的 1440/768/390 尺寸、维护按钮位置、查询 Enter、页码/数量/排序、未提交输入刷新、加载、网络/业务/畸形失败重试、空态、新增/编辑/字典/单元维护入口、实际合成文件选择上传、选中导出、删除失败、慢速删除操作锁和单次 DELETE。

旧基线的整个文档宽度没有超出视口，不能声称旧页存在全页横向溢出。实际 390 像素时，课程表内部可视宽度 342、内容宽度 538，单元表内部可视宽度 342、内容宽度 495；截图可见列宽压缩和中文多行碎裂。新页三尺寸的文档宽度等于视口，工作台及维护按钮均在视口内，长名称和简介正常换行。视觉观察来自合成内容，属于本 Agent 检查，非管理员人工验收。保留 6 张 before、16 张主 after、1 张最终专项，共 23 张截图。

初次真实组件渲染暴露了产品缺陷：`APopconfirm` 直接包裹带 `disabled` 的原生 button，触发 Tooltip 的 `propsData` 异常，10 行对应 20 次 Vue 渲染错误，删除按钮未渲染。已向 UI Agent 直接报告，双方核对 Ant 行为后由其改用 span 包裹；重新加载后的主检查没有该渲染异常。初次证据单独保存在 `admin-course-initial-render-failure.txt`。

## 合成替代范围与边界

- 请求层替换为 loopback 的 `api.js` 与 `server.py`。服务只返回显著标注的合成课程/单元，提供可控慢速、503、业务失败、畸形响应和空态；不代理真实 API、不读取数据库。
- 字典与部门选择替换为测试专用控件，保留查询模型和入口交互。真实远程字典、部门树与平台布局没有在此预览中验收。
- 新增、编辑和字典维护弹窗替换为实际 Ant Modal 内的合成入口提示。本测试核对原列表正确调用 ref、传递行记录/字典代码和保持入口；**不证明真实维护表单、课程地图编辑或保存事务成功**。
- 使用项目现有合成 bootstrap 和测试 util；`Vue.ls` 的 token 返回 undefined，没有注入真实登录凭据，没有登录或绕过验证码。
- 合成导出只用 OLE2 文件头检验列表下载行为；合成上传只验证文件输入、接口调用与列表反馈，不解析 Excel。真实 Excel 内容、导入数据库、201 报告实际文件和媒体资源不在此证据范围。
- 预览不含完整平台导航、真实登录管理员身份或生产数据，不能称为端到端真实验收或生产交付。

root 另行执行并报告 37/37 真实隔离 Java/MySQL API 检查；本 Agent 只读核对其 JSON 为 37/37、`exception=null`，没有重跑。root 的证据位于主工作目录 `.devspace/admin-course-actual-api.json/.txt`，覆盖真实父课程名称、完整维护字段及 false/0、四种排序、过滤分页、精确名称、教师/学生/匿名管理拒绝、所选导出 OLE2 文件头、末页删除 total、68 张表与附件恢复。该项的执行者和范围与组件证据分开；也不是登录后浏览器、XLS 内容或真实导入验收。

## 失败与重试记录

1. 首次旧页检查只改变已有单元页 hash，错误地期待再次执行 created；随后改为新 document 入口。`admin-course-baseline-browser.txt` 保留该失败。
2. 旧页重试将并发请求到达服务的顺序当作 dispatch 顺序；线程服务可先接收带条件请求。改为核对各 1 次请求，dispatch 顺序由方法 Promise 轨迹核对。`admin-course-baseline-browser-retry.txt` 保留失败。
3. 前述 Popconfirm 渲染错误为真实产品缺陷，由 UI Agent 修复；初次渲染错误不列入主通过结果。
4. 主浏览器首次完成 28 项后，确认按钮定位把 Ant 的“删 除”与行按钮“删除”混淆，未发送 DELETE，等待错误提示超时。改为确认提示内的明确定位；`admin-course-after-browser-first.txt` 保留失败。旧临时调用器返回 error 时 CLI 仍可能退出 0，故该次不以退出码判通过。当前 `run-check.cjs` 会同时检查结果 error/失败用例并退出 1。
5. 旧确认竞态的 3 项失败是修复前真实方法证据，未列入通过总数。早期旧快照断言要求改变选择后仍删除旧 IDs；新合约明确禁止，已改成同集合 reverse，另立变化集合的拒绝回归。UI Agent 曾在测试尚未冻结时跑到该旧断言，以其最终完整检查记录为准。

## 可复现命令

从隔离工作树根目录执行方法测试；此命令已执行，退出 0：

```bash
cd /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/admin-course-workbench
node --test web/tests/admin-course-workbench.test.cjs
```

合成预览构建使用已有 `web/node_modules`，不安装依赖。当前最终 after 构建与旧 before 构建均退出 0；after 构建保留最终来源清单，before 由上述 Git 基线取得原组件：

```bash
node web/tests/admin-course-preview/build.cjs /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/admin-course-preview/before fbf8097f0616cb865ce6ee109ca806b42f4767ef
node web/tests/admin-course-preview/build.cjs /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/admin-course-preview/after
```

运行前核对已有服务，不重复启动或操作其他任务的端口。本任务 18137 当前服务为 PID 89023、统一执行 session 98646，目录是主目录 `.devspace/admin-course-preview`；只绑定 `127.0.0.1`，已留给 root 视觉审查。18133、18111 及其他运行服务不属于本 Agent。

```bash
lsof -nP -iTCP:18137 -sTCP:LISTEN
# 仅当此端口空闲时，在单独终端启动：
python3 web/tests/admin-course-preview/server.py --directory /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/admin-course-preview --port 18137
```

确认 `npx` 可用，打开独立 session 后串行执行。每次证据路径必须新建，保留旧失败与重试；runner 会写 `.cli.txt` 和结构化 JSON。以下是可复现命令，**不是声称已经执行的另一次全量浏览器计数**：

```bash
command -v npx
/Users/xuzihan/.codex/skills/playwright/scripts/playwright_cli.sh --session admin-course open http://127.0.0.1:18137/after/
node web/tests/admin-course-preview/run-check.cjs baseline /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/admin-course-baseline-recheck.json
node web/tests/admin-course-preview/run-check.cjs browser /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/admin-course-browser-recheck.json
node web/tests/admin-course-preview/run-check.cjs stale-confirm /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/admin-course-stale-recheck.json
```

列表 HTML 明示“本机合成组件检查”。浏览器截图写入本工作树 `output/playwright/`，已筛选复制到可提交证据目录。`.devspace/`、`.playwright-cli/` 与 `output/` 是私有运行产物，不应整目录提交。root 审查时只需选择本任务新测试、notes 与可提交 evidence；真实 API 脚本由 root 单独审查。

最终完整 `npm test`、`npm run build` 与产品 ESLint 由 UI Agent 执行；其记录报告最终 279/279、退出 0，以及 build 退出 0、12 项既有 CSS 顺序/体积告警。不是本 Agent 执行结果；详见 `admin-course-ui-agent-notes.md` 及该 Agent 私有日志。当前留待 root 的是最终审查、组合和交付，实际平台管理员人工体验、真实选择器/媒体/Excel 与部署仍是各自独立的边界。
