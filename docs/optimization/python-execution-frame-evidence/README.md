2026-10-03 的冻结候选通过 Node 专项 **72/72**、全量 `web/tests` **347/347**。
两次记录的产品 SHA-256 完全相同，执行前后产品文件没有变化；具体文件哈希、Node
版本、命令、退出码和测试源码哈希见相邻 JSON，逐项结果见相邻 TAP。

专项由真实组件与父层/可信 host 的 20 项、真实 Worker/海龟的 9 项、既有输出的
10 项和 URL 的 33 项组成。已有补丁链按 execution → URL → output 逐级反转，
保留原始 vendor 基线哈希，没有将新文件当成历史基线。

验证实际预编译组件的 `runit`/`clear` 调用当前代码、私有 MessageChannel 握手和
消息字段校验、Stop 调用 `Worker.terminate()` 后关闭结果通道并等待 2500ms、
旧停止确认前只保留最新 Run、无确认时保留旧 host 并允许重试、输入等待与计时、
输出纯文本及上限。父层回调覆盖独立 30 秒预算、重叠共享预算、输入暂停、主程序
在回调输入期间完成、结束后空闲不误超时和回调数量限制。

Worker/renderer 测试分别加载真正的旧 Skulpt、固定 loader、Worker entry、海龟
proxy 和原海龟引擎。有限 Python 2 程序验证输入等待 60 秒后 `Sk.execStart` 补偿、
主程序结束 40 秒后的回调再输入 60 秒并继续绘图、序列化与 kwargs、原对象包装
行为、明确启用撤销缓存后的 undo、timer 回调与 dispose、错误可被 Python 捕获、
队列限制和 thenable 兼容。圆弧 720/721 派生步数与低速移动文字使用原方法入口
计数验证前置限制，巨大旧引擎动画链没有运行。

DOM、transport、timer 和 Canvas 表面由夹具控制；Canvas 不生成真实像素。这些
结果不证明浏览器调度、实际 CPU 死亡、跨浏览器一致性、生产部署或人工验收。
实际浏览器的 500ms 探针只测父页面响应与停止生命周期；Worker 的最终 CPU 退出
需外部有界长程序与不停止对照。原 iframe 失败及过渡诊断见测试目录的
`IFRAME-PROTOTYPE-NOTES.md`，原日志保存在本机私有证据目录，未删除或改写。

在项目根复现：

```sh
node web/tests/python-execution-frame/run-report.cjs --output /tmp/python-frame-specialized.json
node web/tests/python-execution-frame/run-report.cjs --all --output /tmp/python-frame-full-suite.json
```

复用已有项目依赖；本次没有安装、升级、登录、真实 API 写入、提交或推送。浏览器
probe 的准备与受控 Node 执行分别记录，实际浏览器测试由主任务持有证据。
