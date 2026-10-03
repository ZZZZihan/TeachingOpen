# 中文媒体路径 HTTP 验证

本项验证合法中文媒体路径的真实 HTTP 行为。旧包实际接受中文上传目录并登记了文件，但随后拒绝返回路径的媒体读取；现有私有生产副本的 297 个媒体路径均为 ASCII，因此这里不声称已修复那 297 个文件，也不把它们作为中文路径复现材料。

## 环境与证据边界

唯一运行环境为项目 `.devspace/unicode-media-1003`，MySQL/Redis/后端/同源代理端口分别为 `13368/16441/18169/18170`。数据库名为 `teachingopen_dev`，仅含五个 `fixture_*` 合成账户。脚本先核实运行进程、指定 JAR 摘要、本地配置、MySQL 数据目录及端口、Redis 数据目录，再使用独立随机 `fixture_ump_*` 前缀创建夹具。

`api/dev/verify-unicode-media.py` 不启动或停止服务。登录与验证码读取仅通过现有 `FixtureApi` 在独立 CLI 合成环境中执行，没有浏览器注入令牌或验证码。HTTP 客户端 `http.client` 保留原始 ASCII 请求目标和百分号编码，以便异常路径不会先被客户端自动规范化。

结果仅证明本地真实 HTTP、数据库和附件恢复范围；同源代理的 HTTP 成功不是浏览器渲染、三角色人工验收、可播放视频、容量或生产交付证据。图片夹具是有效 2×2 PNG，并按完整字节及 SHA-256 核对；`course_video` 字段使用 PNG 夹具核对媒体授权与 Range 契约，没有以此声称验证视频容器、解码器或播放体验。

## 同一组期望行为

旧包与候选包使用相同脚本、相同期望断言。基线失败保留为失败，没有 `--expect-legacy` 将缺陷改作通过。

- 合法中文目录、中文文件名、根目录中文名、中文多点扩展名，以及空格、加号和字面百分号的既有路径行为。首页课程封面使用匿名 GET、HEAD、Range；私有作业和单元媒体使用作者、本班教师、管理员、匿名和跨班账户。
- 实际 multipart `biz` 与 `bizPath` 中文目录上传。上传后按完整文件字节、精确 `sys_file.file_path`、原始显示名称、归属人、存储位置、删除状态核对；随后验证返回路径的 GET、HEAD、Range、本班教师读取、跨班拒绝及匿名拒绝。
- 全部允许读取核对实际正文、`Content-Length`、MIME、`Cache-Control: no-store`、`nosniff` 与 `filename*=UTF-8''...` 的 `Content-Disposition`。Range 核对 206、实际切片和 `Content-Range`；HEAD 要求空正文、完整文件长度、不输出 `Content-Range`。
- 课程 raw key 与编码的同源 URL 引用；单元的编码富文本图片引用。精确匹配的权限允许与外域 URL、子串引用、删除课程、删除单元、隐藏视频的拒绝分别验证。
- 媒体 cookie 单独读取、header 优先级、畸形 header 不回落到 cookie、公共资源携带畸形 token、冻结账户及恢复、实际退出后的旧 token 和旧 cookie。cookie 名从该隔离环境配置读取，避免与其他环境同主机端口的 cookie 混淆。
- 分号、反斜杠、点段、父段、百分号编码点段/斜杠/反斜杠、双编码、NUL/LF/DEL/C1、非法 UTF-8 continuation/overlong/surrogate/out-of-range/truncated 及非法百分号转义。每类异常路径验证 GET、HEAD 和 Range 拒绝，同时要求不返回目标或邻居的文件正文、不泄漏 `Content-Range`。初版另将重复斜杠的空路径段规定为拒绝；真实候选运行和后续授权矩阵表明，此预设不符合框架将重复斜杠规范化到同一资源的现有契约，具体分类见下文，原断言和失败保留。
- 全角斜杠、除号斜杠、全角点、全角分号仅验证未知 key 不会变成真实路径的别名。这些字符本身并不一概视为非法；实际全角字母文件名另有独立允许读取和不同正文校验。
- 中文最终组件的内外符号链接及中文中间目录符号链接，即使管理员请求也不读取链接目标。ASCII 大小写变体不能借数据库不区分大小写的排序规则获得另一精确 key 的权限。
- 18170 同源代理的匿名中文公共封面 GET、HEAD、Range，以及 cookie 单独授权的中文私有 PNG 实际正文。

