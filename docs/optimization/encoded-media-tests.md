# 百分号媒体引用专项测试

该专项已完成同一最终脚本、同一期望的双包真实运行：旧 PR #56 **83/113**，候选 **113/113**。30 项合法编码引用从失败变为通过，没有原通过用例回退。[对照汇总](evidence/encoded-media-references/comparison.json) 核对了脚本 SHA、有序用例名、期望状态与期望字节哈希完全相同。合法 `%2B` 引用的旧 401 记为缺陷；候选返回 200 且对应 PNG 字节完全一致。

该专项使用真实本地 HTTP、数据库关系和不同的 PNG 字节，验证合法百分号 URL 引用能取得对应附件，并保留当前角色、班级、可见性、发布状态及精确文件边界。

执行范围是唯一隔离 runtime `.devspace/encoded-media-1003`，MySQL / Redis / backend / frontend 端口分别为 `13369 / 16442 / 18171 / 18172`，HTTP 实际直连 `127.0.0.1:18171`。当前运行配置的 `jeecg.path.staticDomain=/api/sys/common/static` 是相对 URL，因此“同源引用”按该配置拼接路径；绝对外域 URL 按已有契约拒绝。脚本不启动、停止或切换服务，不登录浏览器，不执行生产操作。

最终脚本 [verify-encoded-media-references.py](../../api/dev/verify-encoded-media-references.py) 的 SHA-256 为 `f97fa6e661460da30a80c0e582cf150795823c8775207ae66c491189b46663d9`。冻结副本与依赖清单见 [probe-corrected.py](evidence/encoded-media-references/probe-corrected.py) 和 [test-source-inventory-corrected.json](evidence/encoded-media-references/test-source-inventory-corrected.json)。该修订保留 113 项行为期望，只修正本机大小写别名覆盖夹具。此前的 `8f1e323…` 版本也保留为 [probe.py](evidence/encoded-media-references/probe.py) 和 [原依赖清单](evidence/encoded-media-references/test-source-inventory.json)。不修改此前已冻结的 Unicode 主测试。

旧 PR #56 基线 JAR SHA-256 为 `95d9ad3ad4ada70897974071fec283a0c29bb703e2cdcb41397e80f77ebbd7c7`。[最终修订基线](evidence/encoded-media-references/baseline-corrected.json) 为 **83/113**，执行错误为空，30 项失败均为期望允许的合法编码引用。原始用例 `<img src="…/original%2Bcover.png">` 的真实结果为 401，而同一 PNG 改为字面 `+` 引用后为 200 且返回预期全部字节。该对照也存放在报告的 `observations` 中。较早 `8f1e323…` 版本的 [首轮完整基线](evidence/encoded-media-references/baseline-final.json) 同样为 83/113，仍保留原记录。

候选 JAR SHA-256 为 `4578567dcedc18bf8a5f69758f8209d9b7bc74fc24f24f0d50196ec97e684c42`。[修订夹具后的候选](evidence/encoded-media-references/candidate-final.json) 为 **113/113**，执行错误与清理错误均为空，原 `%2B` 引用返回 200 且字节精确一致。与最终修订基线使用完全相同的 `f97fa6…` 脚本。较早的 `8f1e323…` 两包记录作为原始过程证据保留，不混入最终同源码对照。

候选在 [原冻结夹具](evidence/encoded-media-references/candidate.json) 下首次为 112/113，唯一失败 `boundary valid encoded exact key` 返回 200，但字节哈希不同。专项用 [文件系统诊断](evidence/encoded-media-references/fixture-filesystem-diagnostic.json) 实测确认本机 `exact+name.png` 与 `EXACT+name.png` 是同一设备 / inode，目录实际只有一个文件，大写路径写入覆盖了目标；覆盖后的哈希 `a874f6…` 与该失败响应完全一致。该失败归因于夹具，原报告仍保留。修订只保留目标实际文件，把大写拼写作为引用及请求 key 验证精确大小写拒绝，并为新增夹具设置已有路径禁止覆盖守卫；没有放宽状态或字节期望。

