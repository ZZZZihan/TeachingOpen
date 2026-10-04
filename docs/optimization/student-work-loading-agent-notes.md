# 学生作品列表加载与失败恢复：作者记录（2026-10-05）

本次只改善 `/account/mineWork` 的 `MineWorkList.vue` 表格，以及 `/account/center` 原样 `Index → page/index.js → MineWorks.vue` 卡片的读取过程。原两个加载器缺少 catch/finally 和请求归属检查：网络或 HTTP 错误后 loading 悬挂，业务失败没有可恢复的列表状态，迟到响应可能覆盖新结果。新实现为两个列表提供明确加载、固定安全错误、原生键盘重试按钮和成功空态，继续沿用天津工业大学紫色及既有 Ant Design Vue 风格。

## 局部行为与契约

表格只局部覆盖 `loadData` 并增加 `retryList`，仍复用真实 `JeecgListMixin` 的条件、排序、筛选、分页与查询参数组装。新请求开始清除旧行、旧选择和旧错误，避免失败时把旧结果当作本次查询结果。每次真正发送的参数做深复制，保存为 `lastListParams`；重试重复这份快照及其页码、页大小，不读取失败后仅编辑、尚未点击查询的输入。明确点击查询仍使用当前输入，`loadData(1)` 仍归第一页。

表格有独立 `listLoading`，状态区、aria-busy、表格 spinner 和重试防重复均使用它。局部 loader 继续设置旧 `loading` 供既有逻辑兼容，但既有批量删除 `.finally` 清共享 loading 不会提前结束列表状态。没有修改全局 mixin 或批量删除流程。

卡片局部替换 `getWorkList`，保留原 `getAction(url, null)` 调用及既有 mounted 接线，不增加分页或改变参数。后端 `/mine` 默认 pageSize 是 999；卡片已有但未接线的 pagination、大量作品渲染与超过默认上限的行为属于另行评估范围，不能把本机 fixture 默认 10 条理解为生产默认 10 条或声称产品只读首 10 条。

响应必须是 `success === true`、包含 records 数组、每行有可用 ID、total 是非负安全整数数字；非法 records、缺少数据、非法 total 和业务 false 进入错误态。数字字符串 total 视为异常体，遵循现有 IPage 的数字契约。有效 `records=[] / total>0` 是当前页空态，保留表格和分页导航；没有强制校正页码或暗改删除行为。表格使用 v-show 控制可见性，在加载和失败时仍保留 Ant Design 实例和内部引用。

两个 loader 都使用递增 requestId 和销毁标志。只有当前请求能提交成功、错误和 finally；旧成功、旧失败、旧收尾及销毁后的结果均不能覆盖当前状态。固定文案区分数据异常、业务失败、访问不可用、超时、服务错误和网络错误，不显示任意服务器 message、stack 或 HTML。状态区重试按钮最小高度 44px，有可见键盘焦点；loading/error/empty 分支互斥。

全局 `request.js` 的 60 秒 timeout、401 会话处理及全局 notification 保持原样，真实环境仍可能同时出现全局请求提示。标签查询与其他 CRUD 的既有错误处理不在本次范围，不能将本次列表恢复表述成“全页面网络错误均无未处理异常”。

## 作者验证与独立审查

- 作者实际 Vue / 实际 SFC 行为测试 28/28。实际 JeecgListMixin 经 Babel 编译保留全部逻辑，查询使用实际 util.filterObj；受控替代仅提供 API 返回和无关 UI 依赖。覆盖两入口启动、各类失败、成功空态、请求完成顺序、销毁、实际状态组件 native button 的 emit 接线、未提交编辑与失败快照、分页恢复、共享 loading 干扰及表格实例保留。DOM 和 Ant Design 延迟滚动回调另由浏览器验证。
- 完整分支 `npm test` 625/625，通过包括上轮反馈的 13 项回归。旧反馈测试仅适配新增状态组件注册及成功 ready 状态，既有反馈断言保留。
- 所有新增 JS/CJS、helper、状态组件均显式 `eslint --no-ignore`：0 错误、0 警告。父组件按相同配置对比 f0980ce2：表格 54 错误 / 154 警告保持不变；卡片由 23 错误 / 73 警告降为 21 错误 / 59 警告，没有新增类别或数量，未全面格式化旧代码。
- 独立审阅者已提供真实 Vue/SFC 的 34 项通过，并为持续表格实例补充第 35 项；最终源清单与提交绑定由审阅者单独保存。独立探针与作者测试、浏览器验收分别记录。
- 根 Agent 最终 after3 CUA 报告三个宽度无页面横向溢出；手机卡片状态区完整跨列。空页翻到第二页再回第一页恢复 10 条 fixture 行，最终代表页 console warning/error 为 0。两个入口的 500、业务 false、非法 records、网络断开、超时和成功空态均能恢复；键盘重试、失败条件快照、迟到响应隔离及恢复后的反馈全文入口均通过。具体截图及 browser/final-report.json 由根 Agent 保存；合成故障预期的 HTTP/network 错误另有记录，不能把它们与 Vue/Ant Design 运行异常混为一类。

