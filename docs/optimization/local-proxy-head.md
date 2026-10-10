# 本机同源代理 HEAD 行为修复

日期：2026-10-03。分支 `fix/local-proxy-head`，基线 `a60d2b4`（`fix/local-worker-csp`）。本项产品改动限于 `api/dev/serve-frontend.py`；回归位于 `api/dev/test_frontend_proxy.py`。

原代理只有 GET 的 API 路由和 SPA 回退。HEAD 继承文件服务器，因此请求存在的 API 媒体时返回本地文件 404，无后缀 SPA 路由也返回 404。直接给 HEAD 接上原 API 方法仍会将无正文响应的 `Content-Length` 重算为 0。

修复为 API HEAD 转发原方法、路径及既有请求头；响应保留上游 `Content-Length` 或其省略状态，继续传递 `Content-Range`、媒体类型、缓存元数据及重复 Cookie。HEAD 不读取上游正文，也不向客户端写正文。静态路径和 SPA 回退移入 GET/HEAD 共用的 `send_head`，由原文件服务器保留目录重定向、条件响应和错误处理。

HEAD 的响应不能带正文；如输出 `Content-Length`，其值应描述相应 GET 表示的长度。实现依据 [RFC 9110 §9.3.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.2) 和 [§8.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.6)，静态处理沿用 [Python SimpleHTTPRequestHandler](https://docs.python.org/3/library/http.server.html#http.server.SimpleHTTPRequestHandler.do_HEAD)。

作者检查结果如下；命令、退出码、文件摘要及原始日志见 [证据清单](evidence/local-proxy-head/author-manifest.json)。

- 原有代理检查 13/13 通过。以基线 `a60d2b4` 的服务器和最终冻结的同一测试文件运行 20 项，出现 13 个失败断言，涉及 6 个测试方法；其余 14 个方法通过，退出码 1。新增用例没有将子用例数量写作测试方法数量。
- 候选代理检查 20/20 通过，耗时 9.274 秒、退出码 0。新增 7 个方法覆盖：中文转义 API 路径和 query、真实 HEAD 方法到达上游、合成鉴权头及 `Accept-Encoding: identity`、200 长度和缓存头、上游 206/416 的 Range 元数据、省略长度的 200/204/304、304 的正表示长度与合法零长度、401/403/404、代理生成的 400/502、静态文件/中文文件/SPA/目录重定向，以及静态 304/404。Range 夹具返回预设状态与头，只验证上游元数据透明保留。
- HEAD 正文检查直接读取 TCP 到 EOF，实际断言线上正文为零字节；通用 HTTP 客户端会自行忽略 HEAD 正文，不能单独证明服务器没有写正文。相应 GET 对照仍读取完整字节，并核对表示头。既有 WebSocket、1 MiB 流和并发、断开/空闲/握手故障、CSP、重复 Cookie 和分段 POST 检查继续执行。
- 完整 `api/dev` 检查执行 106 项，105 项通过、1 项按原有规则跳过，耗时 9.576 秒、退出码 0。跳过项需要 `TEACHING_SNAPSHOT_TEST_RUNTIME`；本轮该环境变量未设置。`py_compile` 和 `git diff --check` 均退出 0。
- 首次候选运行为代理 20 项中的 1 个 error、完整检查 106 项中的 1 个 error 和 1 个 skip。故障夹具的已绑定未监听端口在本机等待连接超时，探针的 2 秒期限先到。仅该用例将实际 urllib 上游连接的等待期限限定为 0.2 秒后，重新运行相同基线和候选；仍经过真实 TCP 连接失败及代理 502 分支。产品的 30 秒超时未修改。两份首次失败日志保留在公共证据中。

复跑时在仓库根目录执行：

```sh
python3 -m unittest discover -s api/dev -p 'test_frontend_proxy.py' -v
python3 -m unittest discover -s api/dev -p 'test_*.py'
python3 -m py_compile api/dev/serve-frontend.py api/dev/test_frontend_proxy.py
git diff --check
```

基线对照使用从 `git show a60d2b4:api/dev/serve-frontend.py` 提取的私有副本，与最终测试文件逐字节相同，避免改动候选工作树。测试只创建临时目录和随机 loopback 端口。本作者没有操作既有 runtime 或任何固定 181xx 服务，未修改 Java、JAR、业务页面或其他代理，没有提交、推送、建立 PR 或生产部署。

本记录是作者工程自检；独立 Agent 审查、真实 Java 后端的媒体/鉴权/Range/通知 WebSocket 联调与发布判断由主 Agent 单独记录。既有普通响应的内存缓冲方式及上游元数据过滤规则保持本轮范围；测试不提供生产代理、流式大文件或容量结论。作者使用用户指定 GPT-6.1-sol / ultra；工具没有独立 Fast 参数，未声称启用该参数。