首轮运行先抓到了同一 `%2B` 401 / `+` 200 对照，随后测试夹具对空字符串生成了无效 `CONVERT(0x USING utf8mb4)` SQL，导致中断。修正只涉及新测试脚本的空字符串 SQL 字面量。[首轮原始报告](evidence/encoded-media-references/baseline.json) 与 [初版源码](evidence/encoded-media-references/probe-initial-error.py) 已保留，首轮为 9/11，包含夹具执行错误，不能用作完整基线。两轮都完成了自己的清理；完整基线另用新文件名保存，没有覆盖旧证据。

覆盖用例按以下行为设置有限断言：

- 引用表示：`%2B` 大小写、字面 `+`、`%20` 空格、中文百分号大/小写、可选 unreserved 字符编码（`%66`、`%73`）、混合原字符与百分号、原始存储 key、配置同源路径、HTML `src` / `href`、普通 JSON 字符串。
- 文件身份：加号与空格两个文件具有不同字节；`%252B` 只解码一次，取得实际文件名中含字面 `%2B` 的 PNG，不能取得加号邻居；反向 `%2B` 引用不能取得字面百分号邻居。
- 资源关系：公开课程封面、私有单元 JSON 视频字段与 HTML 富文本、隐藏视频 / 教案、附加作业链接及 JSON 文档、启用配置 HTML / JSON、发布资讯 JSON / HTML，以及原始 key 的已登记作者附件。
- 认证与权限：五个真实合成账号的登录和动态配置媒体 cookie；作者 / 本班教师 / 本班学生在适用资源中的允许行为，跨班教师 / 学生及匿名拒绝；代表用例的 GET、HEAD、Range，cookie 单独认证，账号禁用 / 恢复、实际退出后旧 token 与 cookie 撤销。
- 状态变更：撤回首页公开、删除课程、隐藏 / 删除单元、关闭 / 重新分配附加作业、禁用配置、资讯转草稿、作品发布后撤回。附加作业关闭后本班教师继续可读，与当前管理权限契约一致。
- 精确引用拒绝：外域同路径、raw key / URL 中仅包含目标的子串、更长文件名、大小写不同的引用 / 请求 key、其他文件名、无效百分号语法；有效目标引用也不能授权大小写别名或两个不同字节的邻居。
- UTF-8 边界：实际 `�` 文件名的合法 `%EF%BF%BD` 引用必须读到精确字节；stored `%FF`、截断 `%E4%B8`、surrogate `%ED%A0%80`、overlong `%C0%AF` 不能借 Java URI 解码替换字符授权实际 `�` / `��` 文件。

每轮运行先取得所有 69 张表的完整行哈希与结构哈希，原始五个用户的每个字段只保留在内存。退出测试登录后删除唯一命名空间的行，恢复五个用户的全部字段，并移除自己的附件目录。最终修订双包均确认全部 69 个结构哈希（含 `sys_log`）一致、68 张非日志表的完整行内容一致、附件字节 / 目录 / 模式 / 链接清单一致，清理错误为空；正常认证所增加的 `sys_log` 行保留。文件系统诊断也单独比较并恢复全部附件清单。所有运行报告及初版夹具证据均保留，未覆盖旧失败。

最终执行顺序是先修订候选 `candidate-final.json`，再由主 Agent 独占运行相关模块回归，随后主 Agent 切回旧 PR #56 包，专项用完全相同的修订源码运行 `baseline-corrected.json`。先候选后基线的实际顺序与 UTC 时间均记录在对照汇总中。专项结束后已退出测试登录、释放锁、复核恢复并归还运行窗口；服务切换和最终停止由主 Agent 完成。

这些结果仅证明报告所列真实本地合成行为。任意 HTML entity 表示、JSON Unicode escape 表示、前端代理、可播放视频、候选 SQL 查询性能、容量、生产部署和人工验收均不在本专项断言范围内。
