# 中性品牌与科技蓝主题

用户选择保留现有布局和功能，只替换天津工业大学相关的内置品牌及紫色主色。候选基于 `6da25b9caabf06574b7b17a824d32e8c6e0d7dc5`，分支为 `feature/neutral-blue-branding`。

## 改动范围

- 内置校名字标、校园照片、校训、学校外链、浏览器标题和图片失败回退改为 TeachingOpen 与学习主题内容。两个替代 SVG 为本次自制，不引用外部图片。
- 主色统一为 `#146fc2`，hover 为 `#095b9e`，登录背景为 `#123e67`；同步默认设置、动态主题默认源、按钮、链接、选中状态和浅色背景。其余可选主题与红绿状态色保留。
- 组件脚本、页面尺寸、间距、布局、断点与教学业务逻辑保持原样。外链替换指向既有站内路由。
- 三个既有独立预览构建增加 SVG 支持并同步默认主题；品牌相关既有测试只更新预期文字。没有新增测试或依赖。
- README 使用[候选首页实拍](../images/course-home-blue.png)，历史截图和素材来源记录继续保留。

## 本地验证

- `npm test`：703 / 703 通过，无跳过。
- `npm run lint:changed`：通过；另外对本轮主要品牌组件执行 ESLint，通过。
- 新涉及的旧主题设置文件存在历史 ESLint 错误；子 Agent 将诊断与改动前逐项比较，新增诊断为 0，没有扩大范围修复历史格式。
- `NODE_OPTIONS='--openssl-legacy-provider --max-old-space-size=4096' npm run build`：成功。仍有资源体积和入口体积两类警告，以及 Browserslist 数据过期提示。
- `npm run check:initial-assets`：通过，初始 JS/CSS 为 3,279,537 bytes，gzip 为 883,355 bytes，均在仓库预算内。
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_prepare_launch_data -q`：18 / 18 通过；后端文件本次仅改注释。
- `account-recovery-preview`、`student-feedback-preview`、`student-work-loading-preview` 三份既有 `build.cjs` 实际构建均以 0 退出；产物包含新 SVG 标识和科技蓝主题。
- 独立 Agent 核查了品牌入口、配置覆盖、路由、SVG、安全的图片失败回退和布局不变性；发现的预览 SVG loader 兼容问题纳入本次修复。

## 浏览器证据与限制

实际候选 `web/dist` 通过本地 HTTP 服务加载。沿用 `web/tests/browser-fixture.py` 的服务方式，在仓库外临时副本中提供默认品牌配置、3 门明确标注的合成课程和空注册目录；没有连接真实后端或生产数据库。

在 1440 和 390 像素宽度分别打开首页、课程列表、登录、注册、密码找回，共 10 个场景：页面宽度未超过视口、图片正常加载、可见文字无学校品牌、链接无学校外链。另在 1440、390、320 像素宽度触发两个品牌图片的 `error` 事件，确认文字回退为 TeachingOpen 与学习文案且无横向溢出；该检查只验证错误处理分支，不模拟真实网络故障。

正式首页截图在恢复图片正常加载后直接保存，未改 DOM、未后期改字。登录与找回页面的验证码由合成服务触发未加载状态，本轮只检查显示与品牌，不宣称真实登录、验证码、注册或密码重置链路通过。

现有服务端品牌、Logo、Banner、页脚、自定义 HTML/CSS，以及浏览器内已保存主题仍按原有方式生效。已上传课程、视频、教案和附件未逐项审核；本 PR 的去学校化范围是内置平台界面。未合并、未部署、未修改生产配置，也不代替用户人工验收。
