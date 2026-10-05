# 认证页面外壳品牌修复：作者记录

正常登录后的课程页面曾出现 `我的课程 · undefined`、`课程单元 · undefined`，顶栏留下没有平台名称的“欢迎使用”，默认 Logo 和个人头像仍使用旧 T 图片。本次统一启动与路由标题的品牌默认值：没有有效自定义名称时显示“天津工业大学 · 人工智能教学平台”；有有效自定义配置时继续优先使用配置。

## 实施范围与根因

基线为 `fix/student-work-loading` 的 `fcaaf6d82dfaa8b3a0120c4104a6b07d8e8ad1f3`。实现位于独立 `fix/authenticated-shell-branding` 分支。实际登录后的动态路由由 `utils/util.js` 生成并使用 `TabLayout`；启动时的默认标题原本正确，但 `TabLayout.changeTitle` 随后直接拼接缺失的 `sysConfig.brandName`。顶栏与 Logo 在创建时保存同一缺失字段的快照，默认头像又复用了 `/logo.png`。

产品仅修改六份文件：`utils/platformBranding.js`、`main.js`、`TabLayout.vue`、`GlobalHeader.vue`、`Logo.vue`、`UserMenu.vue`。新的小型 helper 仅接受非空字符串，统一默认名称与页面标题，不修改原配置对象；缺失或非法的路由名称直接使用平台标题。当前品牌配置更新时，标题、顶栏和 Logo 同步响应。

顶栏显示完整品牌名称，空间不足时截短，保留完整 title。无配置 Logo 显示克制的“天工”文字标识；有效自定义 Logo 继续通过既有文件地址解析器加载，加载失败回退文字，新图片配置到达后恢复。个人头像优先，其次有效的平台默认头像，最后使用 AntD 的中性 user 图标；图片失败也由实际 AntD Avatar 回退图标。文字标识不是官方校徽。本次不调整主题色、SettingDrawer、登录与权限逻辑、菜单路由、业务页面或后端配置。

## 工程检查

作者侧最终定向检查 **38/38**：新外壳测试 19 项、原启动测试 18 项和新增启动测试 1 项。测试编译并执行实际四份 SFC 的脚本和模板，使用真实 Vue、Vuex、项目 mixin、既有 `getFileAccessHttpUrl` 及依赖中的真实 AntD Avatar，覆盖以下行为：

- 空白、缺失、非字符串品牌的默认值，完整自定义品牌优先，以及原配置不被改写。
- 首页与普通页面标题，缺失页面名称不出现 undefined，字段和整份配置替换后标题更新。
- Logo 无图片时的文字标识，相对地址、HTTP 地址、七牛地址，图片失败回退与新配置恢复。
- 个人头像优先，个人地址被既有解析器拒绝后使用平台配置，缺失头像与图片失败显示 user 图标。
- 实际启动路径在非法品牌值下正常挂载，保留有效自定义标题。

分支完整 `npm test` **645/645** 通过，0 失败、0 跳过。最终产品与测试的 SHA-256 及原始输出分别保存在私有 `shell-author/source-manifest.json`、`final-focused.tap`、`final-full-suite.log` 与 `test-agent-final-summary.json`。

所有改动文件均使用 `eslint --no-ignore` 显式检查。新 helper、`main.js`、`Logo.vue`、新测试文件均为 **0 errors / 0 warnings**。三个大型旧外壳组件和原启动测试仍有存量诊断，未将其全量检查写成通过；与基线逐行比对后，新增代码诊断为 0：

| 文件 | 基线 errors / warnings | 本次 errors / warnings |
| --- | --- | --- |
| TabLayout.vue | 89 / 251 | 87 / 242 |
| GlobalHeader.vue | 14 / 100 | 13 / 94 |
| UserMenu.vue | 74 / 124 | 68 / 114 |
| startup.test.cjs | 27 / 221 | 27 / 221 |

Node `v26.7.0`、npm `11.19.0`，复用已有依赖；本分支与依赖来源的 `package.json`、lockfile SHA-256 一致，未安装依赖。正式前端构建使用 `NODE_OPTIONS=--openssl-legacy-provider npm run build -- --dest <私有目录>/dist-final2`，成功完成。产物只写入本任务独立目录，没有覆盖现有 candidate 或运行实例的 dist。构建仍报告 12 个 CSS 顺序／包体等 warning，并有 Browserslist 数据过期提醒；未将构建成功描述为零 warning。

## 过程中遇到的错误与修正

定向测试首次为 27/37：测试夹具错误地把配置放到根 state，而实际代码使用 `state.user.sysConfig`，并有一项断言沿用旧“欢迎使用”文案。修正夹具与断言后 37/37，再增加个人头像解析器拒绝后的回退检查，最终 38/38。没有放宽产品行为断言，也没有把初次失败算作通过记录。

私有 lint 比较脚本首次假定 ESLint 的零诊断结果也包含 source，因而抛错；改为单独保留基线原文后完成比较。两次私有源码／manifest 检查因工作目录在 web、路径再次加 web 而读不到文件，纠正工作目录后重做。均未修改产品行为或旧资产。新增代码的缩进诊断已修正；最终冻结字节再次构建，原始构建与最终构建日志分别保留，不覆盖记录。

## 证据范围和后续验收

初始标题与外壳问题来自主 Agent 的正常认证浏览器操作及保存截图，作者只读核查源码和该截图。本分支的结果属于源码行为、VNode／VM、lint 和正式构建检查，没有新建组件预览、操作浏览器、登录、请求真实 API、修改数据库或切换已有运行服务。

本补丁的真实认证外壳视觉与多宽度验收、独立代码审阅，以及和 candidate 的组合验证由主任务随后分别记录。SettingDrawer 的 AX 节点不等于截图中有外露侧栏，不能据此宣称或修复未观察到的视觉问题；本次未触碰该组件。这份作者检查不替代三角色真实整链、编辑器保存重开提交、用户审美认可或目标环境验证。

私有证据目录为 `.devspace/artifacts/authenticated-role-flow-20261005/shell-author`，与主任务的认证浏览器证据、只读 shell-review 分开保存。PR 以 `fix/student-work-loading` 为 base，提交与推送限当前独立分支，未合并、部署或本地整合 candidate。
