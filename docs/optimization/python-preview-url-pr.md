# Python 预览地址：标准编码与旧链接兼容

基于 `fix/course-summary-text` 的 `6ee37a8b974373536748dbef9128814287f2dede`（PR #46），独立分支 `fix/python-preview-url`。本记录对应本机候选修复；PR 交付状态另由根任务记录，合并和部署不由本项自动执行。

教师作品预览和课程案例已经用 `URLSearchParams` 编码文件地址，旧播放器却通过正则取出原始参数值。实际 Chromium 打开编码后的本机文件链接时，浏览器请求了 `/python/http%3A%2F%2F...`，返回 404，编辑区域没有显示目标代码。社区作品页直接拼接文件地址，文件自身的 `&` 则被当成外层参数分隔符，地址被截断。旧浏览器请求、控制台和截图保存在 [旧浏览器结果](evidence/python-preview-url/old-browser-result.json)、[旧服务日志](evidence/python-preview-url/old-fixture.log) 和 [旧页面截图](evidence/python-preview-url/old-player.png)。

现在三个 Python 预览调用方都使用完整的外层编码，并显式传递 `queryEncoding=uri`。课程案例原本就有这个标记，无需修改。播放器复用现有 `PythonPersistence.query`，标准参数由 `URLSearchParams` 解码一次，文件地址自身的百分号转义、中文、空格、加号、嵌套查询和片段都保留下来。例如 `url` 解码后仍包含 `a%2Fb.py?label=a+b&revision=1`，不会再对 `%2F` 或文件查询中的 `+` 解码。

`player.html` 原来同时加载 `appPlayer.js` 和 `app.js`：前者在 `mounted` 下载，后者在没有编辑器桥接时在 `created` 下载，两份组件都使用旧参数方法。本次对两份预编译文件各替换一处 `urlParam`，均委托给同一个实际解析函数。播放器页面在两份 bundle 前加载现有 `persistence.js`；它只定义函数，不创建保存会话、挂接编辑器或发起网络请求。两次既有下载的生命周期保留，两条路径都受回归检查覆盖。

无 `queryEncoding=uri` 的旧文件链接按以下兼容规则处理：

- 原始 HTTP/HTTPS、`/`、`./`、`../` 路径保留 `%` 和 `+`，例如 `/fixtures/a%2Fb+100%25.py?label=a+b` 不会指向另一个文件。
- 其他值尝试一次 `decodeURIComponent`，只在结果具有上述已知地址前缀时采用解码值，因此整段编码的旧绝对地址和明确的相对地址仍可打开。
- 未识别的裸相对值保持字面值，不推测 `fixtures/a%2Fb+100%25.py` 中的字符属于外层编码还是文件路径。新入口的标记消除了这种歧义。
- 缺失、空值及现有解析器的 `undefined`、`null` 值使用既有空值结果；播放器参数方法返回 `0`。重复 `url` 取首个值。播放器没有地址时不请求文件；另一份旧组件仍按原生命周期读取默认示例。
- 旧链接若未编码文件地址中的 `&`，无法无歧义判断它属于文件查询还是外层参数，本次不拼接猜测。旧地址也不能直接把文件片段 `#` 写成外层片段；需要由当前调用方完整编码。

共享解析器仅调整旧 `url`/`workFile` 的识别分支，其他名称、编号、场景参数沿用原解析逻辑。下载仍使用两份组件原有的 Axios `get`；本次没有修改请求头、凭据、媒体 Cookie、协议处理、保存接口或后端。外部文件主机的 CORS、私有资源的既有鉴权要求仍适用。

预编译补丁见 [vendor-patch.json](../../web/tests/python-preview-url/vendor-patch.json)：记录基线提交、两个文件修改前后的 SHA-256 及各自唯一的前后片段。新增回归首先还原本次 URL 替换，再还原原输出区的六处替换，继续核对历史基线哈希；未覆盖或改写旧输出补丁的摘要。两个 bundle 中的 Skulpt、Python 语言语义、执行路径和依赖均不属于本次变更。

## 已执行的检查

