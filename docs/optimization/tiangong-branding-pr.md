# 天津工业大学校园视觉

## 目标与验收行为

在现有课程与登录体验中加入可辨认的天津工业大学校园身份：官方校名校徽、天工紫、真实校园照片、校训及办学理念。保持克制排版、真实课程信息和现有操作路径。

- 首页、课程发现及登录页显示统一学校标识，390 / 768 / 1440 宽度可使用且无水平溢出。
- 使用本地打包素材，页面运行不依赖学校网站图片请求；校园图加载失败时保留完整导语与课程入口。
- 保留平台自定义名称、logo、菜单、banner、首页 HTML、footer；学校标识与平台标识分别呈现。
- 保留匿名查看课程、课程详情与去上课跳转行为，不改账号、验证码、权限、课程或教学数据。

## 素材依据

- [天津工业大学网站设计规范](https://nic.tiangong.edu.cn/2021/1027/c233a71914/page.htm)：天工紫 RGB 116,37,106（#74256A）及校标形制。
- [学校章程](https://fgc.tiangong.edu.cn/2024/0321/c434a92641/page.htm)：英文校名 Tiangong University、校训“严谨、严格、求实、求是”、办学理念“教研相长、学能并进”。
- [学校主页](https://www.tiangong.edu.cn/)官方标识原文件：[logo.png](https://www.tiangong.edu.cn/_upload/site/00/0c/12/logo.png)，265×66，保留原像素及比例；原图底色 #71246B 单独用于标识横栏，页面交互主色使用 #74256A。
- [新闻网校园景色（四）](https://news.tiangong.edu.cn/2022/0617/c7646a77757/page.htm)首图：[校园实景](https://news.tiangong.edu.cn/_upload/article/images/75/d4/4a5d777841619b51f99fc6328748/71274e44-89e1-457b-8b4f-52c681c7a024.jpg)，499×333，采用官网提供的页面尺寸版本，保留原文件，避免引入 6.3 MB 原图。

上述标识与照片权利归原权利人，保留来源。不复制学校备案、版权归属或统一身份认证声明。学校官网与图书馆仅为外链。

## 验证

产品提交 `87974555da37ba3cfe2188710f6749cf63b00ae3`。基于 #37 `fix/scratch-cloud-client` 堆叠，未包含教师批改工作区改动。匿名真实后端沿用 #38 精确 JAR；本 PR 没有后端改动。

- 分支现有前端检查 **184/184**；11 个修改源码文件 ESLint **0 errors / 0 warnings**；生产构建成功。
- 真实构建前端 + 隔离 Java 后端匿名浏览器 **16/16**：首页、课程、登录三页 × 390 / 768 / 1440 宽度；本地图片解码；官方链接；手机导航；课程详情天工紫按钮；去上课保留登录跳转目标；登录输入为空、验证码图可加载。
- 浏览器临时阻断 / 响应替换 **7/7**：校图及校名图失败回退、自定义首页/名称/logo/footer、横幅优先及窄屏。测试新建的匿名 context 已关闭，未修改后端配置。
- 前后 **19 张截图**、逐项结果与素材 SHA-256 在 [evidence/tiangong-branding](evidence/tiangong-branding/checks.json)。素材合计 142,451 bytes（约 139 KiB），原样打包，无依赖更新。
- 构建仍有 6 项既有类型警告（3 个旧 CSS 顺序、资源/入口大小、性能建议）和旧 Browserslist 提示。浏览器存在既有远程 errlog 被本地 CSP 阻断记录及 Ant Design 弹窗焦点警告；导航时两条预加载连接重置后对应资源 HTTP 200，不声称控制台零错误。

本轮只完成校园视觉工程自检。组件库主色全局改为天工紫，已登录管理页面尚未逐页视觉评阅；未填写验证码或完成真实账号登录，未合并、上线，用户视觉验收待进行。

| 页面 | 修改前 | 修改后 |
| --- | --- | --- |
| 首页 1440 | [前](evidence/tiangong-branding/before-home-1440.png) | [后](evidence/tiangong-branding/after-home-1440.png) |
| 首页 768 | [前](evidence/tiangong-branding/before-home-768.png) | [后](evidence/tiangong-branding/after-home-768.png) |
| 首页 390 | [前](evidence/tiangong-branding/before-home-390.png) | [后](evidence/tiangong-branding/after-home-390.png) |
| 登录 1440 | [前](evidence/tiangong-branding/before-login-1440.png) | [后](evidence/tiangong-branding/after-login-1440.png) |
| 登录 768 | [前](evidence/tiangong-branding/before-login-768.png) | [后](evidence/tiangong-branding/after-login-768.png) |
| 登录 390 | [前](evidence/tiangong-branding/before-login-390.png) | [后](evidence/tiangong-branding/after-login-390.png) |

浏览器脚本以 Playwright CLI `run-code` 执行，仅用于本地已构建页面的观察与故障模拟；需要本地后端合成课程 fixture，不能用于生产。
