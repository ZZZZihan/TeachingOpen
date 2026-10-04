# 班级成员响应式布局独立审阅

2026-10-05；只读产品审阅 Agent `/root/course_resume_impl`，用户指定 GPT-6.1-sol / ultra。

最终独立审阅结论：两份产品的改动限于模板、样式和列宽；除列宽外业务 script AST 与 PR61 相同，既有成员上下文专项 64/64 通过，未发现需要阻止本次布局修复的静态或方法回归。根 Agent 的实际 Vue/Antd 浏览器证据补足了局部滚动、父页面嵌套、三种宽度和短屏弹层的验证；这些证据仍是内存 API 预览，不代表生产或人工验收。

工作树 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/class-membership-layout`，分支 `fix/class-membership-layout`，基线完整 ref `df4e707234c04d1c8932335e4f779e58be25835e`（PR61）。本 Agent 只读产品、父页面、预览框架和本地图片/JSON，执行离线方法测试并写本报告。根明确授权后，仅修正既有测试的一行模板识别正则，使其接受 `.prevent` 修饰符，未增减断言或改产品。未操作数据库、服务或浏览器，未提交、推送或安装依赖。

## 基线实际问题与根因证据

已查看 `.devspace/artifacts/class-member-context/final-390.jpg` 及本任务 `baseline-390.jpg`。两者是实际 Vue/Antd + 内存 API 的独立组件预览，不是完整真实平台登录页面，也没有 DepartList 父页面嵌套。旧 390px 画面可见表头/名称挤成竖排，操作区和表格右缘紧靠或超出画布；截图本身不能唯一证明哪条 CSS 导致 21px 文档溢出。

根 Agent 实际浏览器采集的 `baseline-390-geometry.json` / `baseline-390-overflow.json` 已由本 Agent 只读核对：viewport 390，document scrollWidth 411，body 412。成员 card/client 386，内部内容宽 338，表体 client 338/scrollWidth 386，越界沿 table wrapper/spin/card 传给页面；查询 wrapper client 338/scrollWidth 343。日志 PRE client 326/scrollWidth 489，但有本地滚动，根 Agent 说明其不造成文档外溢。这是根的 DOM 观察，不是本 Agent 发起浏览器检查。

与 DOM 相符的静态因素：

- 基线 DeptUserInfo 根 `.ant-card` 左右 `margin:-30px`。块级自动宽度会因此扩大，属于抵消上层 padding 的旧写法。它能增加传给父容器的宽度，但仅凭源代码无法把测得的 21px 全部归给负边距。
- 成员表格没有 `scroll.x`，操作列固定 150px，其余列依赖表格最小内容宽度。窄容器下只能挤列或让表体撑宽；DOM 的 338/386 已确认存在未被局部滚动收住的表格外溢。
- 查询区使用 inline form 默认右 margin 16px，账号/姓名 md/sm=8，查询按钮的 a-col 嵌在浮动 span 中，并有额外左边距。它与 DOM 的 338/343 少量溢出相符；布局应按实际可用容器宽换行，不依赖隐藏越界内容。

## 选择器及真实父页面风险

`baseline-selector-sizes.json` 显示：390px 弹层宽 374，表体 client 324/scrollWidth 770；768px 弹层 left=0/right=1000，分页 right=976，而 document scrollWidth 仍是 768；1440px 弹层 left=220/right=1220。**只检查 document.scrollWidth 会漏掉 768px 弹层的越界与按钮不可达风险。** 最终需分别确认弹层、分页、确认/关闭按钮的几何范围及实际可操作性。

本地 Antd `modal/style/modal.less` 只在 `max-width:@screen-sm-max`（767px）为 modal 设 `max-width:calc(100vw - 16px)`，因此基线 `width=1000` 在 390 被收窄，在 768 未被收窄，与根的实际 DOM 一致。选择器固定列宽总计 710px，加复选框后实际表体约 770px；表格应允许自身横向滚动，而弹层和页脚留在视口内。查询 span 10+10+8 也需改成随容器换行。

实际 DepartList 为 `a-row gutter10`，左 md10、右 md14/sm24，右侧 `a-card -> a-tabs -> forceRender a-tab-pane -> DeptUserInfo a-card`，存在两层 card padding。768px 起右侧只有 14/24 的父宽，即使桌面 viewport 超过手机断点，成员容器仍很窄。已向根建议补一个保留实际父级 card/tabs/14列约束的场景；独立组件在三个 viewport 的通过不能自动推广为完整 DepartList 页面通过。父部门树、机构表单和全站导航布局不在本次两组件修复范围内。

根已按上述建议新增 `web/tests/class-membership-layout-preview`，本 Agent 只读审阅入口/构建：真实 DepartList 与四份成员 SFC，外围部门编辑、上传、课程/权限面板替代，API 内存化，形状保留。`baseline-parent-sizes.json` 实际 DOM：390px document/body 均390，但成员 card client338/scroll410、表体290/386，被 tabs 裁切；768px 表体371/386；1440px 表体564/564。这里再次表明页面无水平溢出不等于成员列或操作可达。

该预览初稿仅导入 Antd CSS，未加载真实 `src/assets/less/common.less`（全局按钮 margin 与表格单元格上下 padding）。本 Agent 提醒后，根已在最终旧、新预览统一使用 `antd.less`、与 `vue.config.js` 相同的主题 modifyVars 和 `common.less`。已只读核对预览源码和 `preview/{baseline-final,candidate-final}/source-manifest.json`：父 SFC、mixin、两份共享表单、common.less 和主题配置 hash 相同，只有目标两份 SFC 不同。最终父页面旧证据另存为 `baseline-final-parent-sizes.json`；初稿证据保留。预览同样不含全站真实导航与认证环境。

## 必须保留的行为与可达性

- DeptUserInfo 的查询/重置、添加已有用户、新建、导入、清空、批取消、编辑/更多/角色/详情/取消关联仍使用原事件、disabled 条件和 refs。不能通过隐藏操作列、减少展示字段或全页面 overflow:hidden 来消除溢出。
- 导入的 action、beforeImportUpload、handleImportRequest、handleImportExcel 和选中 ID 上下文保持；loading/mutation/import 的禁用行为保持。
- Selector 的 handleOk/handleCancel、空选择或加载失败禁用、load/role 错误重试、行复选与分页保持。scoped show(context) 发对象；普通 add() 或直接 visible=true 发数组，RoleUserList 与 TeachingWorkList 的既有调用方依赖这个数组契约。
- 表格横向滚动区域应可识别、可聚焦；若新增左右键委派，只在 region 本身聚焦时拦截，不能抢走分页输入框/下拉菜单等子控件的键盘操作。作者已收到此审阅建议。
- Modal 为 portal 渲染，普通祖先 scoped CSS 不能假定控制弹层外壳；使用专用 wrapClassName 的局部命名样式后需由根实际 DOM 确認匹配，且短屏下纵向滚动不能把页脚锁在不可达区域。

## 最终 diff 与业务不变性

独立核对最终 diff：DeptUserInfo 去除负边距，改用容器自适应搜索网格、换行工具栏和局部表格横滚；新增表格滚动提示及可聚焦 region。Selector 的固定 1000px 宽改成视口内宽度并设置最大 1000px，查询网格可换行，body 在短屏内纵向滚动，footer 和分页可换行。所有展示列保留；没有用全页面 `overflow:hidden` 掩盖外溢。两个表格保留 `onSelectChange`、选中 keys、pagination/change 和 loading；业务 disabled 条件、重试函数、refs 与导入四个钩子均保留。

左右键事件为 `.left.self.prevent` / `.right.self.prevent`，仅聚焦 region 本身时调整 `.ant-table-body.scrollLeft`；没有拦截子分页输入、菜单或筛选控件的方向键。操作菜单改为明确 click 触发，删除链接仍调用 `confirmDelete(record)` 并增加 `.prevent`。Selector portal 样式全部以专用 `.member-selector-dialog` 命名空间限定，未作用到其他弹层。共享选择器说明依据已有 `selectionContext.deptId` 区分班级入口和普通入口，不改变事件格式。

用实际 `@babel/parser` 解析基线和候选两个 SFC，剔除位置元数据，并且仅从 `columns` / `columns1` / `columns2` 中剔除 `width` 属性后，整个 script AST 相同。不是仅比较部分方法；包含方法、computed、watch、生命周期、URL、其他 data 状态及字段。结果保存 `review-ast.json`：

| 产品 | 最终源码 SHA256 | 基线及候选相同的业务 AST SHA256 |
| --- | --- | --- |
| DeptUserInfo.vue | `edb9adba2a7e74ec900ef403356ab85173ba900242781fba0ef482e20221cfdc` | `a99c3ef21e6da1f48d7e19e185d578691e043f03a07920c8d8182f08ad3f3448` |
| SelectUserModal.vue | `b1b39ce5557dc43f8ab619bb4c2202cdd73f4abd537510e5fe6c587d1ad7c8f1` | `60fb4d0ef8aea07f9e6a4c162db176781b039359a72a32fc96d4d0eea943926c` |

产品 hash 与作者冻结值、最终浏览器预览 manifest 相同。UserModal、DeptRoleUserModal、DepartList 和 JeecgListMixin 未由本次作者修改；本 Agent 没有改动 PR61/PR62 的产品行为。

## 既有 64 条专项回归及测试适配

首次使用未改动的既有 `class-member-context.test.cjs`，实际为 57 PASS / 7 FAIL / 共 64，退出码 1。7 个失败都停在 `rowPrompt` 对旧模板字面的识别：测试仅接受 `@click="confirmDelete(record)"`，新增的 `@click.prevent="confirmDelete(record)"` 被误送到更旧的 popconfirm fallback。原始日志 `member-context-first.tap` 保留，不能把这轮记成产品 64 条通过。

根 Agent 查看全量同类失败后，明确授权仅修改既有 harness 这一行正则为 `@click(?:\.prevent)?="confirmDelete(record)"`。实际仍执行渲染绑定的 `confirmDelete(record)`，确认快照、受控回调和所有请求断言原样；旧 popconfirm fallback 也保留。没有删测试、放宽请求结果或新增 CSS 镜像测试。测试 diff 仅一行；文件 SHA256 从 `8d0131e0bbdd24690efdfa926013e5083d6e1ea6c9a3ca473e38222471161756` 变为 `1823612110d3beb9730a7772e11d9fcaa72d33c34a976397cffe92ae71446bbd`。

工作目录为本任务工作树 `web`，运行 `node --test --test-reporter=tap tests/class-member-context.test.cjs`，候选最终 64 PASS / 0 FAIL / 共 64，退出码 0；日志 `member-context-final.tap`。再用完全同一文件及同一断言设置 `SOURCE_REF=8f58b323`，旧 PR60 仍为 13 PASS / 51 FAIL / 共 64，退出码 1；日志 `member-context-old-same-criteria.tap`。两轮均零 skipped / cancelled / todo，旧版差异未被 harness 适配抹除。`git diff --check` 通过。

根负责分支完整前端测试，本 Agent 没有重复全量运行；已只读复核 `branch-tests-final.log` 最后计数为 561 PASS / 0 FAIL / 共 561，零 skipped / cancelled / todo。首次全量的模板识别失败日志 `branch-tests.log` 也保留。完整测试结果是根的执行，本 Agent 只核对日志及其与本次测试变更的关系。

## 根浏览器证据的复核

以下均为根 Agent 执行真实 Vue/Antd 浏览器、内存 API 预览后保存的记录；本 Agent 只读核对 JSON、manifest 和部分截图，没有另开浏览器。

- `baseline-global-sizes.json` 与 `candidate-sizes.json` 在相同全局样式下对照：独立组件 390px 旧 document/body 为 411/412，候选为 390/390；768、1440 候选 document/body 均等于视口。768px Selector 旧左右边为 0/1000，候选 16/752，弹层关闭与 OK 的横向位置在视口内。1440px 候选仍保留 1000px 最大宽。390px 表体为局部 326/921，不再传给文档。
- `baseline-final-parent-sizes.json` / `candidate-parent-sizes.json` 保留实际 DepartList 嵌套：旧 390px 虽 document/body=390，成员 card 为 338/410，表格为 290/386；候选 card 为 278/278，表体为 278/921，搜索为 244/244，分页为 278/278。768 和 1440 父容器下搜索、card 和分页同样不外溢；表格宽列经自己的横滚访问。
- `candidate-parent-stress.json` 与对应 390px 长文本、多页截图：region 278/278，document=390；滚动到操作列后编辑横向范围 197.5–241.5，更多 245.5–309.5，仍位于视口内；分页独立保留且没有跟随宽表格外移。本 Agent 查看 `candidate-parent-390.jpg`，搜索/工具栏已换行，表格右侧列需要横滚，符合明确显示的滚动提示。
- `candidate-selector-short-keyboard.json`：390×650 时关闭、OK 按钮 bottom=610，页脚仍可达；表头和表体记录 left/scroll=120，显示左右键委派后的同步横滚。`candidate-member-keyboard.json` 同时记录操作列在独立 390px 组件中可见。已查看 768px Selector 截图，确认弹层左右留白、搜索换行与页脚仍在弹层内。
- `candidate-behavior.json` 保存真实预览的查询结果、列表失败恢复、26 条多页数据以及下一页 `11–20 共26条`；根补充说明已实际选人。最终预览树 fixture 补 `value` 后，根报告 candidate-final 的 console error/warn 为空。此 console 结论是根报告，本 Agent 没有独立采集控制台。

本次结果排除了“21px 只是日志 PRE 或预览外壳造成”的简单解释：旧 standalone 确实有成员表格沿祖先传出的 DOM 外溢，实际父级又能把同一宽度问题裁切而使 document 数值看似正常。负 margin 和未局部横滚是相符的静态原因，仍不把全部 21px 精确分配到某一条 CSS。

## 验证范围与剩余边界

64 条方法 VM 回归证明既有班级上下文隔离及共享调用契约没有回归；它不执行原生 Vue watcher/render、Antd 缓存或 CSS。AST 和 diff 审查证明本次没有改业务 script；根的浏览器记录证明指定预览下布局、局部滚动、分页和弹层操作可达。三类证据分别保留。

实际父页面预览仍用内存 API，外围部门编辑、上传、课程/权限面板被替代，没有认证/全站导航、真实三角色或生产数据。此轮没有做触屏设备实机、各浏览器、任意缩放/字体、屏幕阅读器或正式无障碍合规验收；新增 label、aria-live、region 和焦点样式不能替代这些检查。这里没有发现可归入当前两组件布局修复的额外产品阻断，也不声称全页或全站响应式已经验收。