权限状态依据当前实现：匿名没有有效引用时 401，已登录但没有引用/归属权限时 403，下载存储边界或不存在文件时 404。异常路径可能由 Tomcat 或 Shiro 提前拒绝，也可能经过错误分发，因此异常路径只接受现有契约的 400/401/403/404 拒绝结果，不把最终 401 都解释成媒体授权问题。

## 恢复核对

运行前对全部 69 个表做完整行内容 SHA-256 和 `SHOW CREATE TABLE` 摘要；逐字段用 `HEX(CAST(... AS BINARY))` 编码，排序完整行后计算摘要，保留行数作为辅助信息。运行后逐表比较原始行内容、表定义及表集合，正常 `sys_log` 登录/操作审计增量单独排除。登录初始化的 `sys_user.org_code` 和冻结测试状态等字段，在内存保存完整原始五用户行并逐字段恢复，不能只恢复状态或只比较行数。

附件清单包含每个目录、普通文件、符号链接及权限模式；普通文件比较长度和 SHA-256，链接比较目标且不跟随。最终删除仅本次随机命名空间内的业务记录与附件，并注销所有合成账户。证据文件记录允许保留的 HTTP 头、状态、长度、正文摘要和表摘要，不包含令牌、密码、验证码、业务正文或 SQL 错误细节。

## 实际运行记录

旧包摘要：`bca9e5c8f1aa78ab536901e92e2ae3d96433ad0eb4c7599bdaf12174c2c785af`。

候选包摘要：`95d9ad3ad4ada70897974071fec283a0c29bb703e2cdcb41397e80f77ebbd7c7`。冻结主脚本摘要：`3bac3af26370e5313c256b6d16813889a38daebaf683a591d8159e4382657f25`；`baseline-final.json` 与 `candidate.json` 记录的脚本摘要、186 个 case 名及断言完全相同。

| 证据 | 结果 | 含义 |
| --- | --- | --- |
| [core-baseline.json](evidence/unicode-media/core-baseline.json) | ASCII 课程封面 200 且实际正文正确；中文课程封面 401 且未回目标正文 | 首个最小真实复现，已确认全部业务行/表定义和附件恢复 |
| [baseline.json](evidence/unicode-media/baseline.json) | 初次 112/186 | 保留初次结果；含探针默认 cookie 名误设，以及合法 `%2B` URL 引用的既有候选查询不匹配问题 |
| [baseline-final.json](evidence/unicode-media/baseline-final.json) | 118/186 | 修正动态 cookie 名；加号引用使用现有 `UriUtils.encodePath` 对应的字面加号方式。68 失败包括中文允许读取、应为 403 的跨班请求及应为 404 的中文符号链接被旧包提前拒绝；两种实际中文上传均成功，后续读取失败 |
| [candidate.json](evidence/unicode-media/candidate.json) | 182/186 | 中文读取、真实上传闭环、后端 HEAD/Range、实际 PNG 字节、`Content-Disposition`、角色/cookie/冻结/退出权限、危险路径和符号链接均符合期望；保留代理 HEAD 与三项重复斜杠严格拒绝断言的失败 |
| [independent-candidate-observations.json](evidence/unicode-media/independent-candidate-observations.json) | 重复斜杠授权与字节身份 18/18；另 4 条事实观察 | 独立于主脚本：匿名及跨班仍拒绝；授权者得到同一资源正文/切片、不返回邻居正文；合法 `%2B` 仅引用仍 401，字面加号对照 200；ASCII HEAD 后端 200、现有代理 404 |
| [independent-observations-initial-error.json](evidence/unicode-media/independent-observations-initial-error.json) | 首次独立补查夹具失败 | 首次 `teaching_work` INSERT 漏了必填 `create_time`，没有把该探针错误作为产品缺陷；执行 `finally` 清理后补字段重试 |
| [independent-restoration-verification.json](evidence/unicode-media/independent-restoration-verification.json) | 所有恢复对照通过 | 独立补查两次尝试后的 69 表完整业务行与结构（除 `sys_log`）及全部附件清单，与主候选运行结束时完全相同；锁已删除 |

