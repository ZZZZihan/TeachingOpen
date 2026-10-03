# 天津工业大学教师作业与批改工作台

将宽表格和分散操作改为待批改优先的作品列表：学生、班级、提交时间、类型与主要操作集中呈现，讨论、标签及次要管理动作在需要时展开。使用 #39 的天工紫及天津工业大学文字身份，保持白底、明确层级和细边框。

产品提交 `852221a`，基于 #39；运行后端依赖 #40（包含 #38 的讨论/反馈保留修复）。PR 保持 Draft，完整认证浏览器及用户视觉验收尚未完成。

## 最终行为

- 默认待批改，支持其他状态、筛选、分页与排序；未提交的筛选草稿不随状态切换生效。列表失败清除过期记录，保留条件并提供重试；迟到请求不覆盖当前结果。
- 打开批改时重新读取作品和原反馈。评分读取失败时不能保存；讨论独立失败与重试，不会把旧讨论列表写回。
- 0–5 分不预选，零分按数值 0 保存；也可只写评语。评语上限 512 字，与现有数据库一致。保存期间限制重复提交与关闭，失败保留输入；放弃修改需明确确认。未改评分时不重发，改动时保留额外已有反馈行。
- 保留预览、文件打开、克隆、标签、删除和导出入口。文件地址仅接受 HTTP(S)，新窗口隔离 opener。预览 iframe 关闭即卸载，避免依赖某个引擎全局对象。批改和预览弹窗都限制在当前视口内。
- 名称/姓名/标签筛选后的导出要求先选中结果，避免后端导出不能表达相同模糊条件时范围不一致；错误 JSON 不会另存为伪 Excel。班级/课程等原有高级筛选仍保留。

## 自检范围

- 前端 **202/202**（184 既有 + 18 本项），四个改动 Vue 文件 ESLint **0 errors / 0 warnings**，生产构建成功。构建仍有六项既有类型警告及旧 Browserslist 提示，没有升级依赖。
- 真实组件 + 本机合成 HTTP：**25/25** 交互检查，包含搜索草稿、失败重试、读失败保护、讨论单独恢复、零分保存和重开、忙状态/退出、iframe 卸载、安全文件链接、分页、导出失败、空列表、键盘评分和预览三宽度。
- 列表和批改弹窗另有 **6 项**新版宽度观察：390 / 768 / 1440 无横向溢出，手机可滚动到保存按钮。旧版三个列表宽度只作对照；旧表格内部横向滚动，不声称旧文档本身溢出。15 张截图见下方及 [checks.json](evidence/teacher-workbench/checks.json)。
- 真实 Java/MySQL 合成认证单独 **31/31**：列表筛选与班级范围、所需字段、读取、学生讨论后教师零分保存、学生读回、原讨论/归属/附件保留、缺省评分保留、学生/异班教师/匿名拒绝。验证结束后 68 个非审计表及附件摘要一致。它不是浏览器登录证据。

浏览器初查发现 768 宽度的固定尺寸弹窗越界，已增加视口宽度限制并完整重跑。其余检查中，旧表格隐藏副本被错误选择、多页合成样本继承了已批改状态、开场动画未结束时测量位置，分别修正选择器/合成样本/等待条件后通过；没有为满足测试改变真实权限。初期预览替身未匹配导入路径造成无关角色请求 404，别名已修正。受控 503、故意缺图 404 和 Ant Design 旧焦点警告保留在本机日志，不声称控制台零错误。

| 页面 | 修改前 | 修改后 |
| --- | --- | --- |
| 列表 1440 | [前](evidence/teacher-workbench/teacher-before-list-1440.png) | [后](evidence/teacher-workbench/teacher-after-list-1440.png) |
| 列表 768 | [前](evidence/teacher-workbench/teacher-before-list-768.png) | [后](evidence/teacher-workbench/teacher-after-list-768.png) |
| 列表 390 | [前](evidence/teacher-workbench/teacher-before-list-390.png) | [后](evidence/teacher-workbench/teacher-after-list-390.png) |
| 批改 1440 | [前](evidence/teacher-workbench/teacher-before-grading-1440.png) | [后](evidence/teacher-workbench/teacher-after-grading-1440.png) |
| 批改 390 | — | [表单](evidence/teacher-workbench/teacher-after-grading-390.png) · [滚动至保存](evidence/teacher-workbench/teacher-after-grading-390-footer.png) |

## 重跑与限制

从仓库根执行，使用原锁定依赖和隔离环境。预览只监听 loopback，使用六名虚构学生；字典、收件人选择、旧讨论表格和编辑器 iframe 是明确替身。其余列表/评分/预览组件及 Ant Design 为实际产品代码。

```sh
cd web
npm test
node tests/teacher-preview/build.cjs "$preview_after"
node tests/teacher-preview/build.cjs "$preview_before" 193b8bfb349e7b2aa40d51f145b54b07e48ca236
python3 tests/teacher-preview/server.py --port 18133 --directory "$preview_after"
# 另一终端以 18134 服务 before，然后用 Playwright CLI run-code 执行 verify-visual.js 和 verify-interactions.js
```

真实契约脚本 `web/tests/teacher-preview/verify_backend.py` 需要 `--support-repo` 指向 #40 或最终组合、`--runtime` 指向任务自有合成环境、`--jar` 精确匹配运行包，以及全新 `--output` 路径。

本项没有登录验证码操作、完整角色导航、真实编辑器引擎或七牛联调，也没有新增后台权限或解决明确替换评分之间的并发覆盖。共享预览组件影响学生“我的作品”，本轮验证了 URL 构造及实际组件卸载，完整认证学生回归待完成。当前 Agent 工程自检不能替代人工试用。未远端合并、部署或完成整体产品化目标。
