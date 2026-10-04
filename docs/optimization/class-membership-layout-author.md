# 班级成员工作区布局：作者记录

记录时间：2026-10-05（Asia/Shanghai）。作者为 `/root/membership_author`；本记录仅描述作者实施与静态自检，实际浏览器、构建、方法回归及 PR 交付由根任务和独立审阅 Agent 负责。

## 范围与基线

- 工作树：`/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/class-membership-layout`。
- 分支：`fix/class-membership-layout`。
- 基线：PR61，提交 `df4e707234c04d1c8932335e4f779e58be25835e`。
- 产品修改仅涉及 `web/src/views/system/modules/DeptUserInfo.vue` 和 `SelectUserModal.vue` 的模板、样式、表格列宽；业务方法、上下文隔离、API 参数与 URL 保持原样。
- 作者没有修改测试工具、启动服务、操作浏览器或数据库，也没有提交、推送或操作 PR。工作树中的测试变动与预览工具属于根任务及独立审阅 Agent；不归入作者产品补丁。
- PR62 的后端权限与事务文件保持不动。

## 问题与实施决定

根任务提供的实际旧版证据说明：390px 独立页面的 document/body 宽度达到 411/412px；成员表内容宽度大于卡片体可用宽度，搜索区也有溢出。真实 `DepartList` 的右侧 md14 栏嵌套卡片和 tabs 后，可用宽度更窄，旧表被父 tabs 裁切。选择器在 768px 窗口仍达到 1000px，关闭/确认及分页是否可达不能仅由 document 宽度判断。相应证据由根任务保存在本 artifact 目录的 `baseline-390*`、`baseline-parent-sizes.json` 与 `baseline-selector-sizes.json`。

实施采用现有 Ant Design Vue 组件和项目天工紫色调，解决实际布局约束：

1. 成员卡片去掉负左右 margin 和负按钮间距，使用完整的 `min-width: 0` / `max-width: 100%` 容器链。搜索表单采用基于容器宽度的 CSS grid，标签与输入垂直排列；查询按钮、工具按钮组及状态行允许换行，所以窄父栏与窄窗口使用同一规则。
2. 保留所有成员列和行操作，明确设置表格横向滚动宽度 920px 与可读列宽。长内容可在单元格内换行，表头保持正常横排；表格仅在自己的 Ant 表体内横向滚动，分页位于表体之外并允许换行。未使用页面或 body 的 overflow:hidden 掩盖溢出。
3. 两处表格各有命名的可聚焦 region、可见滚动提示和焦点轮廓。左右方向键只在 region 自身聚焦时滚动表体（Vue `.self.prevent` 修饰符）；子输入框、下拉菜单与分页输入框的键盘事件不被该处理器接管。原行操作改用可聚焦的 link button 和 click dropdown，原业务方法调用保持一致。
4. 选择器宽度使用 `calc(100vw - 32px)`，通过专属 modal wrap class 在所有窗口宽度设置 1000px 上限。弹层 body 限高并可纵向滚动，标题、关闭按钮及确认/关闭 footer 处于 body 外；footer 与分页允许换行。Ant modal 通过 portal 渲染，因此弹层样式采用受 `member-selector-dialog` 名称约束的非 scoped CSS。
5. 页面显示真实班级名称和真实选择数，不添加装饰统计。共享选择器在没有班级上下文时使用通用选人说明，避免影响其他已有调用方的语义。

成员列宽为：选择 64、账号 150、姓名 140、部门 180、性别 76、电话 150、操作 160，总计 920px。选择器列宽为：选择 64、序号 56、账号 150、姓名 140、电话 150、角色 180、部门 180，总计 920px。

## 保持的契约

所有现有 `@ok`、`@cancel`、`@change`、`@selectFinished`、refs、导入 headers/action/beforeUpload/customRequest/change、禁用条件、错误提示重试调用和角色重试调用均保留。列表请求、写入请求、班级上下文版本、选择器 session 及导入隔离逻辑没有改动。脚本中从 `methods: {` 开始到 script 结尾的字节与基线逐文件相同；脚本差异仅为上述表格列宽。

## 作者自检与证据边界

- `git diff --check`：通过。
- Vue 2.7.16 template compiler：两文件均 `errors=[]`、`tips=[]`。
- Babel parser：两文件 script 均解析通过。
- 两文件业务 methods 的字节对照：与基线相同。
- 检查使用共享的现有 node_modules；没有安装依赖。记录到的工具版本为 Node v26.7.0、Vue 2.7.16、Ant Design Vue 1.7.8、vue-template-compiler 2.7.16。

这些结果证明本候选语法有效并且业务 methods 保持原样，不证明真实浏览器尺寸、遮挡、滚动、键盘交互或生产行为。作者没有运行构建和方法测试。浏览器与方法回归的执行归属和结果分别记录如下。

## 交接后的验证回报

根任务明确回报：实际浏览器已通过 390/768/1440 三宽度的独立组件与真实 `DepartList` 父级场景、768px 弹层、390×650px 短屏 footer、长文本与 25 行分页、键盘到编辑/更多、正常添加用户/查询/失败重试，未发现两 SFC 的待修问题。作者只读核对了本目录 `candidate-sizes.json`、`candidate-parent-sizes.json` 与 `candidate-behavior.json`：三宽度 document/body 与窗口一致；窄父级成员卡片及搜索区不再由内容撑宽，表体仍保留约 920px 内容的自身横向滚动；768px 弹层 left/right 为 16/752，关闭按钮、分页和 footer 按钮处于窗口内。短屏与键盘证据分别由根保存在 `candidate-selector-short-keyboard.json`、`candidate-member-keyboard.json` 及对应截图。

独立 Agent `/root/course_resume_impl` 回报：除列宽之外，两份业务 script 的 AST 完全等同 PR61，候选通过现有 64/64 条专项断言；同一断言针对旧基线为 13/64。初次候选 57/64 中 7 个失败来自测试的 rowPrompt 字面正则未识别模板事件新增的 `.prevent` 修饰符，根授权修改这一行测试后通过；原始日志保留在 `member-context-first.tap`，最终与旧版对照分别为 `member-context-final.tap` 与 `member-context-old-same-criteria.tap`。该测试变动不是作者产品修改，也不构成 CSS/浏览器行为证明。

上述浏览器预览使用真实组件及父级形状、内存 API 与外围面板替代，属于本地实际浏览器验证；不代表全站真实登录环境、人工验收或生产交付。根任务继续负责集成、构建记录与 PR。

## 冻结源码与指纹

冻结快照目录：`/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/class-membership-layout/author-candidate-20261004T161858Z`。捕获时间为 `2026-10-04T16:18:58.977Z`。目录内保存两份只读产品 SFC、`product.diff`、`product-hashes.json` 与 `syntax-check.json`；`author-current-candidate-path.txt` 指向该候选。

| 产品文件 | SHA-256 |
| --- | --- |
| `web/src/views/system/modules/DeptUserInfo.vue` | `edb9adba2a7e74ec900ef403356ab85173ba900242781fba0ef482e20221cfdc` |
| `web/src/views/system/modules/SelectUserModal.vue` | `b1b39ce5557dc43f8ab619bb4c2202cdd73f4abd537510e5fe6c587d1ad7c8f1` |

根任务已完成本轮浏览器核验并确认无需产品修正，作者产品源码继续保持上述冻结指纹。不追加范围外设计或业务修改。
