# H05 教学菜单管理与导航 URL

实施提交：`13e215da4970fa4838038cdb6fab27174138c38e`。基线前端提交：`93d4cfe8`（H05 代码与 Pro 第一轮候选 `d88f4392` 相同，仅增加前一项 CI 配置修复）。本记录是实施者回归，不替代 Pro 独立验收。

Pro 第一轮新增识别的链为：普通登录账号写入公共教学菜单，公共菜单原样返回 URL 和导航标志，真实 `Header.vue` 经 `TMenu` 渲染原生同页链接，点击 `javascript:` 目标执行。这里的新增识别不表示本轮代码引入，也不表示验证过生产攻击。

## 修复边界

- 菜单管理全部 11 个 HTTP 方法入口（6 个管理查询、POST 新增、PUT/POST 编辑、单删、批删）进入同一个服务边界。每次查询当前账户及数据库 admin/dev 角色，忽略旧 Shiro 角色缓存；匿名公共 `getUserMenu` 仍可使用。当前控制器没有导入、导出或独立排序入口；排序在编辑中受同一检查。
- 服务不再继承通用 `IService` 写方法；服务端选取可写字段、生成新增 ID、设置审计与删除/叶子状态。编辑限制父子循环，删除在一个事务中先验证所有请求 ID，再级联删除，避免失败批次已经删除一部分。
- URL 仅允许空分组、单斜杠开头的站内路径和无账户信息的 HTTPS 外链。拒绝可执行协议、协议相对地址、反斜杠、控制字符、危险编码和畸形地址。HTTPS 不按内部路由处理；站内静态编辑器路径仍保留原查询参数。现有 HTTP 外链将禁用，需要管理员改为 HTTPS 或站内地址；未改写生产或历史存储。
- 公共读取对历史危险目标输出空 URL 并关闭导航标志，不修改数据库。真实 TMenu 对顶级链接、子菜单标题和子项再次执行独立 URL 规则；危险目标变成无 href 的文字，安全子项仍可访问。新页外链带 `noopener noreferrer`。

## 已完成的证据

| 回归 | 结果 | 原始证据 |
| --- | --- | --- |
| 服务与 MockMvc | 15/15，无失败/错误/跳过 | [Java 原文](java.txt) |
| URL 策略及既有 Header 状态回归 | 29/29（新增策略 28 项） | [Node 原文](node.txt) |
| 旧候选真实 HTTP / MySQL | 19/19；最后完整表摘要还原 | [报告](http/before.json)、[日志](http/before.log) |
| 真实 Header + TMenu 基线 Chromium | 26/26 | [报告](browser/before/report.json)、[源码摘要](browser/before/sources.json)、[日志](browser/before/run.log) |
| 同一真实组件修复版 Chromium | 28/28，绑定实施提交 | [报告](browser/after/report.json)、[源码摘要](browser/after/sources.json)、[日志](browser/after/run.log) |

HTTP 基线 JAR SHA256：`7fc5d65069f9b04ab0d4285bff50a2e19d16b67f43ac2d51e76ea582c25e9ba3`。仅访问任务拥有的合成环境；使用唯一菜单 ID 和当前页无害标记。原始菜单、角色关联表的完整摘要在 finally 中核对还原，临时登录注销。首次基线将父子同时按父优先批删，旧实现先级联删除子项再重复删除，业务响应失败；记录在 [首次报告](http/before-attempt-1.json) / [日志](http/before-attempt-1.log)，不计为成功。随后按子优先覆盖旧批删接口，19 项全部完成。

浏览器是 `HeadlessChrome/151.0.7922.34`。runner 编译原始 `Header.vue`、真实 JSX `tmenu.js`、真实 Ant Menu、CampusMasthead、Vuex 和 Vue Router，没有替换 TMenu。两种尺寸各用 Chromium `Input.dispatchMouseEvent` 实际点击顶级、子标题、子项；基线三个计数器均从 0 到 1，修复后三个均保持 0。正常子项、含参数及片段的 SPA 路由、同源静态编辑器、HTTPS 同页和新页全部完成。HTTPS 合成目标由 CDP Fetch 在发往网络前返回测试 HTML，4 次预期导航全部被拦截，没有意外出站或浏览器错误。

## 截图

全部图片由同一次 Chromium 回归原样捕获，没有编辑。宽高分别为桌面 `1440×1000` 与窄屏 `390×1200`；每组还包含正常路由和 HTTPS 外链截图，完整索引见报告旁的文件。

| 场景 | 修复前 | 修复后 |
| --- | --- | --- |
| 桌面危险菜单，点击后 | [1440×1000](browser/before/1440-unsafe-after-click.png) | [1440×1000](browser/after/1440-unsafe-after-click.png) |
| 窄屏危险菜单，点击后 | [390×1200](browser/before/390-unsafe-after-click.png) | [390×1200](browser/after/390-unsafe-after-click.png) |
| 桌面正常站内导航 | [1440×1000](browser/before/1440-normal-route.png) | [1440×1000](browser/after/1440-normal-route.png) |
| 窄屏正常站内导航 | [390×1200](browser/before/390-normal-route.png) | [390×1200](browser/after/390-normal-route.png) |
| 桌面 HTTPS 新页导航 | [1440×1000](browser/before/1440-https-new-tab.png) | [1440×1000](browser/after/1440-https-new-tab.png) |
| 窄屏 HTTPS 新页导航 | [390×1200](browser/before/390-https-new-tab.png) | [390×1200](browser/after/390-https-new-tab.png) |

## 重跑

从仓库根执行；Java 8 与 Maven 使用项目支持版本，`CHROME_BIN` 指定安装的 Chromium/Chrome 可执行文件。`npm ci` 后不需要新增依赖或 Playwright 安装。浏览器缺失直接失败，不会退化为 JSDOM，也不会跳过。

```sh
mvn -o -B -ntp -f api/pom.xml -s api/dev/maven-settings.xml -DskipTests=false -Dtest=TeachingMenuSecurityTest -Dsurefire.failIfNoSpecifiedTests=false -pl jeecg-boot-module-system -am test
node --test web/tests/teaching-menu-navigation.test.cjs web/tests/header-menu.test.cjs
CHROME_BIN=/path/to/chromium NODE_OPTIONS=--openssl-legacy-provider node web/tests/teaching-menu-browser.cjs --output ci-results/menu-browser
CHROME_BIN=/path/to/chromium NODE_OPTIONS=--openssl-legacy-provider node web/tests/teaching-menu-browser.cjs --ref 93d4cfe8 --expect-legacy --output ci-results/menu-browser-before
python3 api/dev/verify-teaching-menu-security.py --runtime /path/to/owned-runtime --jar /path/to/exact-running.jar --output ci-results/menu-http.json
```

HTTP 脚本也支持 `--expect-legacy`。它始终验证 runtime 所有权、合成账户及正在运行的 JAR SHA。固定模式覆盖普通学生/教师所有管理入口拒绝且整表不变、同 JWT 现授 admin/dev 后撤权、管理员合法增改删、历史危险 URL、写入 URL 的全部导航标志组合、审计字段、树父子状态及失败批次无部分删除。输出包含 `passed/failed/total/expected_legacy/completed/jar_sha256`；浏览器输出同样有完成状态、版本、源码 ref/逐文件摘要和实际点击位置/href。

本目录归档时，固定组合 JAR 的 HTTP 回归、最终 CI、候选打包与下一轮 Pro 由根会话继续执行；本目录不把这些未完成项写为已通过，也未连接或部署生产。所有归档文件的 SHA256 见 [证据清单](evidence-manifest.json)。
