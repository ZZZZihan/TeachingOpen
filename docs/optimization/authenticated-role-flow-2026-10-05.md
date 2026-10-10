# 2026-10-05 普通认证角色链路验收记录

本轮已经在隔离的合成写环境中，通过普通登录完成学生、教师和管理员的代表性业务操作。Python、Scratch、ScratchJr 三种编辑器及文件作业共四条主链，均形成了学生提交、教师批改、学生回读的持久化记录；编辑器链另外核对了同一作品 ID 的保存、重开和后续提交。管理员四项资料维护与恢复、角色 B 的数据范围、上传及会话失败后的输入保留也有本轮实际浏览器证据。

这份记录是管理 PR #1 的最终本地候选交付记录。最后发现的真实 390px 班级成员表格末列不可达问题已由独立 PR #76 修复，并在最终构建的 390/768/1440 实际后台验证。原计划十项候选条件按声明范围完成，结论为可供小范围试用的本地候选工程条件满足；用户审美认可、真实师生试用和目标环境部署仍分别待验，不把它们与本机工程检查合并。

## 授权与环境边界

本轮已获得普通五角色登录及图形验证码操作的明确人类授权，五个合成账号分别为学生 A、学生 B、教师 A、教师 B 和管理员。浏览器操作由根 Agent 完成，使用正常登录流程；没有绕过验证码、注入登录会话或以后台 SQL 写入替代页面操作。此前审计中“验证码授权待答、真实认证链待执行”的状态属于历史记录，不能继续作为本轮的当前缺口。

两类数据环境保持分离：

- **真实私有副本只读检查**：18142 使用 2026-10-03 的 Z820 数据快照，覆盖 5 门课程、83 个单元、297 项资源。账号身份和密码已替换，没有复制真实学生作品附件。它用于课程内容和代表性媒体读取检查，不代表生产最新状态，也没有在这个副本上执行本轮学生提交、教师批改或管理员资料维护。
- **合成写环境实际操作**：18150 是本轮普通认证与写入验收入口，配套隔离的本机后端及合成数据库。五角色、课程、班级、作品、批改和上传文件均为可复查的合成验收数据。三编辑器主链需要带编辑器类型的合成单元；真实副本中的 83 个单元不能据此替代这项测试。

私有副本的范围与媒体证据见 [真实副本覆盖记录](production-copy-coverage-2026-10-05.md)。本文件只保留合成 ID、摘要、校验值和证据路径，不把私有数据库原行、账号凭据或完整配置带入 Git。

## 候选、构建与运行切换

下表绑定纳入 PR #76 产品修复后，已构建并实际切换的最终前端。后续仅文档提交不改变这些构建字节。

| 项目 | 精确记录 |
| --- | --- |
| 已构建源码候选 | `1b23551257b3f922f7fc4b125dfd9a85e5090a0c` |
| web Git tree | `4913373ff6b28dd3af0e7e7a43079475735c5d34` |
| dist | `.devspace/artifacts/authenticated-role-flow-20261005/member-scroll-final-build/dist`，4,895 个文件，211,929,947 字节 |
| dist manifest SHA-256 | `49e62b14fe9a61169a40ff67ca0348799fcd455d5eb6f1bb372aa86c20d72bc5` |
| 原后端 JAR SHA-256 | `67568eeaecea8e8d7342088767eeef2d7fcee45d61afffa0fb559b7808664016` |
| 全分支前端测试 | 688/688 通过，失败 0、跳过 0 |
| 正式前端构建 | 成功；12 项已有 warning，涉及 CSS 顺序、包体预算及旧 Browserslist 数据提醒 |
| 本机代理测试 | 上一组合版本 22 项通过，最后 CSS 修复未改代理，没有重复执行 |
| 18150 前端切换 | `2026-10-05T06:31:40.671175+00:00`，前端 PID 49600 |
| 前端代理 runner SHA-256 | `7c5e7af868c180e74d58ac218e4c9f23bf7b2aab411df47363de767800773966` |

