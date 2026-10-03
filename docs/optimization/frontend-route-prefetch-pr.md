# 按实际导航加载异步页面资源

## 问题与最终行为

当前单页应用使用 Vue CLI 的默认 `prefetch` 插件。安装的
`@vue/cli-service/lib/config/app.js` 将其配置为 `include: 'asyncChunks'`，
因此生产首页 HTML 包含所有异步分块的资源预取提示。用户只访问首页，也会让浏览器
在空闲时请求未访问页面的 JS 和 CSS。

本项仅在 `web/vue.config.js` 的 `chainWebpack` 中删除 `prefetch` 插件。
默认 `preload` 插件仍使用 `include: 'initial'`，路由动态 `import()` 和分块配置保留。
异步页面资源在实际访问时加载，首次导航可能需要等待尚未下载的页面分块。

## 作者验证

对照基线为 `fix/python-preview-url` 的 `85f8a7d0a995047feb8ce486224d7bf991878e62`。
旧产物来自同基线 worktree 的 `web/dist`，新产物在本项独立 worktree 构建。
未安装或升级依赖，复用现有 `node_modules`。

| 实际生产构建产物 | 旧构建 | 新构建 |
| --- | ---: | ---: |
| HTML `prefetch` 提示 | 378 | 0 |
| HTML 初始 `preload` 提示 | 4 | 4 |
| `preload` 目标的未压缩文件大小合计 | 9,131,001 字节 | 9,131,001 字节 |
| 首页 HTML 文件大小 | 27,110 字节 | 6,084 字节 |
| JS/CSS 文件数，包含生成的 gzip 文件 | 497 | 497 |

被移除的预取提示指向资源的未压缩文件大小合计为 8,071,640 字节。
此数值是构建产物统计，不能直接当作浏览器实际减少的传输量：部分异步资源也会被
当前首页按需使用，压缩、缓存和浏览器调度也会影响实际网络请求。

生产构建保留 230 个异步 JS 分块，基础路由保留 14 处动态 `import()`，编译后的
入口仍包含 `home` 分块的动态加载调用。首页、课程目录和社区的路由源码未改。
Vue CLI `inspect` 确认 `preload` 插件保留、`prefetch` 插件消失。
这里按入口运行时的 JS 哈希映射统计；240 个未压缩 JS 文件还包含 8 个复制的
`public` 静态脚本和 `app`、`chunk-vendors` 两个初始构建包。

构建生成的部分 JS 文件名哈希重新计算。按逻辑分块名和内容 SHA-256 核查：
497 个 JS/CSS 资产集合相同；除入口 `app` 及其 gzip 文件外，所有文件内容一致。
入口文件中的异步分块文件名哈希映射更新后，入口正文逐字一致。
初始 preload 的逻辑资源、数量和大小相同，HTML 引用匹配新构建文件。

执行结果：

- `NODE_OPTIONS=--openssl-legacy-provider npm run build`：成功。
- `npm test`：318 项通过，0 失败。
- `node --check vue.config.js`：通过。
- `git diff --check`：通过。

本机构建记录位于 `.devspace/artifacts/frontend-route-prefetch/`：
`before-manifest.json`、`after-manifest.json`、`content-checks.json`、
`build-checks.json`、`build.log`、`tests.log`、`preload-config.txt` 和 `plugins.txt`。
`build-checks.json` 中严格比较完整文件名的检查为 false，原因是上述构建哈希变化；
逻辑资源和内容检查记录在 `content-checks.json`。

另一位 Agent 独立只读核对了配置、497 个逻辑资源的磁盘摘要、初始 preload、
230 项运行时异步 JS 哈希映射及路由动态导入，未发现本项阻断问题。
其检查没有重跑上述 318 项作者测试，也没有进行浏览器操作。
开发与核查按用户指定使用 GPT-6.1-sol / Ultra；委派工具无单独 Fast 参数。

## 整合浏览器验证

整合验证对同一 `85f8a7d` 源码基线的旧新生产构建各采样 5 轮。
两个本地代理共用同一后端私有副本和匿名 API 数据；屏幕为 1440 × 1000，
未进行网络或 CPU 限速，每轮禁用网络缓存并清理浏览器缓存，服务端及操作系统缓存
保持原状。Resource Timing 缓冲区设为 2000，首页课程卡片可见且图片加载完成后
再等待 2500 ms 统计同源资源；不包含跨域资源或导航文档本身。
原始测量条件完整保留在
[browser-comparison.json](evidence/frontend-route-prefetch/browser-comparison.json)。

| 首页实际浏览器测量 | 旧构建 | 新构建 |
| --- | ---: | ---: |
| 同源资源请求条目，5 轮相同 | 395 | 17 |
| 同源资源 `transferSize` 合计，5 轮相同 | 23,581,181 字节 | 15,396,141 字节 |
| 课程卡片可用时间中位数 | 318 ms | 243 ms |
| 课程卡片可用时间范围 | 312–322 ms | 225–437 ms |

在该本地采样条件和统计窗口内，资源请求减少 378 条，传输量减少
8,185,040 字节，即 34.71%。5 轮两版均显示 3 张课程卡片，未出现横向溢出。
新版有一轮课程卡片可用时间为 437 ms，因此这里不声称普遍的延迟改善。
早期使用 Resource Timing 默认 250 条缓冲区的探索统计发生截断，不作为本项证据。

两版均通过实际点击导航：首页 → 全部课程（3 张课程卡片）→ 页脚创作社区
（3 张编辑器卡片）→ 登录学习（账号与密码表单可见）。每版各观测到 1 次
点击后的 `user` 分块响应，状态为 200，点击前未观测到该分块响应。
未捕获未处理的 `pageerror`。两版都有本地 CSP 阻止既有外部 `errlog.js` 的
控制台错误；旧版探索还观察到既有 Ant `aria-hidden` 焦点警告，不能将此结果
表述为浏览器无任何错误或警告。匿名导航没有登录、验证码交互或表单提交。
登录导航 102 ms / 51 ms 是各一次观测，不作为性能结论。

初次导航探针因带图标链接的精确无障碍名称不匹配而超时，依据新页面快照改为
`preview-heading` 与 header 的 href 选择器后通过。原失败日志仍保留在
`.devspace/frontend-route-prefetch-browser/navigation.log`，脱敏导航结果见
[navigation.json](evidence/frontend-route-prefetch/navigation.json)。
此选择器修正没有修改产品代码。

复现探针保留整合验证所用脚本原文：
[measure-old.cjs](evidence/frontend-route-prefetch/measure-old.cjs)、
[measure-new.cjs](evidence/frontend-route-prefetch/measure-new.cjs) 与
[navigation.cjs](evidence/frontend-route-prefetch/navigation.cjs)。
它们是 Playwright 的 `async (page) => { ... }` 探针，在准备好相同本地代理、
后端副本和 Chromium 页面后调用；不是独立 Node CLI 程序。脚本只返回汇总指标、
数量和状态，没有生产正文、账号或凭据。

## 验证边界与后续检查

作者完成本地生产构建和产物核查，未启动服务或访问生产数据。
整合验证完成了上述本地匿名首页资源测量和实际点击导航。
本项结果不代表公网性能、并发容量、真实师生验收、合并或生产上线。

初始主包仍然较大。本项只处理默认批量预取，没有重拆分块、迁移框架或更换依赖。
