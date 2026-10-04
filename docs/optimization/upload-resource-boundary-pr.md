# 上传目录与公开资源路由隔离

私有上传文件可以绕过规范下载地址的权限检查。旧冻结包中，自制私有 PNG 的 `/api/sys/common/static/<key>` 匿名请求返回 401，但 `/api/<key>` 返回 200，响应字节与私有文件完全相同。HEAD 暴露文件长度，Range 返回真实文件切片。`generic/<key>.txt` 与 `sys/common/pdf/<key>.txt` 也经由匿名路径暴露上传内容，因此问题不限于图片或 PDF 扩展名。

原因是 `WebMvcConfiguration` 把上传目录放在公开 `/**` 资源映射的首位。修复移除这一个目录位置及其不用的配置注入，保留 webapp 目录和配置的公开 classpath 资源位置。上传文件通过已有 `/sys/common/static/**` 的鉴权、精确键匹配与下载权限服务读取。公开 webapp 与上传目录存在相同相对键时，普通资源地址现在返回 webapp 的公开字节，规范下载地址按权限返回上传字节。

这是本机隔离环境中实际复现的资源路由旁路。普通小写地址已经能复现；此记录没有把它认定为某个 CVE，也没有声称生产环境、浏览器认证或人工验收完成。

## 冻结候选与实际检查

| 检查范围 | 旧冻结包 | 修复冻结包 |
| --- | --- | --- |
| 同一组边界断言 | 247/451 通过，204 失败；退出码 1 | 451/451 通过 |
| 既有规范下载回归 | 未在最终旧包对照中执行 | 88/88 通过 |
| 修复包总报告 | — | 452/452；退出码 0，含一条下载回归集合检查 |
| 结束状态恢复 | 69 张表结构、68 张非审计表行摘要、所有用户字段和文件一致 | 同左 |

451 条断言覆盖 PNG、HTML、PDF 的根路径与嵌套路径，两种匿名前缀的 TXT，匿名、本人、同班教师、管理员、跨班学生及教师，GET、HEAD 与 Range，大写路径及扩展名别名，公开作品的规范地址，公开 webapp 资源及上传/公开同名碰撞，以及冻结 JAR 内 `generic/web/viewer.html`、`viewer.css` 的精确公开字节。最后一条是完整恢复检查。旧包失败分类为普通上传路径 144、大写别名 48、公开作品普通别名 3、上传文件遮蔽同名 webapp 资源 9；规范下载权限和打包公开资源检查均通过。

额外 88 条既有下载回归包含媒体 Cookie、请求头优先级、登录失效、HEAD、Range、历史附件、公开课程/新闻/配置资源以及链接/非法路径拒绝。它通过现有 API 工具完成合成登录，不等于真实浏览器登录验收。

- 旧 JAR SHA-256：`f03ac420301977cea26e14d9de0bab03f0d8a5c0e7ec92854363ad07347060c0`。
- 修复 JAR SHA-256：`9eb18d42d365dd4fba7044d57ed33aaa0fdb543f8468dd67c10c9dc83de05869`。
- 两次最终运行的探针 SHA-256：`cd8a799e0a928e16a3530686e167ca28a7ebebd88844360a8b1c140de1a1b487`。
- 既有下载回归脚本 SHA-256：`a3ec1444d1ad88d658ea6c697182a6f89bec668de2220225d6cc5b4e0332f11d`。

构建使用固定 JDK 8/Maven 和已有依赖缓存，`clean package` 成功；构建过程跳过单元测试。上表来自之后执行的真实本机 HTTP 和 MySQL 检查。候选包及测试工具的冻结副本留在本机私有 artifacts，仓库只保留[脱敏汇总及代表响应](evidence/upload-resource-boundary/synthetic-summary.json)。

## 专属环境与复现

专属运行目录是 `.devspace/resource-route-1005`，四个固定端口分别为 MySQL 13374、Redis 16447、后端 18184、前端 18185。初始化时目录不存在，四个端口再次核对为空闲；使用 `prepare-local.py` 提取 69 张表的 DDL，未导入上游 INSERT，随后仅建立五个合成账号。为让旧包复现不依赖正在改动的源码构建，旧包中的 `PasswordUtil` 被提取到私有 helper，配合现有 `seed-fixtures.py` 和 `FixturePassword.java` 初始化账号。未修改原工具或其他构建目录。