对应私有记录为 `member-scroll-final-build/full-tests.log`、`build.log`、`dist-manifest.json` 和 `runtime-switch.json`，均位于 `.devspace/artifacts/authenticated-role-flow-20261005/`。只把 **18150 的 frontend** 切换到最终 dist；后端 JAR、API 进程、18142 和其他前端保持原运行版本。旧 dist 与进程回执保留用于恢复。

最终本地集成 HEAD 为 `4f30e51b7121b7f102cfe1c71bba3183cd21b7e2`，相对已构建 `1b235512` 只增加 PR #76 的验收文档，web tree 完全相同，无需为了文档重建。GitHub 实时核查 76 个 PR 均 OPEN，#73—#76 均非 Draft；历史 12 个 Draft 为 #19、#21、#22、#23、#25、#26、#27、#28、#29、#37、#41、#44，保留待审阅状态。除管理 PR #1 外，75 个实现 PR 的精确 head 全部是该本地候选的祖先，见 [PR 快照](evidence/authenticated-role-flow-20261005/pr-state-final-76.json)与[逐项关联](evidence/authenticated-role-flow-20261005/pr-ancestry-final.json)。没有远端合并。

浏览器证据跨越四个时点：前段业务链使用原 dist；ScratchJr 故障定位后先只切换本机 CSP 代理；随后以 `0d06bc53` 构建复核课程资料下载、上传重试、会话失败保留、主要页面三宽度及 ScratchJr 教师与学生末段；最后 `1b235512` 构建只追加成员表格 CSS 修复，实际回归了 390/768/1440 末列键盘访问和打开编辑窗口。较早链路不能因最终 HEAD 更新而追认为从头在最后构建重跑。阶段记录分别位于 `runtime-switch/csp-proxy-switch.json`、`candidate-build/runtime-switch.json`、`member-scroll-final-build/runtime-switch.json`。最后组件模板和业务脚本与前版一致，新增 CSS 与经过独立审阅的 PR #76 产品字节一致。

最终交付包保存在私有 `.devspace/artifacts/release-candidate-20261005/bundle-final-1b235512`，独立冻结工作树固定实际构建源 `1b235512`。4,895 个前端文件从实际构建 snapshot、冻结 source 到 bundle 逐文件相同；create 与 offline verify 均通过，校验了 4,906 个不可变文件。包 manifest SHA-256 为 `beb05d1aa50ea0ac0e052c95ef60cbe5c04a6bb85d17b1c5e0584c0dc08046aa`，flat dist 清单 SHA-256 为 `582ccefd1c23fe717afa9e2a4d12e124f6dbb3ad906e8198720ea5a2238295e4`。准确命令、工具/输入摘要和范围见[无凭据冻结回执](evidence/authenticated-role-flow-20261005/bundle-freeze-receipt.json)。新包没有启动服务或重跑运行探针；旧包 45/45 Linux/arm64 结果保持其历史绑定，不挪作新组合运行证据。包中的私有配置与随机凭据未提交 Git；本轮原工作树 `web/dist` 未被覆盖。

收尾只读健康检查确认原三个本机后端 18111、18149、18141 均返回 HTTP 200、UP；没有为了打包重启后端。初次冻结 HEAD 守卫因后续纯文档合入而停止，未创建部分包；按明确的实际构建源冻结后通过，失败尝试保留在私有记录。

## 四条主链及持久化结果

四条主链属于同一合成学生 A 及班级 A，各自对应正确的单元或任务。最后只读快照中，各作品均为已批改状态 `status=2`，各有一条教师 A 的批改记录；评分分别为 0、4、0、5。这里的零分是有效评分，和未评分分开呈现。

