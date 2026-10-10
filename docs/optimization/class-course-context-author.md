# 班级课程上下文隔离实现记录

2026-10-03；工作树 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/class-course-context`，分支 `fix/class-course-context`，基线 `253f3fb4c44b500b6e4824adbf89da51ac89d50c`。实现范围仅 `DeptCourseInfo.vue`、`SelectCourseModal.vue`、共享 `TeachingCourseDeptModal.vue`。未改全站 mixin、角色权限、后端或数据库结构；作者未访问浏览器、服务、数据库、凭据、生产，未安装依赖、编写测试、提交或推送。

已读适用 `/Users/xuzihan/AGENTS.md`、`/Users/xuzihan/.codex/AGENTS.md` 及本次直接任务授权，工作树内未发现更具体 AGENTS。直接证据来自根工作区 `.devspace/artifacts/role-flow-audit-1003/role-entry.md` 和本轮当前 SFC / 继承 mixin / 两个父入口代码。旧记忆仅作项目与验证边界线索，没有用旧状态代替本轮核查。

## 产品改动

- `DeptCourseInfo.open` / `clearList` 每次开启新上下文版本，先同步清课程关系选择、关系列表、分页、读失败和当前界面写锁，并关闭旧选择/编辑弹窗。相同班级重开也会递增版本，避免 A→B→A 时旧确认重新生效。
- 关系列表读请求绑定班级、上下文版本和请求序号；旧成功、失败、finally 均不再覆盖新班。当前失败保留空列表并提供重试；最小记录校验拒绝 null 或无有效 ID 的行。
- 批量删除确认捕获原班级、关系 IDs、选择版本；行删除改为显式 `$confirm`，捕获原班级、版本和当前记录对象。发送前检查上下文、关系存在和选择快照。切班、清空、重开、刷新、重新选择后旧确认均不发送 DELETE；行入口不允许仅传旧 ID 重新绑定当前班级。
- 两类删除确认共用 prompt 身份锁，重复点击只打开一份确认；旧 onCancel / onOk 不会解开新的确认锁。写请求期间锁定重复提交。已经发送的写请求继续保留原班级语义，本修复只抑制切班后的迟到界面更新，不声称可撤销服务端写入。
- `SelectCourseModal.show(deptId, contextVersion)` 每次清查询、选择、列表、分页并建立弹窗会话版本；列表读请求同时绑定会话、班级、请求序号。关闭或重开使旧读回调失效，当前读失败可重试。选择事件仅接受当前列表中的 ID，避免旧表事件迟到把旧课程放进新班选择。
- 选择完成发 `{ deptId, contextVersion, courseIdList }` 的原上下文和独立数组；父 `selectOK` 验证原班级与版本，以 payload 的原 deptId 构造请求。不会使用当前新班级重拼旧选项。父写结果只更新仍匹配的上下文与写请求序号。
- 共享 `TeachingCourseDeptModal.edit(record, context?)` 保留独立 `TeachingCourseDeptList` 的 `edit(record)` / `add()` 入口和无参数 `ok` 事件；只有班级面板入口才提供上下文并回传原上下文。nextTick、延迟表单校验和写返回均绑定弹窗版本，关闭/切班/重开后旧回调失效。校验及在途写锁阻止重复提交，失败保留填写内容供手动重试。
- 共享编辑表单仅注册 `openTime`，因此回填和提交只从表单取该字段，`id` / `deptId` / `courseId` 保留打开时的模型快照。避免对未注册身份字段调用 setFieldsValue 的 Antd 警告，也避免表单值改写关系身份。

选择限定当前读结果：切班、刷新、分页、搜索或重试都会清选择，用户需在新的可见结果中重选。这样确认不会携带未显示或旧读取结果中的关系。未设计跨页选择缓存。

## 修复过程发现与验证边界

作者自行执行三 SFC 的 `vue-template-compiler` 模板编译与 Babel 脚本解析：均无 errors / tips，脚本可解析；`git diff --check` 通过。依赖沿用根提供的既有 `product-candidate/web/node_modules`，无安装和全量构建。

独立测试代理首轮扩展测试发现重复 bulk / row 提示和 null 行未拦截，作者据此修正；其第二轮回报 59/59 PASS。根实际 Vue / Antd 预览发现 getCheckboxProps 在加载期间缓存 disabled，导致读完仍不可勾选，作者移除动态 getCheckboxProps，由读/写加载遮罩及业务方法 guard 控制操作。根第二轮回报复选框恢复、A→B 清选择、旧 A 行删除确认在 B 无 DELETE、B 添加课程和保存开课时间成功。

根真实组件预览另发现共享编辑回填未注册身份字段的旧警告，作者本范围修复后根最终复验通过：B 已存开课时间回填正常，经真实 JDate 修改为 `2026-10-05 10:30:00` 保存，PUT 保留 `relation-b` / `class-b` / `course-b` 身份，列表回显更新、弹窗关闭，error / warn 均空。独立离线最终结果、真实 HTTP / 数据库证据和完整组合构建由根汇总；本记录不把代理回报当成人工验收或生产交付。

最终产品已冻结，作者不再修改三 SFC。SHA-256：

- `web/src/views/system/modules/DeptCourseInfo.vue`：`818140750a44fd642d58e62a481a38fec147af5dce3a713c6f2913cf227ef42a`
- `web/src/views/teaching/modules/SelectCourseModal.vue`：`367bdc581930e997f42a372a923ad543bb9389feeca97f0330da9db652e90f41`
- `web/src/views/teaching/modules/TeachingCourseDeptModal.vue`：`a2f0808da084747ee810a7f3d07c32c0d0847745fb7328cc9829577ad0a849b8`

## 剩余与范围说明

- 作者产品改动已冻结，根真实组件复验完成，独立最终测试正在汇总。提交、推送、PR 由根负责。
- 本轮作者没有验证码授权，也没有登录真实三角色入口；专用离线和组件预览结果不能替代完整管理员登录与菜单流程验收。
- `DepartDetailList.clearSelectedDepartKeys` 仍直接清子组件 currentDeptId（而非调用 clearList）；本轮现有 guard 会拒绝空上下文写入，重开也递增版本。未扩大本任务修改父入口，这个既有清空接口写法作为后续观察点。
- 普通共享 modal 的 `add()` 原入口没有本表单可编辑的班级/课程字段；本次保留既有结构，不改新增关系业务表单。
