# 管理员课程与单元工作台：产品 UI Agent 记录

记录日期：2026-10-03。执行范围为本机隔离工作树 `.devspace/worktrees/admin-course-workbench`，分支 `feature/admin-course-workbench`，起点 `fbf8097f0616cb865ce6ee109ca806b42f4767ef`（课程表单恢复候选，PR 42）。开始及中断恢复后均核对了 Git 状态；开始时没有已有未提交修改。

本记录中的静态检查与代码审查是本 UI Agent 的自检，其他 Agent 的测试结果单独注明。它们都不是用户人工验收、生产发布或实际教学接受证据。没有可设置的 Fast 开关，不声称开启 Fast。

## 修改范围及原因

- `web/src/views/teaching/TeachingCourseList.vue`：将宽表格整理为可扫读的课程行列表。课程名称为主要入口；性质、分类、授权部门、共享状态、首页展示、排序、创建人和日期分层显示。保留新增、编辑、单删、批删、导出、课程性质与分类字典管理，以及原 `/course/courseUnit?courseId=...` 单元维护入口。有效课程地图资源作为链接打开，地图编辑继续由原课程表单提供。原页隐藏的课程导入入口继续隐藏，没有新增权限或业务能力。
- `web/src/views/teaching/TeachingCourseUnitList.vue`：课程、单元名称、简介、作业类型、排序、创建信息分层显示。保留新增、编辑、单删、批删、导入和导出，新增单元名称查询使用真实 `CourseUnitModel` 继承的 `unitName` 字段及原查询接口；原课程选择继续用 `teaching_course,course_name,id` 字典。
- `web/src/views/teaching/course-workbench.less`：两页面共享、在组件内 scoped 的必要样式。白底留白、细分隔线与克制的 `#74256a` 紫色；没有添加蓝色统计卡、编造学校数据、新依赖或新的全局样式。桌面展示封面，窄屏把空间留给正文与维护按钮。响应式断点为 1050、700 像素，390、768、1440 像素实际检查由测试 Agent 的合成预览提供。

没有修改课程/单元表单、mixin、后端、生产配置或数据库。没有接触原 `source/teaching-open`、提交、推送、开 PR、合并或绕过登录验证码。测试 Agent 拥有 `web/tests` 与预览证据，本 UI Agent 没有修改那些文件。

## 查询和恢复行为

- 继续复用 `JeecgListMixin` 的原有表单打开、选择状态和弹窗成功刷新约定；在两个页面局部覆盖列表请求和维护失败处理，没有改动共享 mixin。
- `queryParam` 是正在填写的条件，`appliedQuery` 是上次提交查询的条件。分页、刷新、重试与导出读取后者；输入尚未查询时不会改变已有结果的范围。查询与重置回第一页，保留每页数量。查询后显示条件名称快照；未读到字典名称时只显示“已选择”，不以内部 ID 代替名称。
- `disableMixinCreated=true` 后组件自己只调用一次初始查询。单元页先读取路由 `courseId`，避免无条件请求和带路由条件请求并发；复用同一组件切换课程时监听路由并重新查询。
- `requestId` 排除过期成功和失败响应；销毁后不再更新界面。网络失败、业务拒绝、无记录数组、无有效记录 ID 或无有效非负整数总量，统一进入失败状态，清除旧行、旧总量与选择。查询条件保留，提供重新加载按钮。
- 加载、加载失败、没有课程、筛选无结果分别呈现；不会把旧结果作为新查询的结果显示。每页 10/20/30、前后页和跳页保留；非法、分数和越界页码不发请求。
- 单删、批删、导出和单元导入使用独立操作锁。批删保存确认时的选择快照，阻止重复确认/请求；确认同时核对列表请求版本与当前选中 ID 集合，查询、重置、翻页、路由或选择集合变化后旧确认不再写入，提示重新选择；同集合换顺序仍沿用原快照。独立确认序号阻止旧确认回调修改新的确认状态；删除成功后重新查询，页码超过新末页时回到有效末页再读取。删除失败只提示需要刷新核对，不回显服务端内部错误或谎报成功。
- 导出沿用原 `.xls` 接口与文件名，检查旧 Excel/OLE 签名，拒绝将接口错误响应当 Excel 下载。导入保留原上传接口与 token header，补充网络/业务失败提示及 `201` 部分导入报告链接；报告链接只允许无凭据的 HTTP(S) URL。
- 封面失败降级为普通书本图标；资源 URL 必须从项目原文件访问函数得到非空字符串并通过 HTTP(S)/凭据检查，不把 `undefined` 变为伪资源链接。

## 语义与兼容性核对

- 授权部门空值显示“未分配部门”。共享状态独立显示，不推导全员可访问或声称管理员 UI 决定后端访问权限。该文案来自 root 的审查意见，已经落实。
- 单元父课程名称确认为真实字段：原列表使用 `courseName`；`CourseUnitModel.java:11` 定义该字段；`TeachingCourseUnitMapper.xml:48-54` 的管理查询选择 `unit.*` 与 `teaching_course.course_name`，通过 `unit.course_id` 联表。因此请求字段中保留 `courseName`，没有改用并不存在的 `courseId_dictText`。
- `getQueryField` 显式保留原显示字段及原表单需要的维护原始字段，避免视觉布局决定哪些字段会被读取。
- 测试 Agent 用真实 Vue/Ant 合成预览发现 Ant Design Vue 1.6.3 的 `APopconfirm` 直接包带 `disabled` 的原生 button 时触发 Tooltip 的 `propsData` 异常，删除按钮不渲染。两个页面已将直接子节点改为 span，内部仍为原生按钮，保留 disabled 和测试选择器；`APopconfirm` 本身确有 disabled 属性，操作锁仍有效。此问题由实际组件渲染发现，非静态推测。