私有证据保存于 `.devspace/artifacts/student-work-loading-20261005/author`，包含完整日志、父 lint 基线、源清单和失败迭代日志。作者没有执行正式产品构建，根 Agent 负责最终组合测试、正式 dist、浏览器报告和 PR。

## 合成预览与迭代错误

`web/tests/student-work-loading-preview` 复用既有工具，使用实际 Vue / Ant Design Vue、两个入口 SFC 和原样 Index/card 映射。新构建器将整个产品 src 冻结：旧版由 `git archive f0980ce2 web/src` 获得基线，新版复制工作树 src；webpack 的产品 alias 全部指向冻结目录，最终新版源清单覆盖 424 文件。没有从继续修改的工作区读取旧版依赖。初版 before 在任何产品修改之前编译，随后另存完整冻结的 before-strict2，不覆盖早期浏览器证据。

认证 BasicLayout/RouteView 外壳使用明确标注的普通组件容器。manage 使用 Axios 的合成只读 HTTP 替代，不加载全局认证/通知拦截器；util.filterObj、字典选择器、未使用 PageLayout 和无关预览 iframe 使用受控替代，真实全局 ellipsis 过滤器继续注册。服务仅监听 127.0.0.1，无 API 代理、真实平台会话或持久化。POST/DELETE 拒绝写入。

只读场景包括成功、成功空列表、当前页空但总数 25、HTTP500、业务 false/code510、非法 records、连接断开、4.5 秒延迟成功和请求超时。fixture 默认 pageSize 为 10；真实后端默认 999。超时只在预览传输层缩短为 1.2 秒用于验收，产品 timeout 没有改动。改变场景后可对同一组件重新请求，用于观察迟到响应和销毁保护。

可在 web 目录复现：

```sh
node tests/student-work-loading-preview/build.cjs OUTPUT f0980ce2
node tests/student-work-loading-preview/build.cjs OUTPUT
python3 tests/student-work-loading-preview/server.py --port 18310 --directory OUTPUT
```

打开 `/?view=list&scenario=http500` 或 `/?view=center&scenario=empty`，选择“容器留白模拟”检查窄屏。服务由根 Agent 启动，作者没有操作浏览器或后端服务。

本轮保留了以下失败事实：

1. before-strict 第一次完整冻结构建在 web 子目录调用 `git archive ... web/src`，因 pathspec 相对目录报错；调整 Git 调用 cwd 为仓库根，另存 before-strict2 成功。初次失败日志未被覆盖。
2. 作者第一版 Node 探针直接执行含 JSX 的实际 mixin，23 项因探针解析失败；改为用既有 Babel 编译真实 mixin。第二次剩余一项因 Index 的缩进 import 未被探针识别；修正 import 处理后，新增实例保留回归并最终 28/28。没有为了让探针通过而删除产品 mixin 方法。
3. 新测试初次 lint 的 Promise 参数名和拒绝 fixture 类型产生 6 条错误；改为明确 resolve/reject 名字与 Error fixture 后显式 lint 通过。
4. after2 浏览器暴露 Less 将 `grid-column: 1 / -1` 算成数值，手机状态区形成额外列；after3 改为独立 grid-column-start/end，保留这次浏览器失败。
5. after2 浏览器在空页翻页后触发 Ant Design `scrollToFirstRow/getBodyTable` nextTick 异常，原因是 loader 的 v-if 立即移除表格；after3 改为 v-show 保留表格实例，没有关闭 Ant Design 行为掩盖错误。

after3 是最终产品预览候选，SHA-256 源清单为 `c33ce3380564a252d606c1e2c4cfc37d0e68eb47de7e9c4d2e5b26e83246ba59`，当前产品 src 与其无差异。根 Agent 的最终浏览器结果、三宽度截图和正式构建证据另行绑定。所有证据只支持本机合成列表恢复；真实登录、完整学生作品链路与生产验收仍待执行，未绕过 CAPTCHA 或注入会话。
