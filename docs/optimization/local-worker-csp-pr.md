# 本机 Scratch Worker 的 CSP 修复

日期：2026-10-03。基于 PR #47 的 `b7a7d788734315c8cdb183e4f79b2853198b4018`，分支 `fix/local-worker-csp`。

本机 `serve-frontend.py` 的 CSP 已显式设置 `script-src`，却没有 `worker-src`。Scratch 创建的 `blob:` Worker 因而使用 `script-src` 的来源限制；`default-src` 中的 `blob:` 不能越过这个回退顺序。依据 [W3C CSP3 的 Worker 来源定义](https://www.w3.org/TR/CSP3/#directive-worker-src)及[回退列表](https://www.w3.org/TR/CSP3/#directive-fallback-list)。

本项只在本机响应头增加 `worker-src 'self' blob:`，允许同源和 Blob Worker。普通脚本的 `script-src` 和网络连接的 `connect-src` 保持原值，远程来源继续受限；没有调整生产代理、全局配置、Java 或前端业务代码。

作者检查结果：

- 原代理检查 12/12 通过；先加入响应头检查而保留旧服务器代码，13 项中 3 项因缺少 `worker-src` 失败，其他 10 项通过。修复后代理检查 13/13 通过。
- 检查通过临时 loopback HTTP 服务器读取真实静态页面、SPA、API、404、502 及 WebSocket 101 的响应头。要求只输出一个 CSP 头、指令无重复，Worker 来源精确为 `'self' blob:`，普通脚本及连接来源保持原边界。断言没有引用服务器内的策略字符串。
- 既有实际 TCP 夹具继续检查首帧保留、二进制/control-frame 字节保真、1 MiB 流和并发连接、双向断开、空闲清理、非法握手与 Origin、上游拒绝/损坏/超大/超时、故障恢复、重复 Cookie 和分段 POST。它们是受控后端测试，不是 Java 业务或浏览器验收。
- Python 总回归执行 99 项，98 项通过，1 项按既有 `TEACHING_SNAPSHOT_TEST_RUNTIME` 要求跳过；本轮未指定专用数据库快照测试环境。`git diff --check` 通过。

复跑入口：

```sh
python3 -m unittest discover -s api/dev -p 'test_frontend_proxy.py' -v
python3 -m unittest discover -s api/dev -p 'test_*.py'
```

主 Agent 实际浏览器对照（匿名 Chromium，最终相同 dist）：

- 旧策略 18150：实际 Scratch Blob Worker 产生 1 个错误、0 条消息，并捕获 `worker-src`/`blob` 违规；简单默认项目由原回退继续显示。新策略 18151：同一页面实际 Blob Worker 收到 `support.fetch=true`，1 条消息、0 Worker 错误、无策略违规，编辑器就绪并保留两个 Canvas。
- 实际应用启动只证明 Worker 能启动，默认项目未观测到 Worker 素材请求。另用交付包原样的 `1ec1a83be92ce3c05727.worker.js` 分别创建同源和 Blob Worker，通过其真实消息协议读取同一 SVG。两者均返回 1,229 bytes，SHA-256 均为 `93a43578b1a5aee04906c0bb229729d32674c83fe6d322683e22662ae6aeedfb`，与页面直接读取及资产一致。
- 普通 Blob script、另一 loopback 来源的 script/fetch、data Worker 均被阻断，分别收到 `script-src-elem`、`connect-src`、`worker-src` 违规事件；Blob 脚本标记未执行。此处用本机不同端口检查跨来源限制，没有访问外网。故意拒绝探针会产生控制台错误，不称零错误。
- [机器可读结果](evidence/local-worker-csp/browser-result.json) 和两份实际执行的浏览器探针保留完整步骤。探针经 Playwright CLI `run-code --filename` 执行。`compare-browser.cjs` 的旧/新端口对应对照时的两个进程，切换候选后重跑须另启动旧版本。

独立审查 Agent 在冻结代码上只读检查来源范围和断言，另行执行 13/13 代理测试（8.857s，exit 0）与 `git diff --check`，未见阻断；核心文件 SHA 与作者冻结相同。开发、独立检查均使用用户指定 GPT-6.1-sol / Ultra；工具没有单独 Fast 参数，未声称配置。

本次没有 Java/前端业务代码、依赖或布局变化，无需重新构建既有前端和 JAR；没有新的视觉验收。匿名 Worker 检查不替代认证保存/重开、复杂项目或性能验收。上游若另外输出 CSP，多条策略会叠加；受控代理后端未覆盖该情形，实际本机页面使用所记录单策略。没有修改生产服务。