## 已执行的本 Agent 自检

- 本机 Node `v26.7.0`。
- `./node_modules/.bin/eslint --no-ignore --fix src/views/teaching/TeachingCourseList.vue src/views/teaching/TeachingCourseUnitList.vue`：退出 0；只针对本 Agent 的两个组件格式修正。
- 修改完成后再次执行 `./node_modules/.bin/eslint --no-ignore src/views/teaching/TeachingCourseList.vue src/views/teaching/TeachingCourseUnitList.vue`：退出 0。
- `git diff --check`：退出 0。
- 核对组件入口、真实 API 路径、字典代码、部门选择约定、单元 SQL 父课程字段、维护表单所需原始字段，以及请求/错误/分页/选择/操作锁代码。没有运行真实后端或把合成结果视为真实角色权限验证。

## 其他 Agent 结果与剩余边界

测试 Agent 已报告第一轮真实 Vue/Ant 合成浏览器检查 62/62、errors=[]。两页 1440/768/390 像素几何均无横向溢出，维护按钮位于屏内。该预览使用实际列表、Vue、Ant 与原列表 mixin，API、字典/部门选择及维护弹窗入口为替代组件；不等价于登录后的真实整体页面。测试 Agent 已冻结最终57项脚本行为测试并报告57/57（其中9项复现旧基线，48项核对新行为），最后追加的真实DOM旧确认竞态检查仍由该Agent完成；结果以其独立记录为准。

本 UI Agent 已实际查看两页全部三尺寸列表截图，以及课程错误、单元空状态、单元390底部分页截图。观察到名称与简介可换行，课程/单元层级和维护入口能辨认，手机保留正文与操作按钮，失败重试与空态入口清晰；这是本 Agent 的视觉自检，不是用户验收。截图位于 `output/playwright/admin-course-after-{course,unit}-{1440,768,390}.png` 及同目录状态图。

root 在本任务中后续取得了生产数据副本的使用授权，由 root/数据 Agent 负责脱敏和隔离。当前 UI 实施没有读取该副本。副本内容适配、真实本地 HTTP 接口、登录验证码、真实字典/部门选择、媒体加载、导入/导出实际 Excel 以及管理员人工使用仍需在各自验证范围内确认。没有修改独立后端问题。

## 最终审查追加：旧批删确认失效

root 最终审查指出：批删确认打开后，同一个单元组件的课程路由仍可变化，原确认保存的 IDs 会变成旧上下文。本 UI Agent 确认这是真实问题，测试 Agent 先留下 `.devspace/admin-course-stale-confirm-before.txt`：两个页面查询变化、单元路由变化各实际发出一次本不应再发出的 DELETE。

两页面的 `batchDel` 因而增加确认时的 `requestId` 与 `deletePromptId`，确认执行前必须仍处于相同列表版本和相同选择集合。失效时只显示重新选择提示；不发 DELETE、不把旧回调当成新确认回调。没有扩大修改到共享 mixin 或后端。测试 Agent 更新原快照测试为“同选择集合顺序改变”，避免继续要求已明确禁止的“换成别的 ID 后仍删除旧记录”行为。

第一轮完整 `npm test` 为272/272、退出0，`npm run build` 退出0；此后出现上述审查修复，正在对最终版本重新执行完整检查。构建输出有 Browserslist 的 caniuse-lite 过期提示，以及12项编译告警，涉及原组件的 CSS 顺序与超建议体积资源；没有安装或升级依赖，最终状态见下方补记。

## 最终版本自检与冻结

旧批删确认修复后、本 Agent 在测试 Agent 冻结57项脚本用例之后，重新执行：

- `npm test`：**279/279通过，退出0**。完整日志保存于本工作树私有 `.devspace/admin-course-tests-full.txt`。本次测试执行为 UI Agent 自检，测试文件由测试 Agent 编写。中间一次执行在测试 Agent 尚未更新旧快照合约时出现两条旧断言失败，要求改变选择后仍发DELETE；改为同集合快照并增加失效回归后，最终完整测试已全绿。
- `npm run build`：**退出0**，完成生产构建。完整日志为本工作树私有 `.devspace/admin-course-build-full.txt`。显示12项编译告警：既有图表/表单/上传/编辑器组件的CSS顺序冲突，以及资源/入口体积超过建议限值；另有Browserslist数据库过期提示。没有通过改变依赖或隐藏告警取得成功。`dist`仅为本机构建输出，不表示部署。
- 针对两列表的 `eslint --no-ignore`：退出0。
- `git diff --check`：退出0。

产品代码 SHA-256 冻结值：

- `TeachingCourseList.vue`：`082b0fd45c5c0e036380130b8c3e282c599581b4d8c5d2da642808d6e777e353`
- `TeachingCourseUnitList.vue`：`543c88b64dade17faa0366e4e19fbb6e97e82f8f53c95f7d1343589b9e7ce1d7`
- `course-workbench.less`：`51986d75dc6db0270be6fa856e536af8c8289cc4813cda6b0c0b87c40c2b4ded`

root另报告37项真实隔离API检查通过，覆盖父课程名称、四种排序与维护表单原始字段。本 UI Agent没有执行这37项HTTP检查，不把它们列作本Agent自检；详见root的独立证据。产品文件已冻结供root最终diff审查与交付准备，后续提交/PR与真实内容验收由root协调。