| 主链 | 合成作品 ID | 页面操作与同 ID 核对 | 最终回读 |
| --- | --- | --- | --- |
| Python | `2106979726192918530` | 首版运行输出 42，保存后重开；改为第二版后制造提交失败，代码与输出保留，恢复后重试并保持同 ID | 教师预览运行输出 42；零分批改失败时评分和评语保留，重试、重开及学生全文回读后仍为 0/5 |
| Scratch | `2106980546993045505` | 真实 VM 保存草稿，角色位置 x=100/y=0；重开后改为 x=-80/y=0，提交同一作品，分别捕获草稿 `status=0` 和提交 `status=1` | 教师预览、评分 4，学生读取评分及全文评语 |
| ScratchJr | `2106987033828114433` | 真实引擎保存“前进 5 步”草稿，重开仍为 5 步；改为 8 步后提交同 ID，分别捕获 `status=0` 与 `status=1` | CSP 修复后教师预览实际猫与 8 步积木、评分 5、390px 重开批改；学生读取 5/5 与全文评语 |
| 文件作业 | `2106983038271209473` | 教师从普通页面发布任务 `2106982552604360705`，学生上传自制文本并提交，教师下载文件与源文件一致 | 教师评分 0，学生任务页及作品反馈全文回读 |

文件作业是第四条任务主链，不是第四种编辑器；它验证发布、上传、下载、批改和回读，不宣称具有编辑器草稿重开行为。Python 当前“保存”动作同时保存并提交，本轮没有把它写成独立草稿语义。Python 首版数据库状态没有及时单独冻结，现有证据保留首版重开和附件，不能用第二版或最终已批改状态回填首版状态。

最后附件摘要如下，均来自合成环境文件的独立只读检查：

| 作品 | 字节数 | SHA-256 |
| --- | ---: | --- |
| Python 最终源码 | 58 | `79be9fe6b2aaea4a3e8b5ebb223ea0a5695b6fa27cb8f181ff339d8eaa3b637e` |
| Scratch 最终 SB3 | 1,346 | `2a5a8e898f61ff246883725ba20c5da5b3bc421007f0c1fec0ca489de8cd69b1` |
| ScratchJr 最终 SJR | 10,861 | `7debee19568dfd08c1e2ac080fc6c0a88482da74d678d2d15829bb5bfd83065e` |
| 文件作业文本 | 211 | `df3045cc28d4d653941901df7b5a638a5a9cf801cc1b95032a83703119b4c5e1` |

ScratchJr 草稿附件为 10,869 字节，SHA-256 为 `0e5a2b97d7f5fcaef4703d174b109597e14912a89e33b47bf77683ac37ae5c16`；附件内实际 `project/data.json` 的程序参数由 5 变为 8，与页面操作一致。这个证据证明保存程序并重开，不扩大为所有运行中位置、主页状态或引擎功能都已恢复。Scratch 与 ScratchJr 的教师预览截图证明实际内容可读，单张截图不证明动画实际运动或云变量行为；ScratchJr 学生创作阶段有点击绿旗后猫移动的实际观察。

页面证据集中在私有 `root-browser/` 下：`python-reopened-first.png`、`python-submit-failure-retains-code.png`、`python-retry-success.png`、`teacher-python-preview.png`、`teacher-grade-failure-retains-input.png`、`teacher-zero-grade-reopen.png`、`student-zero-feedback-fulltext.png`、`scratch-draft-success.png`、`scratch-submit-success.png`、`teacher-scratch-preview.png`、`scratchjr-draft-success.png`、`scratchjr-reopened-five-steps.png`、`scratchjr-submit-eight-steps.png`、`teacher-created-assignment.png`、`student-file-submitted.png` 和 `teacher-file-download-verification.json`。仓库精简证据包保留了 [ScratchJr 教师 390px 重开](evidence/authenticated-role-flow-20261005/teacher-scratchjr-grade-reopen-390.png) 与 [学生全文回读](evidence/authenticated-role-flow-20261005/student-scratchjr-feedback-fulltext.png)。

## 角色范围与管理员维护

学生 B 的实际作品列表只出现合成作业 B，任务范围只出现合成附加作业 B；尝试打开已知的学生 A Python 作品时无法读取，编辑器为空，提交和运行禁用。教师 B 的作品范围同样只出现合成作业 B。根 Agent 的实际页面证据为 `root-browser/student-b-own-work`、`student-b-assignment-scope`、`student-b-a-work-denied` 和 `teacher-b-work-scope` 系列。这证明本轮两组指定账号、指定记录与菜单路径的范围检查，不宣称穷尽所有越权请求、全部角色组合或所有后端接口。

