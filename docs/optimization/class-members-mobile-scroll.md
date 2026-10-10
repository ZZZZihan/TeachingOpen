# 班级成员手机键盘滚动

完整后台在 390px 手机宽度下，成员区域只有约 310px。`GlobalLayout.vue` 的 `.layout.mobile .ant-table-wrapper .ant-table-body` 给内层滚动容器设置了 `min-width: 800px`。原成员局部 CSS 约束了外层容器，却遗漏这个 body：921px 内容在 800px body 内只能滚约 121px，外层 310px 容器仍裁掉后半段，连续按右键无法到达操作列。

本次仅在 `DeptUserInfo.vue` scoped CSS 中给成员 body 设置 `min-width: 0; max-width: 100%`。编译后选择器优先级为 `(0,5,0)`，高于全局手机规则 `(0,4,0)`，不依赖 CSS 加载顺序。其他表格保留原全局规则。模板、键盘处理器及业务脚本与 #63 的 `a1dd2c3bef24fdd69a5aa5563550b1707df1bb4f` 完全相同。

#63 的实际组件预览已验证其独立页面的键盘滚动，但预览构建没有包含 `GlobalLayout.vue`，当时 table body 已自然收缩到容器宽度；因此没有覆盖完整后台手机规则与局部组件的组合。本次回归直接编译真实 GlobalLayout LESS 和实际 Vue scoped CSS，验证两种 CSS 顺序、其他表格、桌面宽度，以及 Vue 编译的真实区域左右键和 `.self/.prevent` 处理。310px 容器 / 921px 内容采用现场尺寸构建有界几何模型，确认键盘可达真实列配置中的完整操作列；这不是浏览器布局引擎验收。

验证结果：

- 相同新断言运行于 #63：4/7 通过，两个手机级联断言及操作列可达断言失败。
- 修复后专项：7/7；与既有 `class-member-context.test.cjs` 合并：71/71。
- `npm run build` 退出 0，仍有 12 条 CSS 顺序／资源体积警告和旧 Browserslist 数据提示。
- 显式 `eslint --no-ignore src/views/system/modules/DeptUserInfo.vue` 退出 1：54 个错误、289 个警告；与 #63 逐条相同。本 CSS 修复没有新增 lint 诊断。
- `git diff --check` 退出 0；未安装依赖，未修改后端、数据库或运行服务。

根 Agent 已在完整后台壳中完成真实浏览器复验，绑定组合候选 `1b23551257b3f922f7fc4b125dfd9a85e5090a0c`、最终构建和前端进程 PID `49600`：

| 视口 | body clientWidth / scrollWidth | 右键到末端的 scrollLeft | 外层 clientWidth / scrollWidth |
| --- | --- | --- | --- |
| 390px | 310 / 921 | 610.4545 | 310 / 310 |
| 768px | 377 / 921 | 543.6364 | 377 / 377 |
| 1440px | 769 / 921 | 151.3636 | 769 / 769 |

390px 视口连续按右键8次后，编辑按钮进入可见区域，根 Agent 实际打开学生编辑对话框，再取消并确认放弃，没有提交字段写入。三个视口的外层均不再承载第二段横向溢出。原始 DOM 测量和截图位于本地 `.devspace/artifacts/authenticated-role-flow-20261005/root-browser/admin-members-keyboard-{end-after,768-after,1440-after}.{json,png}`，编辑可达证据为 `admin-members-edit-accessible-after.png`。

根 Agent 最终组合候选全量测试 688/688，生产构建退出0／12条既有告警，证据位于同一 artifact 根目录的 `member-scroll-final-build/`。独立窄审阅的编译／级联／源码／几何探针12/12，无阻断问题，报告为 `member-scroll-review/review.md`；独立离线审查和根的真实浏览器验收分别记录，不混为同一种证据。

上述门槛已完成，PR 转为 Ready。此记录更新不修改产品或测试，不重建。本分支自身 dist 仍不包含组合候选其他 PR，不作为候选运行产物；没有远端合并或生产发布。