三个基线、主候选与最终独立补查的业务行/表结构及附件恢复比较均通过。证据、交付脚本与本文的本机摘要见 [manifest.json](evidence/unicode-media/manifest.json)；该清单不包含凭据文件或原始业务行。

主候选四项失败如实保留：

1. 同源代理的中文公共 HEAD 返回 404 `text/html`，旧包和候选的该 case 都为 404，响应声明长度同为 460。直接后端 HEAD 已为 200、无正文且提供真实文件长度。独立 ASCII 对照也是后端 200、代理 404。当前 `serve-frontend.py` 仅将 `do_GET` 的 API 路径转发，未定义 `do_HEAD`，因此这项是已有本地代理工具问题，需独立修复，不能称为本项中文后端修复已使代理 HEAD 通过。
2. 重复斜杠的 GET、HEAD 与 Range 被预设为必须拒绝，候选却返回同一已授权文件的 200/200/206。随后完整 18 项矩阵确认：匿名 401、跨班学生和教师 403；作者、本班教师和管理员仍分别获得同一目标文件的完整字节、空 HEAD 正文或正确切片，没有邻居正文。这里应保留框架规范化后的权限和字节身份契约，不把合理允许结果解释为越权，也不静默改旧证据或宣称原 186 项全部通过。

本项仍以 **182/186 原始冻结断言 + 18/18 独立授权/字节身份补查** 报告，不按分类重新计算一个“全绿”比例。现有代理工具问题、合法 `%2B` 引用兼容缺陷和重复斜杠的断言预设分别说明，不混为产品失败或已修复成果。

## 单独保留的编码引用问题

`%2B` 是合法的 URI 加号表示。初次基线将 `plus+name.png` 的引用 URL 写成 `plus%2Bname.png` 后，旧服务的 `candidates()` 查询没有检索到该引用，匿名请求返回 401。此问题与中文请求被全局 Shiro 检查提前拒绝不同；本项主断言按现有 `UriUtils.encodePath`（保留路径中的字面加号）的输出建立引用，初次合法 `%2B` 失败仍保留，不能称为输入无效或已经修复。

候选包独立观察已确认：只注册 `%2B` URL 引用时仍返回 401、未返回文件；改为字面加号引用后，同一个 GET 返回 200 和正确 PNG 字节。本项没有修改该引用候选查询，因此合法 `%2B` 引用的旧/新失败均保留为独立兼容缺陷，不纳入主检查通过数。其他 URI 表示等价性、任意 Unicode 规范化、全部字符枚举及所有可选资源模块没有穷举覆盖。

## 复跑命令

由协调者启动并确认对应 JAR 的隔离环境健康后，在该工作树执行；输出文件必须是新名字，既有证据不覆盖。

```sh
python3 api/dev/verify-unicode-media.py \
  --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/unicode-media-1003 \
  --jar /path/to/the-confirmed-candidate.jar \
  --label candidate \
  --output docs/optimization/evidence/unicode-media/candidate.json
```

运行时协调者须独占该环境，避免其他 HTTP 登录、SQL 写入或套件污染恢复对照。主脚本验证此前拒绝结果是否保持；它不会自动更换 JAR、重新启动服务或执行部署。

独立补查最初在 CLI here-document 中运行；已整理为同一文件/权限/恢复逻辑的 [verify-unicode-media-observations.py](../../api/dev/verify-unicode-media-observations.py)，作为后续可复跑入口。该整理后的文件通过 `py_compile`，未在归还运行环境后重新执行；上表 18/18 属于保留的真实 CLI 补查结果，不把整理文件的语法检查替代为一次新的 HTTP 执行。

```sh
python3 api/dev/verify-unicode-media-observations.py \
  --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/unicode-media-1003 \
  --jar /path/to/the-confirmed-candidate.jar \
  --output docs/optimization/evidence/unicode-media/observations-fresh.json
```

该脚本将 18 项重复斜杠权限/字节身份核对与 4 条兼容性观察分别记录，退出码只评价 canonical 权限/字节身份、执行错误和恢复状态。即使退出码为 0，也不能解释为 `%2B` URL 引用或代理 HEAD 已修复；必须同时阅读 `observations` 中的实际状态。