管理员经普通页面修改并重开四个字段：班级备注、学生显示名、课程名称和 Python 单元简介。随后恢复选定字段，`data-observer/administrator-final-comparison.json` 的四项预期比较均通过。学生显示名、课程名和单元简介有修改前基线；班级备注的首个独立快照采集在修改后，根 Agent 记录原页面为空，最终数据库为空字符串，因此不能进一步声称已经证明原始 `NULL` 与空字符串完全相同。没有改角色授权或密码，也不把四字段恢复扩展成全库无变化。

管理员证据为 `root-browser/admin-class-memo-reopened.png`、`admin-student-name-reopened.png`、`admin-course-name-reopened.png` 和 `admin-unit-intro-reopened.png`；精简证据包另保留 [390px 课程编辑页面](evidence/authenticated-role-flow-20261005/admin-course-edit-390-final.png)。

## 实际失败、重试与保留范围

本轮通过浏览器受控故障覆盖了 Python 提交、教师评分和文件上传。Python 提交失败后编辑文本及运行输出仍在，恢复后对原作品重试；教师评分失败后零分与评语仍在，恢复后批改并重开。上传失败后选中的文件和作品名称仍可用，恢复后上传并提交成功，形成额外合成作品 `2106988920858066945`。该作品最终 `status=1`、尚未批改，只作为上传重试证据，不能算第五条完整批改主链。其 211 字节文本附件与主文件作业的源文件校验值一致。代表截图见 [实际上传失败](evidence/authenticated-role-flow-20261005/student-upload-failure-final.png)，成功恢复证据在私有 `root-browser/student-upload-retry-ready-final.png` 和 `student-upload-retry-submitted-final.png`。

普通退出登录后，仍打开的旧 Python 编辑器提交未保存修改，页面提示登录状态失效并保留代码。`data-observer/python-session-failure-comparison.json` 核对该作品选定字段、关联文件记录及已有批改记录没有被这次失败提交改写，最终源码仍为上述 58 字节及相同 SHA-256。它没有检查整个数据库或断言没有审计写入。截图见 [会话失效后保留代码](evidence/authenticated-role-flow-20261005/python-session-ended-retains-code.png)。

根 Agent 已将网络故障拦截恢复为空数组 `[]`，关闭旧故障编辑器页签。四条主链及额外上传重试记录保留供用户复查；管理员选四字段已恢复。最终网络拦截为空，浏览器视口已复位，管理员经正常注销回到游客首页；记录在 `root-browser/browser-cleanup-final.json`。旧资料失败标签受浏览器策略限制未能手动选择关闭，未绕过限制，不影响业务验收。这里不宣称已删除验收业务记录，也不把保留记录写成已经回滚全库。

条件 5 要求具备清理能力，不要求删除所有演示记录。正常清理的历史证据包括 PR #12 的 134/134 检查，覆盖授权删除及持久化；PR #13 的 41/41 检查，覆盖最后引用文件回收、失败回滚与重试、原行和文件字节恢复；PR #14 又执行同包 41/41 检查。这些按各自历史声明范围记录，本轮没有重复执行全部清理路径。保留四条主链和上传重试作品供复查，不因此另列候选硬门未完成。

## 四项独立修复 PR

本轮真实链路暴露的问题分别形成独立 PR，便于审阅。没有远端合并；本机候选组合及其运行切换与 PR 的提交状态分开记录。

