# 班级课程上下文独立测试（2026-10-03）

最终冻结候选的专项 **61/61 PASS**；同一份测试、同一断言读取旧 ref `253f3fb4c44b500b6e4824adbf89da51ac89d50c` 时 **7/61 PASS、54 FAIL**。最终完整前端 **497/497 PASS**，退出码 0。相邻五组单独执行 **114/114 PASS**，随后也被最终完整前端覆盖。

测试 Agent 仅新增 `web/tests/class-course-context.test.cjs`，未修改产品。工作树 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/class-course-context`。产品由 `/root/class_context_impl` 实现；根 Agent 负责审查、真实 Vue/Antd 预览及后续整合。未提交、推送、访问浏览器、服务、数据库、凭据或生产；未安装依赖、启停服务或修改环境配置。

## 实际执行对象与控制范围

测试读取实际 `DeptCourseInfo.vue`、实际继承的 `JeecgListMixin.js`、实际 `SelectCourseModal.vue` 与 `TeachingCourseDeptModal.vue` 的脚本，在 VM 中执行数据、方法、computed 与生命周期钩子。真实 `filterObj` 也从项目源码提取；继承 mixin 的 JSX 通过既有 Babel 转换，未重写业务方法。

网络 Promise、Antd 表单 validation、Vue nextTick、确认回调和消息为受控替身。父子实例使用实际 `$refs` 方法与选择/保存事件连接。行内删除从实际模板识别入口：候选调用 `confirmDelete(record)`，旧版捕获原 `a-popconfirm` 的 `handleDelete(record.id)` 回调；传入的 record 是实际 `dataSource` 中的对象，保持真实表格行引用语义。

旧产品遗弃的 Promise 错误链由测试替身附加拒绝观察，避免某个旧版未处理错误跨测试污染 Node 进程。产品的 `then/catch/finally` 与状态恢复仍照常执行；失败断言要求可见错误及恢复能力，不能因替身观察而假报业务恢复。

## 最终 61 条覆盖

- 班 A 勾选关系 → 切班 B 时同步清空 keys、rows、旧列表和页数；B 返回前不可用 A 的选择删除。
- A 的批量/行内确认分别经历切 B、清空、重开 A 后，旧回调不能发 DELETE；变化的选择使旧批量确认失效。旧取消/确认也不能解除新确认的锁。
- 列表跨班反序、同班反序、网络/业务错误反序、清空/销毁后的迟到读，不能把 A 的数据、错误、总数或加载状态写进 B。
- `[null]` 畸形关系或课程行不进入表格；加载进入可重试错误状态。
- 选择课程弹窗 show B 时清 A 的选中项、候选行、旧搜索和分页；旧 A 结果、关闭后的结果和旧 A 选择事件不能向 B 添加课程。事件必须保留原班级及课程 ID 快照。
- 正常 B 批量删除、行内删除、添加课程与设置开课时间保持现有端点、参数和 B 身份；重复确认、validation 和写入不重复 dispatch。
- 已发出的 A 删除/添加返回成功或失败时，B 的列表、选中项、提示和当前写锁保持正确。已经发出的写操作可能在服务器完成；测试仅要求后续 UI 不被迟到回调污染，不要求回滚实际效果。
- 开课时间弹窗的旧 nextTick、validation 和 HTTP 返回，不能修改、提交、关闭或解锁新 B 弹窗；错误保留值供手动重试，销毁后忽略回调。
- 普通 `edit(record)` 无上下文入口仍发无参数 `ok`；普通无 ID 的新记录 `edit(record)` 保持 POST 创建协议。
- 普通和父面板上下文入口均验证：validation values 带其他关系 ID、deptId、courseId 时，提交仍保留打开时 model 快照身份，只合入 openTime。实际 edit 与 popup callback 仅回填已注册的 openTime 字段。

四条 B 单次写入控制和普通表单入口/validation 控制在旧 ref 也通过。旧版失败主要是跨班选择/确认错误请求、迟到读取覆盖、过时选择事件误绑定、重复 dispatch 和共享弹窗会话隔离问题。

## 保留的失败与测试修正

候选首轮 **43/44**，发现批量确认可重复打开。扩大首轮 **48/53**，发现批量和行内确认堆叠、旧取消不能保持新提示锁，以及两个列表可接受 null 行。实现者修复后第二轮 **59/59**。

根 Agent 在真实 Vue/Antd 预览另发现两项方法测试未覆盖的问题：表格 getCheckboxProps 缓存 loading=true 时的 disabled 值，以及不存在的隐藏 deptId/courseId 字段引发回填 Warning。根 Agent 回报已修复并复验；这些浏览器事实由根 Agent 自己的运行记录支持，不属于本 VM 方法测试的独立浏览器证据。

第三轮增加身份保护与已注册字段检查，并修正测试范围：旧 `add()` 空记录夹具曾把未注册的 deptId/courseId 当作表单 values，现改为有班级/课程身份、无 ID 的普通新记录 `edit(record)`。另移除只比较 `$confirm` 数量的行内弹窗堆叠断言，因为旧版用原生 a-popconfirm，该数量在方法替身中不可比；行内旧确认跨班与重复 DELETE 断言保留。最终分母因此为 **61**，此前 44/53/55/59 的日志均保留，不将旧数量追记为新分母的通过。

## 冻结证据

最终测试前后分别计算三份产品和测试 SHA-256，完全相等，匹配实现者冻结清单。测试文件 `node --check`、工作树 `git diff --check` 均退出 0。

| 文件 | SHA-256 |
| --- | --- |
| `web/tests/class-course-context.test.cjs` | `66baa7f0262cc3b34e7c3f210ab09e3d02a5f1fda71e135ed6e664f52718498b` |
| `web/src/views/system/modules/DeptCourseInfo.vue` | `818140750a44fd642d58e62a481a38fec147af5dce3a713c6f2913cf227ef42a` |
| `web/src/views/teaching/modules/SelectCourseModal.vue` | `367bdc581930e997f42a372a923ad543bb9389feeca97f0330da9db652e90f41` |
| `web/src/views/teaching/modules/TeachingCourseDeptModal.vue` | `a2f0808da084747ee810a7f3d07c32c0d0847745fb7328cc9829577ad0a849b8` |

最终同断言与回归 TAP：

| 记录 | 结果 | 退出码 |
| --- | --- | --- |
| `baseline-final-61.tap` | 旧 ref 7/61，54 FAIL | 1 |
| `candidate-final-61.tap` | 最终候选 61/61 | 0 |
| `adjacent-final.tap` | 相邻五组 114/114 | 0 |
| `frontend-final-497.tap` | 最终完整前端 497/497，包含专项及相邻组 | 0 |

其他历史 TAP：`candidate-first.tap`（43/44）、`candidate-expanded-first.tap`（48/53）、`baseline-final.tap`（阶段性旧版 3/55）、`candidate-round2.tap`（59/59）、`baseline-frozen.tap`（阶段性旧版 7/59）、`frontend-first.tap`（阶段性完整 495/495）、`candidate-round3.tap`（61/61）。文件名的历史 final/frozen 不代表最终 61 条版本；以本表及 `*-61.tap` 为最终专项证据。

四份最终/相邻原始 TAP 均保持原字节。供纳入 PR 的 `published/` 副本只移除每行末尾的空格和 tab，不改变断言内容、结果或行序；`published-manifest.json` 记录原始与发布副本各自 SHA-256。不要把发布副本称为未经处理的原始日志。

复跑时在 worktree 的 `web` 目录执行；NODE_PATH 仅指向已有 `product-candidate/web/node_modules`，没有下载安装或更改全局配置：

```sh
NODE_PATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/web/node_modules node --test --test-reporter=tap tests/class-course-context.test.cjs
SOURCE_REF=253f3fb4c44b500b6e4824adbf89da51ac89d50c NODE_PATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/web/node_modules node --test --test-reporter=tap tests/class-course-context.test.cjs
NODE_PATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/web/node_modules node --test --test-reporter=tap tests/login-session.test.cjs tests/permission-menu.test.cjs tests/admin-course-workbench.test.cjs tests/teacher-workbench.test.cjs tests/course-form-recovery.test.cjs
NODE_PATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/web/node_modules node --test --test-reporter=tap tests/*.test.cjs
```

这些测试证明控制到真实组件方法的请求与状态隔离。它们不证明真实数据库删除/新增效果、实际角色权限或浏览器控件缓存行为，也不代替学生/教师/管理员人工验收。真实 Vue/Antd、服务或数据库运行由根 Agent 另行记录；本测试 Agent 未执行这些操作。
