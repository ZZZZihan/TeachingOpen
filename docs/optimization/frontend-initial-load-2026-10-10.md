# 首屏依赖按需加载验证

基线为 `33995e5b41237d552cf21b66eb408623ac830eab`，即 CI PR #89 合并后的 `codex/registration-acceptance`。本次只处理入口资源；CSS 顺序整改独立跟进。没有升级依赖、关闭警告或提高 Webpack 性能阈值。

## 原因与改动

生产构建依赖统计显示，入口同步包含 OnlineForm UMD（约 5.19 MB 模块源码）和 G2（约 1.78 MB 模块源码）。这不是压缩后传输体积。Online 包同时由 `main.js` 和路由工具同步引用；Viser 在 `main.js` 全局注册。

- 8 类 Online 路由现在在实际访问时解析异步组件，JS/CSS 同时加载。构造后台菜单不会提前下载它们；失败会拒绝本次导航，后续访问可以重试。
- 14 个图表组件通过共用安装模块，在各自异步页面加载时注册 Viser；Online 包也保留原来的图表注册前提。
- 已有的禁用全站预取配置继续保留。
- CI 新增 `npm run check:initial-assets`，统计生产 HTML 引入的本地 JS/CSS（包括 public 中的 polyfill/common），去重 preload 与 script。限制为 3.25 MiB 未压缩、0.9 MiB gzip。候选通过，旧基线失败；这项检查独立于 Webpack 的默认警告阈值。

## 生产构建

| 指标 | 基线 | 候选 | 减少 |
|---|---:|---:|---:|
| Webpack app 入口 JS/CSS | 9,133,788 B（8.71 MiB） | 3,040,675 B（2.90 MiB） | 66.7% |
| app 入口 gzip（相同 level 9 算法） | 2,711,685 B | 822,637 B | 69.7% |
| HTML 所声明的全部本地 JS/CSS | 9,372,871 B | 3,279,758 B | 65.0% |
| 上述 HTML 资源 gzip | 2,772,708 B | 883,660 B | 68.1% |

入口包统计不包括按路由下载的 user/home 包；HTML 统计额外包括 public 的 polyfill/common；下方浏览器结果还包含当前路由包，口径分别列明。

`npm ci --ignore-scripts --no-audit --no-fund` 使用锁文件安装。Node 26.11.0 / npm 11.20.0 本机生产构建通过，`npm test` 699/699；`npm run lint:changed` 及新增入口辅助模块的显式 ESLint 通过。新增测试覆盖菜单构造不下载 Online、全部 8 个组件映射、普通路由保持原加载方式、失败后重试。

标准 `npm run build` 仍有 11 条警告：9 条 CSS 顺序、2 类体积提示。大型异步包仍存在，但已不在首屏入口中。没有将警告数不变误称为整改无效，也没有宣称全部性能问题已消除。

## 浏览器结果

同机 Chromium、1440×1000、每次独立 context/冷缓存、服务端 gzip、模拟 10 Mbps 下行/50 ms 延迟/4 倍 CPU 降速；每项 3 次。接口由本机合成夹具响应，外部日志脚本替换为空响应。页面就绪以实际表单或首页名单状态可见为准，不使用加载动画的 first-contentful-paint 代替业务内容。

| 页面 | JS/CSS 请求数（前→后） | gzip 响应体（前→后） | 内容可见时间中位数（前→后） |
|---|---:|---:|---:|
| 登录 | 8 → 8 | 2,789,092 → 900,044 B | 3,720 → 1,294 ms |
| 注册 | 8 → 8 | 2,789,092 → 900,044 B | 3,678 → 1,269 ms |
| 首页 | 8 → 8 | 2,794,242 → 905,194 B | 3,779 → 1,354 ms |

18 次加载均未捕获 pageerror。三页全页截图在相同 viewport 下逐像素一致（登录 1440×1000、注册 1440×1263、首页 1440×1000）。候选三页没有请求 Online 异步资源；访问图表页后绘制出 976×420 柱状图，仍未请求 Online；进入 Online 表单页才加载 5,191,415 B JS 和 76,932 B CSS，列表、报表页可打开。

教学工具的本地入口检查与后端写入验收分开记录：Python 从创作入口打开，显示“可以开始编写代码”；Scratch 从入口打开并显示编辑器。没有用合成接口冒充真实账号、注册落库、作品保存或生产服务验收。

原始资源清单及 18 次浏览器记录位于 [evidence/initial-load-20261010](evidence/initial-load-20261010)。本机截图与验证脚本保存在工作区 `output/playwright/initial-load-20261010` 和 `.devspace/initial-load-*`。这些是本地受控测量；上线效果仍取决于真实服务器压缩、缓存、用户网络和设备。

复核入口：

```sh
cd web
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run lint:changed
NODE_OPTIONS='--openssl-legacy-provider --max-old-space-size=4096' npm run build
npm run check:initial-assets
# 需要依赖图时额外使用 --report-json；report.json 体积较大，不提交到仓库。
```
