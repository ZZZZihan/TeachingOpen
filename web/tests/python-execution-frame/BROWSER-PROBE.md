# 自建浏览器夹具使用

只用于当前任务拥有的 loopback 页面和新命名 Playwright CLI 会话。先记录空闲端口、
服务 PID 和浏览器会话名；结束后仅关闭这些自己创建的资源。该测试目录不会读取令牌、
登录真实账号或访问写 API。

在工作树根启动只读服务：

```sh
python3 web/tests/python-execution-frame/server.py --port <owned-free-port> --directory web/public
```

打开 `/python/player.html?queryEncoding=uri&url=%2Ffixtures%2Fseed.py` 或
`/python/index.html`，等待实际组件完成挂载。使用已安装且匹配本机缓存的
Playwright CLI；不安装、升级浏览器或依赖。Playwright 的 `run-code` 可执行以下
代码，捕获发生在子 frame/Worker 的 console 事件，时间戳由浏览器外记录：

```js
const consoleEvents = []
const collect = message => consoleEvents.push({
  text: message.text(), observedAtEpochMs: Date.now()
})
page.on('console', collect)
try {
  await page.addScriptTag({ url: 'http://127.0.0.1:<owned-free-port>/__frame_probe.js' })
  const report = await page.evaluate(() => TeachingPythonFrameProbe.basic())
  const checked = await page.evaluate(({ report, events }) =>
    TeachingPythonFrameProbe.attachConsoleEvidence(report, events),
    { report, events: consoleEvents })
  return { report: checked, consoleEvents }
} finally {
  page.off('console', collect)
}
```

`basic()` 使用实际挂载的 `PythonEditor`、实际 `runit` 和运行控制，覆盖有限 Python 2、
输出文字、父输入提交与取消、睡眠后替换、受控 500ms JavaScript 忙循环和 turtle
square/text/undo。显示上限、合成 realm canary、mouse/key 回调样例位于
`TeachingPythonFrameProbe.fixtures`；它们可经 `run(fixtures.<name>)` 运行。

`FRAME_PROBE_BUSY_ENTERED` 只在循环实际完成至少 20ms、带迭代计数后输出；
`FRAME_PROBE_BUSY_DONE` 是有限循环结束标记。报告会记录 Stop 的 epoch 时间。
确认 END 晚于 Stop 表示 CPU 没有立即退出。Worker 的终止可能存在浏览器退出宽限期，
因此 500ms 探针不能判定最终退出失败；最终终止需较长但有界的运行与不停止对照。
缺少 console 或 END 只能说明没有观测到标记；
不能据此声称 CPU 已终止。返回值的普通 `pass` 表示该项显示/生命周期断言通过，
CPU 终止始终应单独检查 `cpuTermination`，结合外部证据和真实终止 API 的行为判断。

Node 模拟时钟、浏览器显示、Worker 终止、跨浏览器响应性和人工验收分别给出结论。
此探针已对齐 Worker 的异步 Stop/clear：等待可信 host 的确认和实际 frame 移除，
普通取消在当前候选需约 2.5 秒。该等待不充当 CPU 死亡证明。

独立的 `realm-network-probe.js` 可在同一自有 loopback 页面加载。它只创建唯一命名
的 synthetic localStorage/DOM canary，并在 Worker 有限程序中尝试访问它们、创建
嵌套 Worker 与 `credentials:'omit'` 的合成 GET。结束后恢复 canary 并等待 clear。
使用实际 browser console/CSP 或 requestfailed 的拒绝证据；仅 fetch 失败、缺少请求
或 canary 未变不能单独证明网络策略通过。

```js
const consoleEvents = [], failures = []
const onConsole = message => consoleEvents.push({text: message.text()})
const onFailed = request => failures.push({url: request.url(), failure: request.failure()?.errorText || ''})
page.on('console', onConsole)
page.on('requestfailed', onFailed)
try {
  // browser-probe.js is already loaded, or load it using its absolute test path.
  await page.addScriptTag({path: '/absolute/worktree/web/tests/python-execution-frame/realm-network-probe.js'})
  const report = await page.evaluate(() => TeachingPythonFrameRealmProbe.run())
  return await page.evaluate(({report, events, failures}) =>
    TeachingPythonFrameRealmProbe.attachEvidence(report, events, failures),
    {report, events: consoleEvents, failures})
} finally {
  page.off('console', onConsole)
  page.off('requestfailed', onFailed)
}
```
