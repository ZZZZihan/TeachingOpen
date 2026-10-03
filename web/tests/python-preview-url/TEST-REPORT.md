# Python 预览 URL 专项测试记录

2026-10-03，在 `fix/python-preview-url` 的工作树执行。基础提交为
`6ee37a8b974373536748dbef9128814287f2dede`，Node 为 `v26.7.0`。

专项测试共 33 项。相同测试源码在基础提交上为 4 项通过、29 项失败；
当前候选为 33 项通过、0 项失败。`base-red.json` 与 `candidate-green.json`
记录产品文件和测试源码的 SHA-256，两个报告的测试源码哈希一致。
对应 TAP 文件保留实际断言失败和通过结果。

旧代码的实际失败包括：教师、课程生成的完整外层编码地址仍以
`https%3A%2F%2F...` 交给播放器；社区裸拼地址在嵌套 `&` 处被截断。
两个预编译组件的旧查询方法均出现编码地址未还原的失败。

测试从 `appPlayer.js` 和 `app.js` 的实际 `PythonEditor` 对象执行查询方法、
生命周期、下载方法和向 Ace 写入代码的方法；教师、课程、社区链接由各自的
实际 SFC 方法生成。测试没有复制产品的解析算法。
`appPlayer.mounted` 和没有持久化桥接时的 `app.created` 均被执行。

覆盖的契约包括：

- 三个现代入口明确使用 `queryEncoding=uri`，只解码外层查询一次。
- 嵌套 `&`、文件自身的 `+`、空格、中文、`%`、`#` 和相对地址保持完整。
- 文件自身的 `%2F`、`%26`、`%25` 和 `%2526` 不被再次解码。
- 无标记的旧 HTTP(S)、`/`、`./`、`../` 和普通相对路径保留 `%` 与 `+`。
- 已整段编码且有可识别地址前缀的旧链接兼容一次解码。
- 重复 `url` 取第一项；空值或缺失保持 `0`，播放器不下载，旧编辑器仍读取原默认示例。
- 页面 fragment 中的伪 `url` 不作为查询参数；不完整百分号不抛异常。
- 两个 HTML 入口在 bundle 前加载真实查询 helper；共享 helper 的 `workFile`、名称和 ID 行为有回归检查。

适用的已有 Python 输出、持久化、桥接、教师工作台和课程阅读器测试实际运行
56 项，全部通过。随后在 `web/` 执行完整 `npm test`，318 项全部通过，
没有取消、跳过或待办测试；完整输出保存在 `full-suite.log`。

预编译补丁验证保留原输出补丁的历史基线。测试先逆向回滚本次 URL manifest
的两个单项替换，再逆向回滚原六个输出替换，继续比对原记录的 SHA-256，
没有更换旧基线哈希。

候选 bundle SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `web/public/python/static/js/app.js` | `81254a2410f3788f86f6981265502cd62643d54169ad5400a666745faf3af80a` |
| `web/public/python/static/js/appPlayer.js` | `c58d3cbc733d294f56413d3f5d5a41c7c409474f22bda74eeb0ba9b1d3bf7ba9` |

可重现命令，在仓库根目录执行：

```sh
node web/tests/python-preview-url/run-report.cjs --ref 6ee37a8b974373536748dbef9128814287f2dede --output web/tests/python-preview-url/base-red.json
node web/tests/python-preview-url/run-report.cjs --output web/tests/python-preview-url/candidate-green.json
node --test web/tests/python-output.test.cjs web/tests/python-persistence.test.cjs web/tests/python-bridge.test.cjs web/tests/teacher-workbench.test.cjs web/tests/learning-reader.test.cjs
```

完整项目检查在 `web/` 执行 `npm test`。

浏览器复现可以复用已有 `web/tests/python-preview/server.py` 的合成端点
`/fixtures/seed.py?revision=1&label=a+b`。在明确由当前任务拥有的 loopback
端口启动该既有夹具后，以下命令通过三个真实 SFC 方法生成地址：

```sh
node web/tests/python-preview-url/links.cjs http://127.0.0.1:18154
```

本测试工作没有启动服务、操作已有 runtime、登录、提交或推送。
这里的 Node VM 检查与合成 HTTP 夹具不是实际 Java 后端验证、真实角色验收或
人工验收；浏览器证据由主 Agent 另行核对。本次不涉及 Python 执行隔离。
