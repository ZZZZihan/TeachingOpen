# 学生作品反馈可读性：作者交付记录（2026-10-05）

本次改善两个真实学生入口：`/account/mineWork` 的 `MineWorkList.vue` 表格，以及 `/account/center` 的 `Index.vue → page/index.js → MineWorks.vue` 卡片。原表格只在鼠标悬停时用 tooltip 提示教师评语，禁用星级无法区分零分与未评分；原个人中心卡片没有反馈。两处现在共用只读 `StudentWorkFeedback.vue`，直接显示评分和评语摘要，并提供可用键盘打开的全文按钮。沿用天津工业大学紫色、既有布局和 Ant Design Vue，没有新增依赖。

## 行为与数据范围

评分按接口的 `row.score` 处理：整数 0–5 是有效分，兼容去除首尾空白后的单个数字字符串；空值、非法格式和越界值显示“未评分”。0 分显示 `0 / 5`。`row.teacherComment` 非空白字符串直接保留原文；未评分但有评语、已评分但无评语、完全无反馈均有明确文字。没有将作品状态推断成评分结果。

`GET /teaching/teachingWork/mine` 返回每行的一组 `score / teacherComment`。现有查询关联批改记录，未提供反馈数组、最新反馈排序或按作品 ID 聚合；本次不修改这个接口，也不将显示内容称为“最新评语”或“全部反馈”。评分、批改、CRUD 与权限规则保持既有契约。

摘要按 Unicode 字符截取前 120 个字符，最多显示三行。全文使用 Vue 文本插值，保留换行和首尾空白，连续字符、长链接可换行；HTML 标签只显示为文字。全文有可聚焦的局部滚动区，按钮最小高度 44px。关闭后清除当前快照并恢复到仍存在的触发按钮；作品替换、刷新内容或组件销毁立即关闭旧详情。旧关闭动画的回调不能清除已经重新打开的详情。

表格限制为自身横向滚动，在窄屏显示滚动提示；聚焦表格区域后可用左右方向键滚动，子控件按键不会被拦截。原表格作品操作改为原生按钮以便键盘使用，事件处理和请求保持原样。卡片使用自适应网格，手机单列且允许缩小，避免固定宽度裁切反馈。

## 验证与迭代事实

- 作者真实 Vue / 实际 SFC 行为测试：13/13 通过，覆盖零分与非法分、评语文本保持、HTML 纯文本、真实两个父组件接线、开关与焦点回调、关闭后重开竞态、刷新和销毁清理、局部键盘滚动。Ant Design 的实际 DOM 和动画由浏览器验证。
- 分支完整 `npm test`：597/597 通过。最后的父组件变更仅修正本次新增代码缩进，其后再次运行上述 13 项；没有重复正式产品构建，最终组合构建由根 Agent 执行。
- 所有新增 JS/CJS、共享 SFC 和 helper 均显式执行 `eslint --no-ignore`，0 错误、0 警告。两旧父组件以同配置逐字对比基线，错误由 82 降为 77，警告仍为 227，无新增问题类别或数量；保留旧组件的存量 lint 问题，没有全面格式化旧文件。
- 独立审阅者使用真实 Vue 与实际 SFC 提供 20/20 离线探针通过；这是独立审查，与作者测试分别记录。提交后由审阅者绑定最终提交及父文件 hash。
- 根 Agent 用 CUA 在合成预览检查 390 / 768 / 1440 三种宽度、键盘全文入口、长文本、纯文本标签、关闭返回焦点及局部表格滚动；报告三个宽度页面无横向溢出。最终预览补入实际全局过滤器后，浏览器 console warning/error 均为 0。浏览器证据由根 Agent 保存在私有 `student-feedback-20261005/browser` 目录，最终对外说明由根 Agent 绑定截图与源清单。

第一次新版预览构建曾失败：Less 对 `minmax(min(100%, 260px), 1fr)` 中的原生 `min()` 提前求值，报 incompatible types。随后改为桌面 `minmax(260px, 1fr)` 和手机 `minmax(0, 1fr)`；成功构建后的日志覆盖了早期失败日志，因此在此保留失败事实与原因，不能把整轮描述成首次即通过。

独立审阅复现了关闭详情后立即重开时，较早的 `afterClose` 回调清掉新详情的竞态；现已在回调里检查 `visible`，并加入作者与独立回归。根 Agent 也记录过草稿预览快速关闭再切换行时未显示全文的一次失败，随后按最终版本重新复核。评分 helper 同时收紧字符串格式，避免 `0x0`、`0e0` 被转换为零分。

预览第一版漏注册 `JEllipsis` 所用的实际全局 `ellipsis` 过滤器，导致卡片 console 警告。此为预览工具缺口，修正方式是在 preview entry 导入实际 `src/utils/filter.js`，没有修改产品 `JEllipsis`。后续 `after-final2` 预览确认警告消失；`after-final3` 只绑定父文件缩进修正后的字节。

## 可复现预览

工具位于 `web/tests/student-feedback-preview`，实际使用 Vue 2.7.16、Ant Design Vue、真实共享 `JeecgListMixin`、真实两个入口 SFC 及其实际 Index/card 映射。BasicLayout/RouteView 认证外壳替换为可调整留白的普通组件容器；字典选择器、未使用的 PageLayout 和无关作品预览 iframe 使用受控替代。真实全局过滤器注册保持产品行为。预览不是完整平台登录页面。

合成服务只监听 `127.0.0.1`，只读提供标签和分页作品。10 种合成样例包含零分、字符串零分、仅评语、未评分、仅评分、长中文、多段落、连续字符与长链接、HTML 字面文本、空白评语和普通反馈。POST/DELETE 及其他 teaching 接口拒绝写入；无 API 代理、真实数据、令牌或平台会话。

在 `web` 目录可使用既有依赖运行：

```sh
node tests/student-feedback-preview/build.cjs OUTPUT c2c3eac
node tests/student-feedback-preview/build.cjs OUTPUT
python3 tests/student-feedback-preview/server.py --port 18308 --directory OUTPUT
```

分别访问 `/?view=list` 和 `/?view=center`，开启“容器留白模拟”检查局部宽度。构建工具生成 SFC 源快照和 SHA-256 清单。私有作者目录保留 before、after、after-final、after-final2、after-final3，互不覆盖冻结的预览证据；正式 dist 没有被本工具覆盖。

这些证据只支持本机合成组件的行为和可读性。真实登录、真实学生账户读取、实际教师批改后的完整链路、部署和生产验收仍待执行，未绕过 CAPTCHA 或注入平台会话。
