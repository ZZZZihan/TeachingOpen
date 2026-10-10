# Python 源文件加载候选：独立窄范围静态审查

本次审查没有发现需要阻断产品冻结的问题。审查对象是 `fix/python-source-loading` 工作树当时的八个产品文件；基线是 PR52 的 `f906f8e782795ddd670725e85ffa4ea1756b665c`。文件 SHA-256、八个产品文件与七个原执行/运行时文件的对照、bundle 逆重建结果都在 `final-product-manifest.json`。这是固定文件的独立静态审查，不代替 root 的实际浏览器、保存重开、构建或部署验证。

1. `source-loading.js:73–103` 先等真实 Ace.editor/CodeMirror.coder 具备 getter/setter，最多等待两秒；写入前检查 live host 与内容 guard，同步调用真实 setter，并同步 ref.code/hasCode/host.code。随后跨一次 Vue nextTick 同时核对真实编辑器、包装 getter 与 host.code。这条路径没有调用遗留包装 setter。空文件或同内容重试不会因为旧值已经相等而跳过真正的应用，也不会留下本次 source apply 的延迟 setter。

2. 两个 bundle 的 JCode `setCodeContent` 均把原先不可取消的 300ms timer 替换成同步 code 与 coder.setValue。每个 bundle 只有 manifest 记录的四处替换；逐处逆替换能够逐字恢复 PR52 基线，前后 hash 与作者 manifest 一致。真实页面默认仍然是 Ace；CodeMirror 是保留的可选组件，因此本次不把其基线风险描述成已经发生的默认页面失败。

3. 源码 CRLF/CR 经 LF 归一化后写入，跨 tick 比较也按相同规则；`editor-bridge.js` 的 snapshot/savedSnapshot 从 `Source.contents` 取实际编辑器内容。由此不会把读取文本的原始换行表示与编辑器 getter 的规范表示混为不同作品。source apply 同步写实际内容及包装、父组件状态，并没有依赖旧 Ace outer setter 的异步 value watcher 才完成内容应用。

4. `editor-bridge.js` 在 loading 通知时保存名称和真实内容快照；调用 apply 之前及等真实编辑器准备后再次检查 unchanged。apply 完成后再次检查 host identity 与 `_isDestroyed`，此后才改作品名称和保存快照。`PythonPersistence.load` 现在 await apply，并在 Promise 完成后检查加载版本，busy 覆盖获取和应用整个阶段；同步返回 undefined 的 apply 调用方仍兼容 await。源码读取超时的 settled guard 阻止迟到成功进入应用，retry 在 busy 期间不产生第二次 load。

5. 加载和保存期间 bridge 同时设置 Ace/Coder readOnly，原 title/open/submit 状态门控保留；两组件的 Run 方法和按钮新增 ready/busy 门控。播放器初始化状态为 sourceBusy=true/sourceReady=false；编辑器初始状态沿用 bridge 状态。播放器没有 url 时进入明确的 load-error，不再调用被额外挂载 app 的默认下载。当前两个 HTML 都只载自身 Vue bundle，源码读取实际由共同 helper 单一路径管理。

6. `PythonPersistence.query` 完全未变；已有 workId 仍先取 canonical work 信息，以 `workFileKey_url` 读取，并恢复 courseId/additionalId/departId，resetTemplate=1 的既有例外保持。保存 id/类型/上下文、登记/提交和 workId URL 更新不变。文件读取使用完整 URL 与同源 cookie，不设置 API JWT 请求头，跨域 credentials 为 same-origin。此次 bridge 读取超时从原 60s 改成共同 helper 的 15s，是作者明确记录的加载行为变化。

7. `execution.js`、`runner.js`、`runner-loader.js`、`worker.js`、`worker-turtle.js`、`static/js/vendor.js`、`static/js/manifest.js` 七个文件逐字与 PR52 基线相同。runner-loader 原本只注册 bundle 模块并读取固定 Skulpt 模块，不执行 Vue entry；本次组件入口改动没有加入 Worker 的执行路径，也没有升级 Python2/Skulpt 或 turtle 适配。

作者最后一处 `persistence.js` 文案调整仅处理错误信息尾标点和重复重试提示；其最终 SHA-256 为 `a41c51846744be8532d98c2ce449d219dd985b24c464fd62abdda45a36180ab3`。该 diff 未修改请求、保存或 ready/busy 状态的语义。

证据边界：只读查阅与精确 bundle 逆重建；未运行浏览器、服务或完整测试，也未修改产品文件。首轮准备关注点保留在 `FOCUS.md`，基线文件和定位摘录保留在同目录。最终 manifest 的时间代表这份静态快照，若后续产品 bytes 变化，应对变化文件补审；未把作者陈述的运行结果当作本次独立实测。
