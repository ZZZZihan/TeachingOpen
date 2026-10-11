# H-02 通知管理与收件边界

审查基线为 `2cbd9c4713a6a7ec830fd6c5b30a02a2a98aface`；本修复从仅含候选包 Nginx pin 修复的 `a3f4e10ceafcbe405093a3abe06a20225a17d3f6` 开始。验证使用隔离合成账号和数据，未访问生产，也未把静态结论称为生产攻击。

## 复现和最终行为

原通知控制器允许普通登录用户新建、修改、删除、发布及撤销；原收件控制器还能写入任意收件关系，已读接口把 `anntId` 拼入 SQL 尾部。原展示组件直接把 `msgContent` 写入 `v-html`。

实际合成 HTTP 基线由统筹会话保存在 `evidence/baseline/h02-before-r2.json`，6 项通过，包含普通学生写入/发布、另一登录用户通过 WebSocket 收到广播、未净化正文存储和返回。实际 Chromium 挂载原 `ShowAnnouncement.vue` 后，无外传的图片错误事件将本页 `dataset.executed` 设置为 `image`。本分支修复后同一 payload 不执行，段落、图片和表格保留；见本分支 `evidence/h02/browser-before.json` 与 `browser-after.json`。

- 管理入口及服务命令使用实时数据库账号和 `admin`/`dev` 角色；不依赖 JWT 缓存中的旧角色。管理权限为全站通知管理，读权限仍按当前收件人、发布及删除状态判断。
- `AnnouncementCommand` 仅接收可编辑字段。ID（新建时）、发送人、审计信息、删除和发布状态、动态组件/路由信息均由服务端控制。Excel 导入复用相同命令与事务。
- 新建、编辑、受众替换、发布/撤销及批量删除在事务中执行，管理目标加行锁；拒绝和事务失败不改变通知、收件关系或广播状态。
- 收件关系通用写入入口明确拒绝，管理人员使用父通知的受众编辑。普通用户保留自己通知的列表、详情、标记已读、全部已读和本人其他标签页同步；本人同步不再向全站广播。
- ALL 通知沿用注册时间作为历史资格边界。历史账号没有注册时间时，以当前时间兜底，可读取有效或无截止日期的全员通知，不会因此获得已过期历史；订阅、详情、两个列表和批量已读采用相同规则。
- 历史通知在列表、详情、导出和收件箱读取时净化；写入及内部通知生产者也净化正文。历史动态导航只保留服务端既有业务类型定义的目的地。前端实际展示组件再次调用既有 DOMPurify 策略。
- 广播仅在事务提交后发送，socket 失败记录日志并保留成功写入的成功响应，用户仍可通过通知列表读取。
- 同类发件箱、消息模板及测试发送控制器均要求实时通知管理权限。未对真实邮件、短信或第三方网络执行发送。

## 回归和执行方式

`AnnouncementAuthorizationTest` 包含 16 项 Java 测试；连同既有 `RichTextSanitizerTest` 3 项全部通过。覆盖管理矩阵、同主体撤权、固定字段、目标受众、历史内容/导航、已读参数绑定、提交后广播及广播失败，以及缺失/已知注册时间的 ALL 资格、真实 POI XLSX 导入。现有 `notification-socket.test.cjs` 11 项通过。

首次整合候选 HTTP 回归为 243/246，通过全部拒绝和状态隔离检查，但发现学生/教师漏收 ALL 及手工 XLSX 探针缺样式表导致 POI 3.9 解析失败，原文由统筹保留在 `evidence/fixed-r1/http-other-high-r1/`。两个 NULL 注册时间 Java 回归在 `2c6d1574` 上重现，修复后 19/19 通过，见本分支 `evidence/h02/null-registration-before.json`、`null-registration-after.json`。修正后的探针工作簿已由候选中实际 POI 3.9 库解析校验，见 `xlsx-fixture-parser.json`；对应实际 HTTP 需由统筹绑定更新后的不可变候选重跑，不能用旧候选的 243 项通过替代。

```sh
cd api
mvn -s dev/maven-settings.xml -DskipTests=false \
  -Dtest=AnnouncementAuthorizationTest,RichTextSanitizerTest \
  -Dsurefire.failIfNoSpecifiedTests=false -pl jeecg-boot-module-system -am test
cd ..
node --test web/tests/notification-socket.test.cjs
CHROME_BIN=/path/to/chromium node web/tests/announcement-rendering.browser.cjs
CHROME_BIN=/path/to/chromium node web/tests/announcement-rendering.browser.cjs --expect-legacy
python3 api/dev/verify-announcement-authorization.py \
  --runtime /path/to/isolated-synthetic-runtime --jar /path/to/candidate.jar \
  --output /path/to/report.json
```

浏览器测试编译、挂载实际 `ShowAnnouncement` SFC，仅替代外层设计系统容器，无通知组件替身。它检查真实 DOM、危险 URL/事件处理器移除、无本地执行标记，以及普通段落、图片、表格；全部资源内联或 `data:`，不向其他主机外传。视口为 1280×800，可用 `ANNOUNCEMENT_SCREENSHOT_DIR` 保存对应前后截图。本机使用已安装 Chromium headless shell；桌面 Chrome 的 headless 显示初始化不稳定，未用其失败当作安全通过。

HTTP 探针覆盖学生/教师全部管理和旁路入口、读取自己与他人通知、编辑受众后旧 token 失权、实时移除管理角色、拒绝前后四表哈希和 socket 静默、真实 XLSX 导入及收件写入失败触发器回滚。它临时将两个合成账号的注册时间设为 NULL/指定时间，核验当前 ALL 可收、过期历史边界及无资格收件关系不被批量标读。项目现有权限拒绝协议为 HTTP 200、业务 `code=510`、`success=false`；探针同时检查“没有权限”消息，不把任意 500 或校验错误当授权拒绝。探针完成后删除本探针创建的合成记录，还原注册时间，校验原通知表状态恢复。

最终组合候选的 HTTP、CI、打包和 Pro 独立验收由统筹会话执行并绑定最终不可变提交。本文和本地单测/浏览器证据不替代这些门槛，也不构成生产部署或绝对零漏洞声明。
