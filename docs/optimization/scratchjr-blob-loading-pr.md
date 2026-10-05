# 本地 ScratchJr 项目 Blob 加载

2026-10-05。分支 `fix/scratchjr-blob-loading-delivery`，基线为 GitHub `fix/local-proxy-head` 的 `dc4c398a8559efa5eef46280305242156cc7ae61`。产品改动仅为 `api/dev/serve-frontend.py` 的页面响应头。

真实认证课程入口打开 ScratchJr 时，外层已取得模板字节并创建子引擎，但直到 60 秒后仍未收到就绪回调，最终显示读取超时并保持保存禁用。对当前候选 18150 的引擎页面执行无身份 HEAD，确认其 CSP 为显式 `connect-src 'self'`，见 [响应摘要](evidence/scratchjr-blob-loading/baseline-engine-head.txt)。

外层 `editor-bridge.js` 将服务器文件变成 Blob URL，再将该地址作为 `workFile` 传给同源 `engine.html`。继承引擎的 `downloadProject` 使用 XHR 读取这个地址，但显式 `connect-src` 没有 `blob:`；`default-src` 中的 `blob:` 不能补足连接许可。原加载代码仅处理 status 200/404，没有 XHR 错误回调，因此这一阻断最终由外层超时保护报告。

模板与以前实际编辑成功的 `scratchjr-preview/sample.sjr` 均为 679 bytes，SHA-256 `3db97173b9436df3ce8deacacbf3dd46ac60467044ea1650b14f7d250bf88147`，是相同的自制空白单页项目及 PNG 缩略图。此前样本 HTTP 服务已允许 `connect-src 'self' blob: data:`。两份部署 nginx 配置没有显式 `connect-src` 且默认来源含 `blob:`，本次不需要修改部署配置或模板。

修复只对路径精确等于 `/scratchjr/engine.html` 的响应输出 `connect-src 'self' blob:`，包含查询参数的编辑/预览地址均适用。其他静态页、外层 editor、SPA、API 和 WebSocket 保持 `'self'` 连接来源；脚本、Worker、样式及默认来源指令完全保留。没有修改登录、业务 API、原始引擎、文件内容或依赖。

作者检查：

- 先加入真实 HTTP 响应头检查而保留旧服务器实现：2 项新检查中，许可边界检查通过，引擎页面的 GET/HEAD、含/不含查询共 4 个断言因缺少 Blob 连接许可失败，见 [旧实现结果](evidence/scratchjr-blob-loading/red-headers.log)。
- 修复后代理检查 **22/22** 通过，见 [代理结果](evidence/scratchjr-blob-loading/green-headers.log)。新检查读取临时 loopback HTTP 服务器的实际响应，不复制服务器内部策略作为期望；断言单一 CSP、完整保留来源集合、精确路径与查询处理，外层 editor/其他页面/相似文件名/API 的查询内容不能获得 Blob 许可。既有鉴权头传递、HEAD、WebSocket、错误响应和 TCP 流检查继续通过。
- 交付基线的 Python 总回归执行 **108 项：107 通过、1 按既有专用快照 runtime 条件跳过**，见 [完整结果](evidence/scratchjr-blob-loading/full-python.log)。此任务未配置 `TEACHING_SNAPSHOT_TEST_RUNTIME`，没有把跳过计为通过。
- 两个 Python 文件的语法检查及 `git diff --check` 通过。[验证摘要](evidence/scratchjr-blob-loading/validation.json) 记录计数、基线与产品文件哈希。

```sh
python3 -m unittest discover -s api/dev -p 'test_frontend_proxy.py' -v
python3 -m unittest discover -s api/dev -p 'test_*.py'
python3 -m py_compile api/dev/serve-frontend.py api/dev/test_frontend_proxy.py
```

上述是作者受控 HTTP/TCP 和 Python 检查，没有在本任务操作浏览器、读取身份凭据、切换现有 runtime 或重新构建前端/JAR。真实认证课程从加载到实际编辑、保存、重开的 DOM 回归由主 Agent 执行；本文不将响应头通过称为该流程完成。独立审查、人工验收、合并及生产部署分别保留为后续状态。