产品编码和专项测试由不同 Agent 并行执行，以下是工程检查，不是师生人工验收或独立后端认证验收。

- 专项测试直接执行三个实际 SFC 调用方和两份实际预编译组件的解析、初始化、Axios 下载及 Ace 设置代码的方法。冻结的同一套 33 项检查在旧提交为 4 通过、29 失败，候选为 33/33 通过。证据见 [基线报告](../../web/tests/python-preview-url/base-red.json) 和 [候选报告](../../web/tests/python-preview-url/candidate-green.json)。
- `npm test --prefix web`：318/318 通过；适用的已有 Python、教师预览和课程阅读器检查为 56/56 通过。它们运行在受控 Node VM/接口替身中，没有登录真实 Java 后端。原输出区补丁链的历史哈希检查继续通过。
- `npm run lint:changed --prefix web` 通过；教师预览组件显式 ESLint 为 0 error / 0 warning。`WorkDetail.vue` 显式检查的基线为 34 error / 165 warning，候选为 33 error / 165 warning，未新增诊断，文件末尾换行消除一条既有错误。`persistence.js` 基线为 16 error / 82 warning，候选为 16 error / 88 warning；新增代码沿用原文件缩进，增加六条同类缩进 warning，没有新增 error。没有把这两个文件的全量显式 lint 记为通过，也没有混入全文件格式重写。
- `npm run build --prefix web` 返回 0，生产构建成功，报告 12 条 CSS 顺序/资源体积警告，另有旧 `caniuse-lite` 数据提示。本次复用其他本机工作树已安装的 `node_modules`，没有安装或升级依赖。使用 Node `26.7.0`。
- 本次修改的四份 Python 静态入口/脚本在源码和 `dist` 中 SHA-256 相同：`player.html`、`persistence.js`、`app.js`、`appPlayer.js`。`git diff --check` 通过。
- 主 Agent 使用真实 Chromium，分别打开由教师、课程案例、社区三个实际 SFC 生成的候选链接；真实播放器的两个组件都 GET 完整正确地址并返回 200，保留 `revision=1&label=a+b`。实际 Skulpt 运行显示 `Python persistence fixture` 和 `42`，清空后输出为空，重跑得到相同输出，`pageErrors=[]`。旧编码链接请求错误相对路径并返回两次 404；旧原始简单文件路径作为控制可正常运行输出 `42`。结果和探针保存在 [候选浏览器结果](evidence/python-preview-url/browser-result.json) 及同一证据目录。本次没有重新布局界面。

独立只读审查由第三位 Agent 完成：实际执行本次专项及既有 Python 持久化、桥接、输出四个测试文件，共 60/60 通过；`git diff --check` 通过。另从 `6ee37a8` 按 manifest 顺向重建两个 bundle，每个文件唯一一处替换，重建结果与候选完整字节一致，未见本轮阻断。无标记且整段编码的裸相对地址保持字面值，是上述明确的兼容边界；当前实际调用方未发现使用该形式。编码、测试和独立审查均使用用户指定的 GPT-6.1-sol / Ultra；工具没有单独 Fast 配置参数。

可重复的核心检查：

```sh
node --test web/tests/python-preview-url.test.cjs
npm test --prefix web
npm run lint:changed --prefix web
npm run build --prefix web
```

真实浏览器核查使用本机合成 HTTP 文件服务，没有 Java 后端、真实登录或账号权限验收。浏览器服务读取本分支的 `web/public`，四份修改的 Python 文件与构建产物字节一致。实际页面运行和 Node 组件检查是分别执行的证据，不能合并称为已登录浏览器端到端验收。

## 剩余事项

继承的页面仍有双组件初始化与两次文件下载；本次仅保证参数地址一致，不调整挂载结构。下载失败的可见反馈仍沿用旧播放器行为。缺失 Python 源工程、同源 Skulpt 的 `jseval` 能力、执行超时/取消和无限执行隔离仍是后续工作。本次参数修复没有提供不可信代码沙箱，也没有更改 Python 2 语义。真实账号浏览器验收、生产存储/CORS、人工验收及发布需要分别完成。
