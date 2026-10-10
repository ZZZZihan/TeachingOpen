# Python source loading 专项验证记录

2026-10-03，基于 `f906f8e782795ddd670725e85ffa4ea1756b665c`（PR52）。最终冻结版 source-loading 专项 **22/22**；连同现有 URL、桥接保存和输出专项 **71/71**；冻结后执行一次全量 `web/tests/*.test.cjs`，**369/369**，失败、跳过、取消均为 0。

完整 TAP 记录保存在 [专项日志](../../../docs/optimization/evidence/python-source-loading/node-specialized.tap) 和 [全量日志](../../../docs/optimization/evidence/python-source-loading/node-full.tap)。[测试时产品清单](../../../docs/optimization/evidence/python-source-loading/node-tests-product-manifest.json) 记录 SHA256 与基线比对。专项耗时 242.79ms，全量耗时 2333.55ms；耗时只描述本机这次执行。

`harness.cjs` 按真实 HTML 的脚本列表选择入口，加载实际 readable helpers，从 shipped bundle 提取实际 PythonEditor 的 data、created、mounted、methods 和 render。断言同时检查真实 Run 按钮 disabled、直接调用 runit 的阻断，以及就绪后真实 execution coordinator 收到的代码和 opaque frame。浏览器宿主的 DOM、native fetch、Ajax、raw editor、nextTick 和时钟由受控夹具提供；加载、保存、guard 与运行决策来自产品代码。

新增检查覆盖：

- index/app 与 player/appPlayer 每页一个 entry、单次初始 GET、模板与预览的不同缺参数行为、完整 URL 的 query/plus/percent/hash 保留及无 API 请求头；重复 mount 和连续点击 retry 不增加并发请求。
- Ace 与 CodeMirror 原生编辑器尚未就绪时保持 loading 和 Run 禁用，raw 就绪后跨 nextTick 确认 raw、wrapper 与 host 一致；CRLF 规范化、raw 永不就绪的应用失败、预览保持只读，编辑器在 ready 时解锁。
- 404、断网、HTML/JSON 响应、无效地址、过大文件与 15s 超时的可识别失败；超时 abort 后迟到响应不能应用，retry 正常恢复。
- 请求返回前的编辑和 apply nextTick 窗口中的编辑均被保留，状态为 load-error 且 Run 仍禁用。空文件与同内容初始加载、同内容 retry 后编辑跨 350ms 保留；夹具故意保留旧 300ms wrapper，以证明 helper 没有调它。另直接执行两个 bundle 的真实 CodeMirror setter，确认同步应用且不存在随后覆盖。
- workId 先读取 metadata，再只请求该作品文件；保存上传当前 raw 内容、保留作品 ID、更新地址、清理旧 source 参数；受控重开读取保存后的内容和标题。真实 UI 保存重开的证据由 root 执行的实际浏览器流程提供。
- 新 source-loading manifest 先逆恢复 PR52 bundle SHA，再逆 execution、URL、output 历史层；旧清单未更改。PR52 的 execution.js、runner.js、runner-loader.js、worker.js、worker-turtle.js、turtle-renderer.js 与基线字节相同，现有 Worker/turtle/lifecycle 全量回归包含在 369 项内。

历史测试适配只改变真实调用入口和 transport：URL 测试从同页双 bundle 改为各自的 HTML/helper 入口，下载地址按浏览器 URL 解析成绝对地址，保留所有旧 parser 断言；保存桥接的源文件 stub 从 Ajax 改成 native fetch，原 API/upload/session 测试仍保留；执行专项夹具明确从 source-ready 状态开始，而加载 gate 由新页面夹具验证。原输出补丁链先撤销 source-loading 层，保留原历史 hash。

首轮专项的 5 个失败为夹具适配错误：错误使用 coordinator 的离线能力检测 frame，以及假设旧 output manifest 存在 after_sha256 字段。修正夹具后完成上述最终记录，没有以修改产品预期来消除失败。

本 Agent 未启动浏览器或 HTTP 服务、未安装依赖、未注入认证、未访问生产、未提交或推送。HTTP fixture 的新增模式通过 Python AST 校验；未将其宣称为本 Agent 的实际浏览器验证。真实 Chromium 14 个功能情境、6 个宽度状态和保存重开结果分别见 root 的 [浏览器记录](../../../docs/optimization/evidence/python-source-loading/browser-final.json)、[保存重开记录](../../../docs/optimization/evidence/python-source-loading/save-reopen.json) 与对应截图。本记录不把受控 VM 验证替代实际 UI 验证，也不重新主张本轮测过 Worker CPU 终止。

可复现命令（仓库根目录，使用现有 Node；不安装新依赖）：

```sh
node --test web/tests/python-source-loading.test.cjs
node --test web/tests/python-source-loading.test.cjs web/tests/python-preview-url.test.cjs web/tests/python-bridge.test.cjs web/tests/python-output.test.cjs
node --test web/tests/*.test.cjs
```

最终关键 SHA256：

| 文件 | SHA256 |
| --- | --- |
| source-loading.js | aa2c55aadb776df7825f97ef969e45598eafaafacfa87c6169a2c6b9fc5266a9 |
| editor-bridge.js | a54a9937214f5e50e1faecca4cf665dd280f6443cf74a0d8af7c8cfae3056aca |
| persistence.js | a41c51846744be8532d98c2ce449d219dd985b24c464fd62abdda45a36180ab3 |
| static/js/app.js | 34fb61d7c5a5637d3756deda0f0f3ef92c8576d7d992fc925fd2d5c8b3bec392 |
| static/js/appPlayer.js | 6e972a3abdc8a06947ba364c12b7128a568438824c725b163b49ac8f2eb1d5e1 |
