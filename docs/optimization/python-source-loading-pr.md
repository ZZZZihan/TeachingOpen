# Python 文件打开与失败恢复

本项基于 PR #52，处理编辑器和播放器的重复初始化、加载失败以及内容尚未就绪时仍能运行的问题。保留原有 Python 2 / Skulpt、Worker 执行隔离、作品编号和保存协议。

## 修复前实测

root 使用 PR #52 精确提交 `f906f8e782795ddd670725e85ffa4ea1756b665c`、真实 Chromium 页面及独立合成 HTTP 服务进行对照：编辑器与播放器各打开一个有效文件都发出两次 GET；不存在的文件也各发出两次 GET。播放器没有错误状态或重试入口，两入口的运行按钮在读取失败后仍可点击。播放器有两条未处理的 404 异常，编辑器有一条。

证据：[四种旧版场景](evidence/python-source-loading/baseline-browser.json)、[复现脚本](evidence/python-source-loading/baseline-probe.cjs)。旧版截图为 1280 CSS 像素宽：[播放器缺文件](evidence/python-source-loading/source-baseline-player-missing.png)、[编辑器缺文件](evidence/python-source-loading/source-baseline-index-missing.png)。全部使用自写程序或不存在的夹具路径，不含生产数据。

## 实现边界

两个 HTML 原先同时加载 `app.js` 和 `appPlayer.js`，即使没有对应挂载点，另一套组件也会执行文件读取。每页只保留自己的页面入口，共享文件加载、错误状态和重试机制。文件请求保留同源媒体 Cookie，不向文件服务发送 API JWT。

加载状态与真实编辑器内容就绪关联，等待期间禁止运行和提交。CodeMirror 原有的 300 毫秒延迟写入需要消除；默认 Ace 使用不同的更新方式，两者分别验证。空文件和同内容重试也不能仅凭初始字符串相等就提前宣布就绪。

保存接口、作品编号优先级、完整 URL 解码规则和 Worker 生命周期不在本项重写。默认示例程序保持原样；本次实读当前文件，没有复现前序记录中末尾 `ss` 的疑点。

## 最终验证

- 独立测试 Agent：新增源加载专项 **22/22**，连同历史 URL、bridge、output 专项 **71/71**，最后冻结后完整前端 **369/369**，无失败或跳过。检查覆盖超时及迟到结果、单次加载、重试、实际 raw editor 准备、空文件/同内容、CRLF、CodeMirror 同步 setter、workId 和保存身份、精确 bundle 回退链。[完整测试日志](evidence/python-source-loading/node-full.tap)、[专项日志](evidence/python-source-loading/node-specialized.tap)。这些是受控 VM/组件测试，不等同真实用户浏览器验收。
- root 实际 Chromium **154.0.8037.93**：两入口各七个功能场景，共 **14/14**，包括有效完整 URL、1200 毫秒慢读、404/断网后重试、非法 URL、返回 HTML、空文件；普通加载仅一次 GET，重试后共两次，均无未处理 pageerror。可编辑页面的空文件在输入后等待 550 毫秒，内容保持；播放器保持原有只读行为。失败由独立合成 HTTP 服务与浏览器路由控制，不操作生产。[最终浏览器结果](evidence/python-source-loading/browser-final.json)、[复现探针](evidence/python-source-loading/source-loading-root.cjs)。
- root 两入口各 **390/768/1440**：六组错误状态布局无横向溢出，重试入口可见、运行禁用。截图见下方；这不代表重新设计或验收整套编辑器。
- root 真实编辑器 UI：workId 优先于同时传入的另一个 URL；输入自写代码和名称并点击提交，只发生一次上传、一次登记、一次更新原 seed-work。重新加载后代码/名称一致，未新增作品，再运行输出 42，无 pageerror。[保存重开](evidence/python-source-loading/save-reopen.json)、[探针](evidence/python-source-loading/source-loading-save.cjs)。使用合成 HTTP 接口，未据此宣称真实 Java 认证或数据库保存验收。
- root 最终 `npm run build` 成功，Node 26.7.0 / npm 11.19.0，保留 **12 条既有 CSS 顺序与资源体积 warning**；17 个 Python 产物与源码逐字一致，独立服务的 17 个 HTTP 响应也一致。[构建摘要](evidence/python-source-loading/build-summary.log)、[最终源码摘要](evidence/python-source-loading/final-source-manifest.json)。无依赖升级。
- 另一 Agent 独立窄范围静态审查未发现本项阻断问题：两 bundle 每个四处替换精确逆重建 PR #52，旧执行/运行时七文件逐字未变；原补丁 manifest 未改，新增回退层单独记录。[独立审查](evidence/python-source-loading/review/REVIEW.md)。作者自检、独立测试、独立静态审查与 root 浏览器检查分别列证。

探索探针曾错误假定播放器允许编辑、并遗漏运行按钮可访问名称中的图标文字，均已按真实页面修正；最终结果采用完整成功的复测。错误文案最后只做了尾部标点和重复重试说明的整理，最终 20 场景已重新运行。保存重开在此文案调整前完成，保存与状态逻辑未变。

## 最终截图

播放器错误状态：[390](evidence/python-source-loading/source-final-player-error-390.png)、[768](evidence/python-source-loading/source-final-player-error-768.png)、[1440](evidence/python-source-loading/source-final-player-error-1440.png)。编辑器错误状态：[390](evidence/python-source-loading/source-final-index-error-390.png)、[768](evidence/python-source-loading/source-final-index-error-768.png)、[1440](evidence/python-source-loading/source-final-index-error-1440.png)。[保存后重开](evidence/python-source-loading/source-final-save-reopen.png)。

## 兼容性与剩余范围

文件加载期限从编辑器原来的 60 秒收紧为共同的 15 秒，超时显示原因并可重试；作品信息及保存接口期限沿用原值。需要支持 Fetch 与 AbortController 的浏览器，不具备时给出可理解的错误。默认页面仍用 Ace，CodeMirror 可选路径由受控测试和静态审查覆盖，本轮未做真实 CodeMirror 页面验收。浏览器实际验证只覆盖上面的 Chromium 版本；此前 PR #52 的其他浏览器证据没有重复计为本轮通过。

更完整的认证三角色流程、真实后端保存、用户视觉评阅和生产验收仍分别保留状态。组合候选在产品化计划中单独验证与登记；本项没有 GitHub 合并或生产部署。
