# Python 源文件加载：作者说明

本候选建立于 PR52 的 `f906f8e782795ddd670725e85ffa4ea1756b665c`，改动范围是 Python 编辑器与播放器打开源文件的可靠性。实际浏览器基线记录显示两个入口的有效文件与 404 文件均收到两次 GET；播放器缺少可理解的状态与重试，两页加载失败时仍可点击运行。

两个 HTML 原先同时装载 `appPlayer.js` 和 `app.js`，分别执行两套 Vue 入口与组件生命周期。现在编辑器只装载 `app.js`，播放器只装载 `appPlayer.js`。Worker 的原版模块注册流程不执行 Vue 入口，沿用 PR52 的实现；本候选没有修改执行协调器、renderer host、Worker、turtle 桥或模块加载器。

编辑器的作品初始化仍由 `editor-bridge.js` 与 `PythonPersistence` 管理：已有 `workId` 先取得作品信息，再读取作品文件；新作品或模板沿用原参数及默认模板选择。保存、登记、提交和重开的上下文及认证协议保持原有实现。bridge 同一页面的重复 mount 不重复创建会话、请求、watcher 或离页监听。

新增可读 `source-loading.js` 统一源文件读取。请求只发一次 GET，保留完整 URL 的查询、百分号转义、加号和片段，沿用已有 query parser；仅接受 HTTP/HTTPS 地址，拒绝嵌入账号和控制字符。文件请求使用 `credentials: 'same-origin'` 保留本域媒体 cookie，不发送 API JWT，也不向跨域文件主机传递凭据。十五秒没有完成会中止请求并拒绝后续迟到结果；404、权限、超时、网络、HTML/JSON 内容及超过 10 MB 文件有明确反馈。

播放器缺少或空的 `url` 参数时显示没有指定程序文件，不执行隐藏的默认模板请求。`persistence-status` 提供加载中、已打开、失败状态，`retry-load` 重新加载同一源地址。编辑器沿用原工作区状态与重试。两组件都在方法入口和运行按钮上核对 ready/busy，不能在文件尚未打开或应用完成前误运行。

读取开始时记录实际编辑器内容，编辑器另记录作品名称。在应用之前再次核对快照，内容发生变化便保留当前内容并显示失败。加载与保存期间同时锁定 Ace 和 CodeMirror；应用等待真实编辑器就绪，最长两秒。源文件直接同步写入真实编辑器，再同步包装组件与父组件内容，跨一次 Vue 渲染核对三者一致。CRLF 或混合换行按真实编辑器的 LF 表示核对，已保存快照也取实际内容，避免打开后立即误判为未保存修改。

原 CodeMirror `setCodeContent` 使用不可取消的 300 毫秒定时器。仅等待 `getValue` 等于目标会在空文件或同内容重试时提前完成，旧定时器可能覆盖随后编辑。因此两个 bundle 的该 setter 精确替换为同步状态和 `coder.setValue`；源加载器本身不使用旧包装 setter。`PythonPersistence.load` 等待 apply Promise，并在应用后再次检查加载版本；bridge 检查挂载对象仍然有效。

预编译改动的原文、替换文和前后 SHA-256 记录于 `web/tests/python-source-loading/vendor-patch.json`。逆替换应精确恢复 `f906f8e`，再按既有 execution、output、URL、persistence 补丁链回退；旧 manifest 保持独立。本候选未升级 Python/Skulpt，不改默认程序。当前工作树实际默认模板末尾是 `print ("Teaching Python Editor")`，没有发现待混修的 `ss`。

作者完成语法、差异检查、bundle 精确逆重建与 PR52 执行文件逐字一致检查。独立测试、实际浏览器、保存重开、构建和交付证据由对应报告记录；这些级别分别表述，不由实现完成推断人工验收或生产部署。