| PR | 精确 head 与 base | 修复及证据 |
| --- | --- | --- |
| [#73 修复课程资料静态前缀重复](https://github.com/ZZZZihan/TeachingOpen/pull/73) | head `6ec6bfb31e3cb6a529f15dd7c158d544df6932dc`；base `fix/student-work-loading` | 课程资料已是根相对静态 URL，前端再次拼接造成重复前缀。修复后实际浏览器下载 91 字节，与源文件一致；独立针对性测试 21/21。根因及前后证据为 `data-observer/material-url-source-diagnosis.json`、`python-second-submit-counts-and-material-status.json` 和 `root-browser/course-material-fixed-download.json`。诊断时匿名 GET 的 401 不当作已登录用户权限失败。 |
| [#74 修复登录后页面标题和默认品牌标识](https://github.com/ZZZZihan/TeachingOpen/pull/74) | head `cb7bfda2d2c4b6c46f853816b638ba0dbcd4c115`；base `fix/student-work-loading` | 真实外壳原标题出现“我的课程 · undefined”。共享缺省品牌改为天津工业大学与人工智能教学平台，有效配置优先，中性缺省头像；补充缺域名、空配置、相对头像及合法 IPv6 完整 URL 边界。独立测试 44/44。前后为 `root-browser/student-course-shell-before.png` → `student-shell-wide-final.png`，产品及图片冻结清单 SHA-256 为 `dc5ccc4c5f5463af979a5cf27d9555584ce6512d0c3014bde33a9b7b3a8156b7`。没有扩改主题、权限或配置侧栏。 |
| [#75 Fix local ScratchJr project Blob loading](https://github.com/ZZZZihan/TeachingOpen/pull/75) | 产品修复 head `68af0db5cc50d643234360c35cb7f305c2113cfc`；追加文档后的 PR head `fd6d2dcec0b808dac12ec9b1bb9a557cc5f03556`；base `fix/local-proxy-head` | 本机 `/scratchjr/engine.html` 的精确 CSP `connect-src` 增加 `blob:`，`script-src` 等其他规则保持原边界。独立受控代理测试 6 项，组合代理测试 22 项。前后为 `root-browser/scratchjr-real-course-timeout.png`、`teacher-scratchjr-preview-before.png` → `teacher-scratchjr-preview-ran.png`，并有草稿、重开、提交证据。现为 Ready；修的是本机开发代理，没有宣称生产服务器 CSP 已更新。 |
| [#76 修复手机班级成员操作列不可达](https://github.com/ZZZZihan/TeachingOpen/pull/76) | 产品 head `eb8715022016b76074e500fdce5017d81cb551cd`；最终仅文档 head `47549b7d9d8518c955ef124a9457779d179ad682`；base `fix/class-membership-layout` | 四行局部 scoped CSS 修复全局最小宽度造成的嵌套滚动；旧 4/7、新 7/7，成员相关 71/71，独立编译级联 12/12。最终真实后台三宽度可到操作列，390px 实际编辑窗口打开后取消。现为 Ready。 |

PR #74 的初稿曾在空配置相对头像路径上复现异常，后续普通追加提交修复；合法 IPv6 URL 的处理也纳入回归。PR #75 的诊断、交付范围和失败记录保留在私有 `junior-diagnosis/REPORT.md`、`delivery.json`。这些都保留“先复现、再修复”的事实，不只展示成功截图。

## 真实外壳、视觉与成员表格修复

`0d06bc53` 构建后，在实际 CSS 视口 1440、768、390 下检查了课程阅读器、学生个人中心、教师作品列表和管理员课程页。各页面未产生页面级横向溢出；相应 JSON 记录了实际 `innerWidth` 与文档宽度，而不是把浏览器 110% 缩放后的外层请求尺寸直接当作 CSS 宽度。学生个人中心标题已经显示“个人中心 · 天津工业大学 · 人工智能教学平台”。私有记录为 `root-browser/course-reader-viewports-final.json`、`student-center-viewports-final.json`、`teacher-worklist-viewports-final.json` 和 `admin-course-viewports-final.json`；仓库精简包保留 [本轮候选页面](evidence/authenticated-role-flow-20261005/candidate-home-final.png) 与 [管理员 768px 页面](evidence/authenticated-role-flow-20261005/admin-course-768-final.png)。

随后在真实 390px 班级成员页发现键盘到末列的缺陷，证据为 `root-browser/admin-members-keyboard-390.json`、`admin-members-keyboard-end-before.json`，以及仓库中的 [修复前末列截图](evidence/authenticated-role-flow-20261005/admin-members-keyboard-end-before.png)。根因是全局移动样式仍强制 `.ant-table-body` 最小宽度 800px，旧页面外层只有 310px，内层滚动最多约 121px，键盘到头仍看不到操作列。PR #76 仅在成员表格增加四行 scoped CSS，取消这一局部最小宽度并限制为容器宽度，未修改模板、业务脚本或其他表格。

最终实际后台复验：390px 时 body 宽 310px、内容宽 921px，8 次右方向键到约 610.45px，操作列完整进入视口，并实际打开学生编辑对话框后取消；768px 时 body 宽 377px、滚动约 543.64px；1440px 时 body 宽 769px、滚动约 151.36px。三个尺寸外层宽度均等于自身内容宽度，不再形成隐藏的第二层横向滚动。截图为 [390px 修复后](evidence/authenticated-role-flow-20261005/admin-members-keyboard-end-after.png)、[768px 修复后](evidence/authenticated-role-flow-20261005/admin-members-keyboard-768-after.png)、[1440px 修复后](evidence/authenticated-role-flow-20261005/admin-members-keyboard-1440-after.png)。

作者同一回归旧 4/7、新 7/7；成员相关检查共 71/71。独立审阅者对真实 Less/scoped 编译和级联的独立探针 12/12，另执行作者 7/7 和既有 64/64；最终产品提交 `eb8715022016b76074e500fdce5017d81cb551cd` 与候选文件逐字节相同，没有阻断项。既有组件 lint 的 54 errors/289 warnings 与基线一致，不写成 lint 通过。最终全量前端 688/688、构建退出 0，本轮条件 6 的工程缺口关闭。

天津工大默认品牌、文字可读性、响应式尺寸与键盘操作属于工程证据。用户对审美风格的认可仍单独待记录；本稿没有把 Agent 自检或截图存在升级为用户认可。配置侧栏曾在可访问性树中出现，但截图未证明它实际外露，不据此扩大成新修复。

## 证据强度与收尾判定

根 Agent 的浏览器记录证明普通认证后的页面操作；数据观察者通过只读事务和附件读取，独立核对指定记录、同 ID、状态、评分、关联文件及校验值；源码审阅者对 PR #73/#74/#75/#76 的冻结字节执行针对性 Node/Python 检查。这三类证据互相补充，任何一类都不替代另外两类。附件读取与 SQL 快照不是跨资源原子快照，本轮也没有外部复现或生产容量测试。

私有 `data-observer/final-index.json` 的冻结时点为 `2026-10-05T06:14:28.895165Z`，SHA-256 为 `5d703cbbfdf5130ce47112c64fc9749859a11aa28a3292dbade888d4b6f27a75`。它汇总上述四条主链最后状态及其证据索引；观察范围见 `data-observer/README.md`。独立源码审阅摘要 `independent-review/review-summary.json` 的冻结 SHA-256 为 `5eabe4fb29b594664a6808735319bfdeb8694f4ad0cc80d9f753979af4af62ec`，当时没有剩余的 PR #73/#74/#75 产品字节阻断项。

链路最终独立审阅记录为 `independent-review/role-chain-review.md`，SHA-256 `e4dd9dc34e21274231a45e877f47a9b6bbcf56272af67699777f3016126284b2`。审阅者查看了 53 张实际像素截图（证据项数，不是测试项数），确认本轮代表链及最后 UI 修复范围内没有尚未修复的明确阻断；成员表格源码独立窄审阅为 `member-scroll-review/review.md`，该源码报告 SHA-256 为 `b4d8889ffdd74e7f892661c67337c0b3bf245c754663546a0f452146db229874`。它们与根实际浏览器验证、数据观察各自署明范围，均不称为用户人工验收。

管理 PR #1 的仓库证据包位于 [精简组合证据目录](evidence/authenticated-role-flow-20261005/)。其中[精确候选摘要](evidence/authenticated-role-flow-20261005/candidate-final.json)绑定最终 source/build 与 12 张选定合成截图；完整 observer 原行、原配置及浏览器私有资料仍留在 `.devspace/artifacts/authenticated-role-flow-20261005/`，以路径和冻结哈希追踪。

## 原十项条件的最终判定

本表依据原计划，不追加必须生产上线的条件，也不把历史检查包装成最终版本重复执行。

| 条件 | 本地候选结论与证据 | 保留边界 |
| --- | --- | --- |
| 1 构建与隔离复现 | 已完成。前端既有干净安装记录及最终 688/688、成功构建；[本轮空 Maven 缓存构建](completion-audit-2026-10-05.md)退出 0，208 外部库、945 应用文件、111 内部模块文件内容与运行包一致；隔离初始化/启动工具已交付。 | Java 测试仍被父 POM 跳过，不能称 Java 单测全绿；JAR ZIP 元数据不完全可重复。 |
| 2 学生流程 | 已完成代表链。普通登录、课程/单元、视频播放与定位、三个编辑器保存/重开/同 ID 提交、教师反馈回读均有实际 UI 与选定数据记录。 | 声明的合成课程与账号范围，无真实学生作品。 |
| 3 教师/管理员 | 已完成。教师 A 四条主链预览批改、教师 B 范围；管理员班级、用户、课程、单元四字段维护与重开恢复。 | 未增加教师授权；班级备注原 NULL 与空串不作等价全库证明。 |
| 4 权限/数据 | 已完成约定范围。[先前后端审计](evidence/completion-audit-20261005/backend-review/review.md)、课程/作业/私有附件允许和拒绝回归，以及本轮 B 账号页面拒绝、失败后选定记录不变。 | 不是对全系统所有组合的穷尽证明。 |
| 5 异常与清理 | 已完成。实际上传/提交/批改失败可恢复，会话退出后保留代码，同 ID 提交无重复；正常清理能力引用 #12/#13/#14 的原始检查。 | 四条主链与上传重试记录保留供复查，没有声称本轮全库回滚。 |
| 6 UI | 已完成工程检查。天工品牌、主要页面三宽度、错误/空/忙状态；#76 最终真实后台键盘末列和编辑入口通过。 | 用户对美观程度的认可仍待评阅。 |
| 7 媒体/创作 | 已完成保留的核心承诺。Scratch、ScratchJr、Python 均实际打开、修改、保存、重开、提交；文件作业另列第四主链。 | Python 保存同时提交；复杂项目、七牛及云变量等未覆盖能力不扩大宣称。 |
| 8 运行/恢复 | 已完成本地范围。#33/既有基线、[#51 页面预取优化](evidence/product-candidate/frontend-prefetch-candidate.json)、[#64 私有副本读取基线](evidence/product-candidate/production-read-benchmark-candidate.json)，以及 [#30 备份恢复](evidence/product-candidate/backup-restore-candidate.json)、[#31 切换与回退](evidence/product-candidate/candidate-switch-candidate.json)保留精确环境和历史绑定。 | 历史结果不是本轮重跑，不等同生产容量或灾备承诺。 |
| 9 依赖/发布条件 | 已完成核查和状态记录。[实际依赖及一手公告审阅](evidence/dependency-release-20261005/review.md)、资源入口 #65 修复和真实副本/生产定制差异已记录。 | Spring/Boot/Shiro/Vue 维护债务、实际 TLS/可信代理、Z820/Linux 目标部署及真实试用仍待。 |
| 10 PR/交付 | 每个实现结果有独立 PR，最新 #73—#76 已交付；最终源码、构建、JAR、代理、包和 PR head 由精简冻结记录绑定。 | 远端 PR 保持未合并，历史 Draft 状态保留；本地集成与 GitHub 合并分开。 |

最终本地候选可由用户小范围试用；工程自检、独立 Agent 审阅与用户/课堂/生产验收分开。不存在因剩余部署或用户审美状态而继续无限加补丁的理由；后续新问题继续独立 PR 管理。
