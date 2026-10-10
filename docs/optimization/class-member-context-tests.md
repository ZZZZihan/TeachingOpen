# 班级成员维护上下文独立专项测试

2026-10-03；测试 Agent `/root/course_resume_impl`，用户指定 GPT6.1-sol / ultra。

独立方法测试已完成：候选专项 **64/64**，同判据旧版 **13/64**（51 FAIL），相邻 **176/176**，完整前端 **561/561**，均无 skip/cancel。候选三组测试退出码 0，旧版专项退出码 1。测试只修改独立测试文件与本目录证据，未修改产品、后端、服务、数据库或浏览器，未安装依赖，未提交或推送。

## 冻结判据与旧版复现

- 工作树：`/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/class-member-context`。
- 旧版完整 ref：`8f58b32362899047da0136e41278368fd26c88f0`（PR60）。
- 测试文件：`web/tests/class-member-context.test.cjs`。
- 冻结测试 SHA-256：`8d0131e0bbdd24690efdfa926013e5083d6e1ea6c9a3ca473e38222471161756`。
- 同一组冻结业务判据 64 条，旧版 **13 PASS / 51 FAIL / 0 SKIP / 0 CANCEL**。
- 原始记录：`old-frozen-64.tap`。早期 `old-core-49.tap` 的文件名误写 49，实际为 39 条（5 PASS / 34 FAIL）；原文保留，没有重写为绿日志。

测试执行真实 DeptUserInfo、SelectUserModal、UserModal、DeptRoleUserModal 的 SFC script 与真实 JeecgListMixin 方法；API、Antd 表单验证、确认回调、nextTick、计时器、上传 transport 受控。行删除根据真实模板执行原 popconfirm closure 或候选 confirmDelete(record)，导入读取真实 beforeUpload/customRequest/action 绑定。普通 selector 的 visible watcher 显式调用，等效方法证据不声称 Vue 异步 watcher 或真实 Antd 渲染已验证。

冻结覆盖：

1. A 选择切 B；A 批取消/清空/行取消确认后切 B、clear 或同班重开；旧确认取消回调不能释放新提示；非法迟到用户 ID；选项变动；重复确认/点击。
2. A/B 列表与同班查询反序；旧成功/失败不污染新列表、数量、busy 或反馈；当前失败可重试；畸形 null 行不进入表格；clear/destroy 后迟到响应失效。
3. 已发送 A 批取消、清空和行取消的成功/失败回调不得刷新或清选择 B。**已经发送的服务器写不要求撤销**。
4. Selector 重开 B 清 A；A 原 emit 不能添加到 B；反序读；不存在当前列表的用户 ID；重复 emit/OK；失败阻止旧选择且重试恢复；普通 add() 与直接 visible=true 入口仍发数组。
5. UserModal 新增/编辑旧 validation、辅助读取、nextTick 和 pending save 与当前弹窗隔离；正常 B 新增/编辑；重复验证/写；普通 edit(record) 保持零参数 ok。普通新增的角色下拉选择由测试模拟真实用户 v-model 操作，不把既有异步默认角色问题纳入本轮。
6. DeptRoleUserModal 两读未完成/失败不能保存，可重试；旧读与旧保存不关闭或覆盖 B；普通 add(record,departId) 兼容；配置 A 时 assigned 返回 A+B、options 仅 A，提交 oldRoleId/newRoleId 仅含 A，避免请求删除不可配置的 B 角色。
7. 导入尚未发送即切班时拒绝旧 transport；已发送旧上传回调不污染 B；B 正常 action 仍含原 departIds；失败恢复及旧 uid 回调不能解锁新上传。

旧版通过的 13 条包含正常 B 批取消、清空、行取消、添加已有用户、新增与编辑、正常导入，以及共享 selector / UserModal / DeptRoleUserModal 的普通入口对照；因此冻结判据并非以禁用正常功能换取通过。

## 最终候选四组件快照与验证

测试前后下列 hash 完全一致，工作树 HEAD 在本测试范围内仍为旧 ref，产品改动尚未由测试 Agent 提交。根任务后续真实 UI 若产生产品修正，需要用新 hash 重跑关联断言。

| 文件 | 候选 SHA-256 | 旧 ref SHA-256 |
| --- | --- | --- |
| `DeptUserInfo.vue` | `f69c235df231ba801224d26a7bb168d4df29699e11687d3de3db3c68cf2a42b1` | `dc02e0c1b6b5317e6485dc7b5365d9b86a4a469f99e7ffa64707972334c38f65` |
| `SelectUserModal.vue` | `0b5f4636eb8164173aa3778da2e9479d08a23d918dfc3bb9bc0b39810e2a8562` | `e7d8e22239e72bb15008eb77260f4ff436d1c65ffacfebb93b63e93f2f078491` |
| `UserModal.vue` | `fd2779130889aad87a617babdcd68b698095fca4c0c56cdc4b9ee58bf31362f5` | `0e32f625da56d1ed65e7f5e6ef928f1b1a024f7a628c4b947606784fa5ff96d3` |
| `DeptRoleUserModal.vue` | `5d7da557941c6dda75278bb2ab0fd6b57497c46a72bc7369fc593d88443058c9` | `16610793b07af94710346aa4f693862db80e8d6df7c0fb406c849bd0827fe1b7` |

