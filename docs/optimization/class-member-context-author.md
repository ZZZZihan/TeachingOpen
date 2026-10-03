# 班级成员维护上下文隔离实现记录

2026-10-03；实现 Agent `/root/class_context_impl`，用户指定 GPT-6.1-sol / ultra。

产品改动已经完成并冻结。工作树为 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/class-member-context`，分支 `fix/class-member-context`，基线 PR60 `8f58b32362899047da0136e41278368fd26c88f0`。本 Agent 仅修改四个产品 SFC 与本目录作者证据；没有修改测试、全局 mixin、后端，没有操作浏览器、服务、数据库或凭据，没有安装依赖，没有提交或推送。

## 已确认的旧行为

实施前用基线实际 DeptUserInfo、SelectUserModal 的 SFC script 与实际继承 JeecgListMixin 方法录制，API 和 Promise 为受控替身。原始结果保留于 `author-old-behavior.json`，这属于实际方法证据，不代表浏览器或数据库验证：

- A 打开清空确认后切换 B，再确认，旧代码 GET `/sys/sysDepart/removeAll` 的 `id` 实际为 `class-b`。
- A 选择 `user-a` 并打开批取消确认后切换 B，再确认，旧代码 DELETE `/sys/user/deleteUserInDepartBatch` 实际组合 `depId=class-b` 与 `userIds=user-a,`。
- A 选择器返回裸用户 ID 数组，父组件已切 B 时会 POST `/sys/user/editSysDepartWithUser`，把 A 选择的用户加入 B。
- B 列表先完成、A 列表后完成时，当前班级为 B，但可见列表被 A 记录覆盖。

根 Agent 随后在真实 Vue/Antd 预览中独立复现 A 清空确认切 B 后清空 B，保留 `preview-baseline-cleared-b.txt/.jpg`。独立方法测试也用相同冻结判据记录旧版 13/64，通过项包括正常 B 添加、移除、清空及共享普通入口，详见 [独立测试报告](class-member-context-tests.md)。

## 改动与原业务契约

`DeptUserInfo.vue` 为每次 open、clear 和同班重开生成新上下文版本，立即重置用户选择、旧列表、查询、页码和数量，并关闭所属选择器、用户编辑与部门角色窗口。列表响应同时校验班级、上下文版本和请求顺序；当前失败或畸形记录给出可重试反馈，旧响应不能替换新列表或解除新请求的 busy。每次搜索、分页或刷新同样清空选择，避免保留已不在当前结果中的用户。

批取消、行取消和清空确认保存原班级、上下文及用户快照。批取消另存选择版本，行取消保留当前真实记录身份；确认创建和取消使用对象身份锁，防止重复提示及旧取消回调解锁新确认。未发送的旧操作在切班、clear、重开或选择改变后拒绝。通过确认发送的写请求始终使用原目标；它在服务器上可以正常完成，前端只抑制迟到 UI 回调，不声称已撤销服务器写。

正常 API 继续使用原接口：加入 POST `{depId,userIdList}`；行取消 DELETE `{depId,userId}`；批取消 DELETE `{depId,userIds}`，保留末尾逗号；清空 GET `{id}`。写入只在服务响应 `success === true` 时显示成功；拒绝和无法确认的网络结果保留可读错误并可刷新核对、重试。清空文案按实际接口说明为清空所有班级成员、保留用户账号。

`SelectUserModal.vue` 新增 `show(context?)`。每次展示清空选项和分页，关闭或重开使旧列表、角色读取和确认失效。班级入口事件为 `{deptId,contextVersion,userIdList}`，父组件先验证上下文，再使用事件中的原班级；共享普通入口 `add()` 和直接 `visible=true` 仍返回原裸 ID 数组。RoleUserList、TeachingWorkList 调用方保持兼容，未修改调用方或全站 mixin。

`UserModal.vue` 的 `add(context?)` / `edit(record,context?)` 仅添加可选上下文。角色、部门读取，nextTick 回填，异步重复检查，validation 和保存均绑定弹窗会话；关闭、切班、重开使旧回调失效。读取未完成或失败不能保存，失败可重试，重复提交在异步 validation 前锁住。新建班级成员固定为原班级；编辑保留实际用户的全部部门关联，避免因为班级入口只显示一个部门而移除其他关联。角色固定的普通新增入口保留调用方种子选择；普通入口仍发无参数 `ok`。表单只回填实际注册的字段，身份 id 由原 model/userId 保持。嵌套部门窗口按会话重新创建，旧窗口不能回填新会话。没有扩大到用户权限或后端管理重写。

`DeptRoleUserModal.vue` 的 `add(record,departId,context?)` / `edit(record,context?)` 保留普通入口。两次读取一起完成后才可保存，读取、保存和取消确认均绑定窗口会话。实际 assigned 接口返回用户所有部门角色，而 options 接口仅返回当前可配置范围，因此 oldRoleId 与 newRoleId 都按实际 options 过滤，防止在 A 配置时删除不可见的 B 角色。保存前复制原用户及差异集合，迟到响应不能刷新或关闭新窗口。当前失败保留反馈并可重新读取核对。

导入使用 `beforeUpload` 保存 upload uid 的原上下文和原 action，再在 `customRequest` 的真正发送点校验。沿用项目已安装 Antd 的默认 XHR transport，保持 multipart、header、进度与 abort 契约；尚未发送就切班的文件不会发旧请求。已经发送的导入继续原目标，回调只清理自己的 uid，不覆盖新班列表、反馈或新导入锁。业务失败或缺少成功响应不会假报成功，部分成功保留可读明细提示和安全的结果链接，刷新列表时明细提示保留。

四组件的 loading 遮罩与入口 guard 负责锁读写期间操作，没有使用会被 Antd 1.x 按行缓存的动态 getCheckboxProps，避免列表加载后复选框停留 disabled。

## 最终冻结

2026-10-03 最终重新计算并确认与独立测试前后快照一致。除出现新的失败证据并先通知根及测试 Agent 外，产品不再修改。

| 文件 | 最终 SHA-256 |
| --- | --- |
| `web/src/views/system/modules/DeptUserInfo.vue` | `f69c235df231ba801224d26a7bb168d4df29699e11687d3de3db3c68cf2a42b1` |
| `web/src/views/system/modules/SelectUserModal.vue` | `0b5f4636eb8164173aa3778da2e9479d08a23d918dfc3bb9bc0b39810e2a8562` |
| `web/src/views/system/modules/UserModal.vue` | `fd2779130889aad87a617babdcd68b698095fca4c0c56cdc4b9ee58bf31362f5` |
| `web/src/views/system/modules/DeptRoleUserModal.vue` | `5d7da557941c6dda75278bb2ab0fd6b57497c46a72bc7369fc593d88443058c9` |

## 验证归属与边界

作者自检：四 SFC 的 Vue template 编译与 Babel script 解析均无 errors/tips；最终 `git diff --check` 无输出、退出码 0。使用已有 node_modules，未安装或更新依赖。这只覆盖语法与空白检查。

独立测试 Agent `/root/course_resume_impl`：冻结专项候选 **64/64**、相邻 **176/176**、完整前端 **561/561**，均退出码 0；相同判据旧版 **13/64**（51 FAIL）。测试使用实际 SFC 与 mixin 方法，受控 API、表单 validation、确认、nextTick 和上传 transport；不声称实际 Vue/Antd 渲染已经由方法 VM 验证。原始 TAP 与四文件前后 hash 记录见 [独立测试报告](class-member-context-tests.md)。

根 Agent 实际 Vue/Antd 预览反馈：A 清空确认切 B 后旧 OK 无请求且 B 行保留；B 正常添加及批取消正常；普通用户编辑和旧选择器数组事件正常；A 编辑中切 B 关闭旧窗口；部门角色正常保存；console error/warn=[]。此处为根的独立操作反馈，本 Agent 没有操作浏览器，原始 `preview-*.txt/.jpg` 由根维护。

实际 HTTP/DB Agent `/root/python_frame_tests`：核心冻结候选 **22/22**，旧版 **12/22**，实际 SFC/mixin 方法连接独占合成 runtime 的真实 HTTP 并立即查 DB。正常 B 添加、单取消、批取消与清空实际持久化；业务拒绝保持关联并无假成功。报告 `live-after.json` 的源 hash 与两核心冻结值一致，69 张 schema、68 张非审计数据集合及全部附件已恢复。此处为独立 Agent 的实际服务证据，本 Agent 没有操作服务或 DB。

部门角色实际 HTTP/DB 最终候选 **9/9**，同冻结判据旧版 **7/9**，报告 `live-role-after-final.json` 与 `live-role-before-final.json` 使用相同 probe/wrapper hash。旧版两条失败均为 A 取消或添加角色实际删除 B 角色；候选请求 old/new 差异只含 A，A 取消后 B=1 条，A 新增后 Anew=1、B=1。候选源 hash 为上述冻结 Role 值，69 张 schema、68 张非审计数据集合及附件均已恢复。候选首轮 `live-role-after.json` 的 8/9 被保留，单红来自工具在候选已保留 B 时仍按旧版行为再插 B，产生两条 B；工具仅改为缺少 B 才重建，随后旧/新同一新冻结判据各跑一次，产品没有为该夹具问题改动。

集成构建、提交、推送、PR 和最终交付由根 Agent 完成；上述不等于生产部署或人工验收。既有 390px 页面横向溢出由根保留旧/新尺寸证据，本次不承诺整体响应式修复。HTTP Agent 独立记录学生直接请求 removeAll 在冻结后端可清空其合成班级，该后端权限问题超出本次前端上下文范围，未修改或计入前端通过断言。
