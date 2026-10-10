# 受控测试与 iframe 原型的未满足边界

2026-10-03。这份记录只描述第一版 iframe 原型，不能作为最终 Worker 候选验收。

在增加私有 `start` 握手前，Node 专项实际运行 58 项全部通过：frame 15 项、
output 10 项、URL 33 项。Node 检查覆盖真实预编译组件的 `runit`/`clear`、
共享 coordinator/runner 的协议与生命周期、输入等待、显示上限、旧补丁链，
并通过继承的 `runner-loader` 和原 vendor/app bundle 执行有限 Python 2 程序。
其中 DOM、MessageChannel 和时钟由夹具模拟，因此没有验证真实浏览器调度或 CPU 终止。

Root 随后的真实 Chromium 实测发现，Stop 后虽然 frame 已移除，有限 500ms
JavaScript 循环仍运行到结束：`loopSTART` 463ms、Stop 475ms、`loopEND` 940ms。
该证据由 root 持有，见本机主工作区
`.devspace/python-execution-frame-browser/stop-time.log`。这证明第一版未实现真正停止计算；
隐藏旧输出与恢复父页面操作不能代替此目标。

`iframe-prototype-transition.json`/`.tap` 记录随后作者正在增加 `start` 握手时的
诊断快照：15 项中 12 项通过、3 项因测试夹具尚未发送 `start` 失败。
该报告的产品与测试 SHA-256 只代表快照时刻；报告之后夹具已经补齐握手，
并等待 Worker 方案的新契约，未据此宣称最终通过。

上述两份原文件与下述全量日志已移存至本机私有目录
`/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/python-execution-frame-browser/prototype-tests/`。
历史 JSON 内的原输出路径保留原样，文件内容未重写。这里只保留摘要，避免将过渡期整套
诊断日志纳入可复现测试源码；私有路径在其他机器或仓库 PR 中不提供文件下载。

`iframe-prototype-full-suite-diagnostic.tap` 是同一阶段的全量诊断：247 项通过、
7 项失败。其中 3 项是上述夹具契约变化，4 个既有 suite 当时无法加载 Vue/依赖，
不是产品行为退化。Root 随后授权复用已有的
`product-candidate/web/node_modules`，新工作树 `web/node_modules` 已建立本机忽略软链；
没有安装或升级依赖。该阶段按 root 指令冻结，不继续重复全套测试。

浏览器 `browser-probe.js` 明确将 CPU 终止初值记为 `unverified`。
CLI 必须在浏览器外捕获循环内至少 20ms 的 ENTERED 标记与 DONE 时间戳；
把这些记录传给 `TeachingPythonFrameProbe.attachConsoleEvidence(report, events)`。
旧 iframe 原型 DONE 晚于移除表明其没有计算终止机制。Worker 新版的 500ms DONE
可能处于浏览器的退出宽限期，探针只报告非即时性与最终退出未验证；最终终止必须
结合有界长程序、完整不停止对照和外部记录。缺少 DONE 或 console 证据不证明 CPU 已停。
所有忙循环都有 500ms 的绝对上限，未运行同源无限循环。

当前测试 Agent 没有启动浏览器、HTTP 服务、登录、真实 API、提交、推送或生产部署。
当时最终 Worker 候选尚需重新验证；现在冻结候选的 Node 结果由
`docs/optimization/python-execution-frame-evidence/README.md` 及相邻报告给出，实际
浏览器、CPU 退出、像素与跨浏览器记录由主任务分别持有，不能追溯替换原型结论。