真实继承 `JeecgListMixin.js` 未改，SHA-256：`a0ed6a57f8534efae911766c115d3b4cc8f7c22fdd183b317561cbe74aa001ce`。

| 检查 | PASS / 总数 | FAIL | 退出码 | 原始 TAP |
| --- | --- | --- | --- | --- |
| 旧 ref 同专项 | 13 / 64 | 51 | 1 | `old-frozen-64.tap` |
| 候选四 SFC 专项 | 64 / 64 | 0 | 0 | `candidate-four-sfc-round1.tap` |
| 相邻模块 | 176 / 176 | 0 | 0 | `adjacent-round1.tap` |
| 完整前端 | 561 / 561 | 0 | 0 | `full-round1.tap` |

相邻模块为 login-session、header-menu、admin-course-workbench、teacher-workbench、class-course-context、course-form-recovery，完整前端使用 `tests/*.test.cjs`。`git diff --check` 无输出、退出码 0；新测试对 `/dev/null` 的 no-index check 无空白错误输出（退出码 1 表示存在新增文件差异）。

原始 TAP 保持不动；`published/` 下保存去除行尾空格的同名发布副本，可用于提交证据，不会把旧失败改成通过：

| TAP | 原始 SHA-256 | 发布副本 SHA-256 |
| --- | --- | --- |
| `old-frozen-64.tap` | `7611dfe1df5185ad5e2413ef34169069d12b99579a0babb0e37e4a07c952672a` | `5750fd4da953eef1270378792e7c0ec34413f6fa9cb7cd76750f8f51d865d3e7` |
| `candidate-four-sfc-round1.tap` | `7edee41b5f0787cae81db37b5f559ec8441ed8bc2f2c5d5389b79c6b81873df5` | 同原始 |
| `adjacent-round1.tap` | `9d27eb52983fef5bb3a7096ee99c911466c1d6d24089aed05e9d71f6f71a1bc5` | 同原始 |
| `full-round1.tap` | `ef4d2ff9d99d4f7539f9beec787915ad321a694c585955517f6af32db7ea2aa9` | 同原始 |

## 中途失败记录

`candidate-partial-64-round2.tap`：58 PASS / 6 FAIL。六条失败都来自当时尚旧的 UserModal：新增/编辑迟到验证、迟到 role/depart 读、clear 后 nextTick、迟到写完成和重复验证/写。DeptUserInfo、Selector、Role 与 import 判据已通过。第一轮含尚未匹配的新/旧 modal 接口，以及测试夹具缺 `$delete` 的失败，保留 `candidate-partial-round1.tap`，不将其描述为最终产品结果。

## 重跑命令

在工作树 `web` 目录执行，复用已有依赖，不安装：

```sh
NODE_PATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/web/node_modules SOURCE_REF=8f58b323 node --test --test-reporter=tap tests/class-member-context.test.cjs
NODE_PATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/web/node_modules node --test --test-reporter=tap tests/class-member-context.test.cjs
NODE_PATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/web/node_modules node --test --test-reporter=tap tests/login-session.test.cjs tests/header-menu.test.cjs tests/admin-course-workbench.test.cjs tests/teacher-workbench.test.cjs tests/class-course-context.test.cjs tests/course-form-recovery.test.cjs
NODE_PATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/web/node_modules node --test --test-reporter=tap tests/*.test.cjs
```

## 证据边界与交接

本专项已无未处理方法层失败，测试文件与判据可冻结。根 Agent 负责真实 Vue/Antd/浏览器和构建集成，另一个 Agent 负责真实 HTTP/数据库夹具；本报告只覆盖离线方法与受控异步证据，不替代实际 UI、服务器持久化、人工验收或生产交付。真实 Antd 的复选框缓存、可见表单字段注册、JS watcher 调度，以及跨窄屏页面布局等由实际 UI 证据分别判断，不能由本方法 VM 的通过结果推广。

根 Agent 最终交接反馈：实际 Vue/Antd 已检查普通编辑提交、旧 selector 数组事件、A 编辑中切 B 关闭、部门角色正常保存，console error/warn=[]，未发现本任务新产品异常。本 Agent 未操作浏览器，这段属于根任务的独立实际 UI 反馈，以根浏览器原始证据为准。390px 页面仍有旧版已有的 21px 溢出，768/1440px 无；本修复不声称全页面响应式通过，既有窄屏问题保留为独立待办。