探针只接受这个无符号链接的专属目录和端口，检查实际 MySQL 数据目录、五个账号的完整身份集合、Redis 数据目录、私有配置、JAR 路径与 SHA-256、后端进程参数，以及 MySQL/Redis/后端的监听 PID 和 loopback 绑定。资源请求显式禁用代理和重定向，响应上限为 2 MiB。只运行本任务创建的合成环境，不将命令指向生产或已有长期服务。

在[后端构建说明](../../api/BUILDING.md)所述工具链已准备好、相应冻结 JAR 已启动并健康为 UP 后，分别对旧包与新包执行相同命令形式。输出必须使用不存在的新文件，位于专属运行目录或 `.devspace/artifacts/upload-resource-boundary/` 内；不会覆盖旧证据。

```sh
python3 api/dev/verify-upload-resource-boundary.py \
  --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/resource-route-1005 \
  --jar /absolute/path/to/frozen-candidate.jar \
  --jar-sha256 SHA256_OF_THAT_FROZEN_JAR \
  --output /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/upload-resource-boundary/new-comparison.json
```

新包检查可加 `--download-regression` 执行既有 88 条回归。旧包使用安全行为断言，因此实际边界失败会返回非零退出码；没有切换成“预期泄露即通过”的判据。脚本及辅助工具在最终旧/新检查之间没有修改。

探针在登录前保存用户的全部列、全部 69 张表结构及逐列编码行摘要、uploads/webapp 文件摘要。`finally` 退出合成会话，精确删除本次插入的作业/文件记录和自制文件，恢复用户全部列，再核对 69 张表结构、68 张非审计表完整行摘要以及所有附件/公开文件。认证审计表 `sys_log` 可以保留本次审计记录。私有用户快照、口令、Token、配置、原始日志均未进入仓库。

首轮探针使用过长自制 ID，MySQL 对 `work_file VARCHAR(32)` 返回基础设施错误；其报告为 1/2，并确认恢复。修正为短 ID 后，中间矩阵为 241/445；补足 classpath 判据并冻结工具后，最终对照仅使用同一 451 条断言。首轮和中间报告保留在本机私有目录，没有替代最终证据。

本项验证支持本机合成场景的资源隔离结论；实际部署配置、自定义公开资源位置、其他服务器操作系统和人工业务验收仍须按对应环境单独核对。

## 主 Agent 复核与兼容说明

日期：2026-10-05（Asia/Shanghai）。本分支基于 PR #62 `fix/class-membership-access` / `328a021224521674654c8c6f03c01be7fbb7ae2f`。两个指定 GPT-6.1-sol / ultra Agent 分别完成实现与实际独立测试；子 Agent 接口无单独 Fast 参数。根 Agent 复核代码差异、两份原始报告的计数和按序断言、JAR 与冻结源码绑定。该报告审查不是第二次 HTTP 实测。

[作者记录](upload-resource-boundary-author.md)保留构建及冻结细节：唯一变动的应用 class 为 WebMvcConfiguration，208 个外部依赖 archive 字节相同，内部 common archive 解包文件逐字节相同。构建日志两处 Tests are skipped；早期成功但被最终缩进/注释修订取代的包保留，未用作最终 HTTP 候选。

直接依赖旧 `/api/<上传键>` 地址的外部消费者应改用 `/api/sys/common/static/<上传键>` 并遵循原权限。自定义公开 static-locations 须保持与上传目录分离；本次没有检查或修改生产配置。没有改变 Shiro、媒体权限、前端、数据库结构或依赖版本。

真实浏览器三角色、编辑器闭环、人工视觉、目标环境验收仍未完成；HTTPS 代理 Cookie 与 Servlet session 条件评估留作后续独立工作。PR #64 的性能基线绑定旧 #62 JAR，不能直接用作本次新包的性能结论。
