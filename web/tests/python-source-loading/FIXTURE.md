# Source-loading 夹具

Node 专项使用 [harness.cjs](harness.cjs)，执行真实 HTML 所选的组件入口及 readable helpers，fetch/API/raw editor/time 受控。文件请求与 workId API 分别记录在 `requests`、`writes`，不需要运行服务或注入会话。

现有 [loopback server](../python-preview/server.py) 保留 PR52 的 workId/upload/register/submit 和失败模式，补充可复用 source 情境。另开服务时先选择未占用的本机端口，记录 PID，并在完成后关闭该进程。不要重启或关闭其他 Agent 已占用的服务。

```sh
python3 web/tests/python-preview/server.py --port <unused-loopback-port> --directory web/public
```

固定地址 `/fixtures/slow.py` 延迟 1200ms；`/fixtures/empty.py` 是有效的空程序；`/fixtures/html.py`、`/fixtures/json.py` 分别返回对应 MIME；不存在的 `/fixtures/missing.py` 返回 404。原 `/fixtures/seed.py?revision=1&label=a+b` 与保存后的 `/fixture/*.py` 保持原语义。

`POST /__mode` 使用 JSON `{ "mode": "..." }`：新增 `slow-source`、`source-404`、`source-error`、`source-once-error`、`source-html`、`source-json`、`source-empty`。`source-once-error` 在切换模式后第一条源文件请求返回 503，后续正常，适合验证 retry。切换模式会重置 source attempt 计数。`GET /__state` 的 `sourceReads` 记录完整 request URL、mode、attempt 和响应 status；旧 `reads` 仍只记录 workId metadata 请求。浏览器级断网由所属浏览器 probe 的 route abort 控制。

小型 [browser-probe.js](browser-probe.js) 只查找真实挂载的 PythonEditor 并返回源状态、raw 内容、只读状态、Run 按钮、entry script 和 frame 数量。服务通过 `/__source_loading_probe.js` 提供它。可在自己拥有的 Playwright CLI session 中加载脚本，并用 `return` 返回 `TeachingPythonSourceProbe.snapshot()`，避免使用只写 console 的方式误认为 CLI 已得到结果。它不代替测试断言，不修改编辑器，不设置认证。

Root 的完整 Chromium route/UI probe、保存重开脚本和截图已放在 `docs/optimization/evidence/python-source-loading/`。本轮没有再新建重复的浏览器矩阵。
