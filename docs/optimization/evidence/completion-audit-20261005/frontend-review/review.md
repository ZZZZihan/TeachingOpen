# 前端完成条件只读审计 · 2026-10-05

本次审计的结论是：候选已有相当完整的局部工程能力与明确证据，当前不能把条件2、3、7记为完整满足；条件5、6仍缺对应普通认证外壳中的组合检查。未发现有证据支持、现在必须先另做一个局部修补才能开始整链验收的前端工程阻断。最有价值的下一步是沿已准备的三角色夹具执行真实页面闭环，出现真实可复现问题后再实施修复。继续新增组件 harness 或重复 API 上传，无法替代这一步。

用户审美认可与目标部署/TLS是独立状态，不能自动升格为必须通过的本地候选完成条件。本报告把它们列为待办，不以“用户尚未赞同外观”或“尚未生产上线”单独否定候选。也不把未验收能力推断为已损坏。

## 本次核对范围与来源

候选工作树为 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate`，实时HEAD确认 `06ab2040780f33296e93c97d29d00e80cbcc2f65`。完成契约位于 E01 第69–80行，审计只涉及2/3/5/6/7。当前聚合记录 E02将实际测试/构建提交 `872109fd…` 与最终HEAD的api/web同字节关系明确记录；本次只读核对现有记录和源码，没有再次构建或重跑645项。

当前产物的历史执行绑定为 JAR `67568eeaecea8e8d7342088767eeef2d7fcee45d61afffa0fb559b7808664016`、4895文件dist清单 `9f9a89fb12fc2a3c674988059c86665bcc0a80617bd53b8445f996708b5929da`。三代理24份初始资源一致与18142匿名首页三课程，是上轮root实际检查的结果，本次没有再次HTTP核验其在线状态。

本次文件摘要核对：E11的10份实际测试来源、E30的3份产品+2份probe，共15/15当前同字节，结果见 `source-check.json`。这支持局部证据的源码继承，不能替代同一候选运行验收。39个证据文件的准确绝对路径、SHA256和scope见 `evidence-index.json`。旧测试分母保持各自归属，不相加为一个“总通过”。

工作树事先已有未跟踪 `.playwright-cli/` 与 `output/`，保留原样。全程仅文件读取和在新审计目录写报告：没有浏览器、真实HTTP、数据库、服务操作、验证码填写、令牌注入、产品修改、commit或PR。

## 条件2：学生学习到反馈完整链

**状态：局部正证充分，整链缺失。**

- 当前能力：真实 `/account/mineWork` 表格和 `/account/center → Index → page/MineWorks` 卡片均接入共享教师反馈和局部列表恢复。源码接线已核查；E11当前10份源字节相同。E08实测零分、仅评语、未评分/无评语、长文本、HTML字面文本及键盘开全文，E09/E10实测读取失败、retry、未提交条件不应用、迟到响应、空页分页和反馈恢复。均使用真实Vue/AntD，却明确是普通合成容器/只读合成HTTP，无平台会话。
- 历史正证：E06/E07用真实Z820私有副本资产和实际UnitViewModal/JModal完成5视频起播/拖动/结束/切页关闭、2PDF首屏、1MD字节一致，覆盖3门有单元课程。211/211媒体元信息通过，86图片仅清单。学习记录为内存适配、素材URL为loopback只读适配；没有登录、受保护媒体路由或学习日志持久化，不能称实际学习链已完成。E21真实任务页面+提交弹窗的上传/提交/反馈/零分/重试，同样是合成HTTP。
- 真正缺失：普通登录之后从实际菜单找到课程、进入真实单元、播放/拖动同一资源、进入三编辑器实际修改、真实保存、关闭后从实际个人中心/表格重开、提交，教师对这些同一workId批改，学生再次从实际页面读到持久化评分/评语。当前没有把浏览器动作、真实API返回/数据ID与重开内容接成同一证据链。
- 下一安全动作：使用E03现成五账号真实菜单和三单元夹具，不再增加准备工具。待之前验证码操作确认得到回答后，由root沿该清单执行普通登录验收。本轮授权仅审计，因此这里不操作认证或数据。

E03清单有两项已经被后续产品改变的历史描述，应在执行时按当前源码记录：课程作品评语现在通过摘要/全文按钮可读，不能继续用“只有tooltip”描述；Python保留保存/提交而没有独立草稿按钮。无需为这些描述差异改产品或新建一套清单。

## 条件3：教师、管理员实际维护链

**状态：真实接口与组件分别成立，普通认证角色链缺失。**

- 教师：E12记录真实Vue/AntD工作台的25项交互，包括查询快照、失败清旧行/重试、评分读取失败不能覆盖、讨论独立错误、零分保留、512字评语、重复保存互斥、失败保留输入、重开和预览卸载；其iframe是明确替身。E13另有31/31真实Java API/合成CLI认证/MySQL读回，使用旧JAR。这两类证据不能拼成教师浏览器批改实际学生三格式提交。
- 管理员：E14有57方法、62实际组件浏览器以及最终旧批删确认4项复验，E15另有37/37真实Java/MySQL课程/单元维护。E16成员界面采用真实DepartList父SFC、公共样式、theme、Vue/AntD但内存API，覆盖窄屏、键盘和交互。真实部门/字典/用户编辑入口、登录后路由外壳及保存重开仍不能据此判通过。
- 真实角色准备：E03/E04已有五账号、班A/B、真实动态菜单、三编辑器单元、文件任务；22/22真实API预检确认菜单/按钮/分班与素材。教师没有管理员课程/用户维护权限，不应为验收扩大角色。
- 真正缺失：教师普通登录后找到学生实际提交、使用真实三格式预览、保存评分评语并关闭重开；管理员普通登录完成代表性用户、班级、课程/单元维护并重开确认，新增合成数据按正常流程清理。维护原五合成账号，不新增第六个账号。
- 下一安全动作：沿E03既有管理员→学生→教师→学生回读步骤，使用同一冻结前后端，逐段记录同一unitId/workId/additionalId及保存重开。当前安全工作是本报告已经完成的证据归并；无法用另一个组件预览完成这个gate。

## 条件5：异常体验及数据保留

**状态：五类失败已有局部覆盖，整链和真实会话组合缺失。**

| 要求 | 已有证据与实际范围 | 未完成的组合证明 |
| --- | --- | --- |
| 网络失败、超时、HTTP500、业务false、非法records | E09/E10当前两作品入口在真实Vue/AntD+只读合成HTTP下可恢复；35项E11独立离线执行实际SFC和mixin | 合成容器没有global request.js的60秒timeout/notification/401语义；预览timeout是1.2秒，不能称产品60秒实测 |
| 过期登录 | E17匿名验证码图失败/重试和登录字段；登录/会话真实源码有清会话、单次提示、不强制刷新的实现与受控脚本检查 | 普通认证后发生过期，保留未保存编辑、重登后回目标以及旧账号迟到401不注销新账号的浏览器组合未记录 |
| 缺资源、错误程序文件 | E06阅读器和E37实际Python页面的404/断网/503/伪HTML/超时/恢复，真实引擎历史打开失败保护 | 实际受保护媒体与真实课程入口的缺失资源，不用默认示例静默覆盖学生版本 |
| 上传/保存失败 | 三编辑器历史真实UI+合成HTTP、E22任务上传/登记/提交失败；E12批改失败保留内容 | 普通认证对真实Java上传登记/提交/批改失败的页面保留和恢复，同一业务ID与附件验证 |
| 重复点击、迟到返回 | 当前E09/E11列表请求归属、destroy、retry；三编辑器历史同页保存锁；E12教师互斥 | 实际课程→编辑器→真实提交，不产生额外作品，失败后不污染其他作品或账号 |
| 原有数据与正常清理 | 历史API报告有数据库/附件恢复，E29三格式模块31/31恢复 | 普通页面新增的业务数据记录与按正常界面流程清理；不能把CLI恢复写成浏览器清理 |

`request.js:10`当前60秒timeout、401处理与全局notification保留；#72没有改全局mixin、标签请求或CRUD。卡片大量作品分页未接线，真实后端默认pageSize=999，fixture默认10，不推断当前产品仅前10或整页零未处理错误。跨标签新建幂等、失败后无引用文件回收、七牛真实路径等为已记录范围限制；目前没有真实整链复现证明它们是必须先修的本轮阻断，不提出新补丁PR。

下一安全动作是取得必要认证操作授权后，在E03已有真实流程中对自己这次请求做可恢复故障：断网/恢复、缺资源、上传/提交/批改失败和重复点。以真实数据ID、重开与正常清理结果证明，无需覆盖全仓库或无限增加边缘测试。

## 条件6：统一UI、键盘和三宽度

**状态：匿名主页面与多处真实组件已有工程截图，认证外壳下关键组合页面尚未覆盖；用户审美意见独立待答。**

E18是实际dist+真实隔离后端的匿名首页/课程/登录三宽度16项，并另有7项浏览器响应替换/图片故障回退；图标/校园图本地解码、天工紫、校名、手机导航和登录跳转有实际记录。它不能证明已登录管理页面。历史外部errlog/CSP与AntD焦点告警也不能被最新合成预览的console0抹去。

E19是f92cc7dd实际完整应用18142匿名找回密码首屏，真实验证码图片、实测390/768/1440，无凭据输入；E20是实际SFC/UserLayout合成四步展示，未解验证码、未发真实SMS、未输入新密码，完成页只展示fixture。当前源还保留真实图形验证码，手机号实值POST短信与校验、POST JSON改密、明确失败/结果不确定回验证；这些源码和受控测试不等于真实账号恢复完成。

学生反馈E08、当前列表E09、教师E12、管理员E14、成员E16、阅读器E06均有实测尺寸、键盘或状态证据。关键差别是多处替换BasicLayout/RouteView、字典/部门、传输层或编辑器iframe，不能由局部三宽度无溢出推断整个平台每个页面无裁切。当前反馈全文HTML按纯文本显示、44px按钮、键盘开关及焦点恢复成立；不要把它写成教师真实批改后的学生回读。

下一安全动作是复用普通认证整链，在390/768/1440核对真实导航、父容器、页面/弹窗关键按钮、标签/焦点、空错忙态、缺图回退；保留实际前后截图与测量结果。用户审美认可按计划单独注明“待用户评阅”，不是本报告额外设置的必须赞同门槛。目标部署/真实试用状态归其原计划条件，不扩成本次UI强制上线要求。

## 条件7：Scratch、ScratchJr、Python保留能力

**状态：核心能力有实际工程正证，普通认证的真实入口同ID闭环仍缺。**

| 编辑器 | 直接引擎/浏览器证据 | 另行真实API证据 | 当前继承与限制 |
| --- | --- | --- | --- |
| Scratch | E23真实VM/UI+syntheticHTTP 15项，实际x=100→-80，两版SB3/PNG生成、草稿/提交与同ID重开 | E24 24/24用浏览器生成文件真实上传/登记/更新/Cookie下载逐字节一致 | 旧JAR85f774…；后续cloud/CSP/player/课程恢复改动已加入当前，旧保存report不是当前整个编辑器新运行 |
| ScratchJr | E25真实角色库、拖位置与forward积木，18项，两版SJR/PNG | E26 24/24真实上传/登记/同ID/字节核验 | #28六份引擎/bridge/CSS当前同字节；共享Scratch persistence已后续改动。不能把源继承当认证整链重跑 |
| Python | E27真实Vue/Ace/Skulpt14条，两次保存同saved-2/刷新重开/输出72；后续E38/E39也有实际UI保存重开 | E28 18/18真实API上传/登记/同ID/Cookie字节 | 当前`persistence.js:105`固定workStatus=1，只有保存/提交，勿宣称独立草稿；本地下载未完成，不冒称已验收 |

三格式从课程URL恢复学生版已有E29真实产品persistence模块+HTTP/MySQL31/31，旧16/31，学生文件/标题/同ID保持。该报告明确排除编辑器render与浏览器登录；capture/apply使用适配器。E30三产品和两probe共5/5当前字节一致，不改变它的证据类别。

现有匿名引擎并非“尚未运行”：E31 #52当时组合两入口×三代理6/6，实际dist/CSP、自写代码绘图/输入/clear；E36 #53另有两入口×三代理6/6、实际单次源GET与turtle输出绘图。均匿名、无保存/认证、不是当前HEAD新运行。辅助只读核对#53 17份资源当前15/17相同，变化仅后续课程恢复的persistence/editor-bridge；10份Worker核心与#52同字节。Python仍是现有Python2/Skulpt，不增加Python3承诺。

E34真实Scratch VM匿名播放器/编辑器与真实后端云快照、匿名绿旗只改本机、撤回停止/恢复有记录；E35 15/15是交付provider+Node WebSocket+真实Java/Redis/MySQL的VM-interface harness。#37八份Scratch产品当前源摘要相同，但作者普通认证、首次真实保存建立云定义、私人作品读取、换账号/退出的浏览器组合未有证据。旧blob Worker CSP问题由#49后续处理，不能把旧告警当成当前未修复。

各编辑器均未形成“普通登录→真实课程入口→实际原生编辑→当前Java保存→从实际列表同ID重开→提交→教师实际预览”的一次闭环。无证据证明核心引擎现在损坏，也无证据允许把独立API附件上传与浏览器引擎观察拼成已完成。现有#48准备足够，按E03执行才是下一步；真实七牛、复杂项目、触摸积木、录音摄像、本地导入导出、云变量复杂场景等保留明确未验收范围，不通过隐藏入口达到完成指标。

## 当前可安全自主推进与停止扩修的判断

现在可以完成、且本审计已完成的是：核对冻结候选、证据来源/摘要、当前源码继承、旧结果与最新结果分界、现成验收夹具/菜单及缺失整链。没有额外需要先新建的harness、账号fixture或操作清单：E03已包含三编辑器、五账号、教师/管理员菜单及完整顺序，E04已有22项真实API准备检查。

不能安全自主执行的是此前未回答的验证码浏览器操作以及本轮明确禁止的浏览器/HTTP/数据库操作；不通过读取挑战、注入token、替换auth/mixin或直接改会话绕过普通登录。由root继续处理必要的操作确认，随后复用现成18150真实角色夹具，而不是给18142生产来源课程副本写入合成学生数据。

认证授权一旦齐备，优先做可交付的真实学生→教师→学生回读，再串管理员代表维护与实际异常/三宽度；每段记录真实页面行为、API返回/同一ID、重开内容或字节摘要、新增合成数据清理。只有发现真实可复现缺陷才开对应窄修复，不以再积累局部PR数或test总数替代这几个gate。

最新#72容器包E02仅offline immutable create/verify，本轮runtime未启动；E32的45/45属于#71精确69002a14+4894文件dist，不算当前4895文件组合重跑。该45项本身是API/登录、资源/保存/退出探针，也不是普通认证编辑器浏览器链。目标部署、TLS、大小写敏感Linux、真实云存储及人工试用单独列明状态，不在这里擅自扩成所有候选必须生产上线。

## 审计执行说明

报告结论来自实际文件、源码摘要与历史报告字段核对；没有再次执行其浏览器或API测试。辅助只读子Agent核对编辑器历史manifest/当前字节和能力范围，它没有写文件或运行服务，不能称独立产品复测。两个读取命令曾使用不存在的路径/未匹配zsh glob；改为实际文件路径/rg定位。一次JSON缩略打印把数组当dict报AttributeError，随后按真实数组形状核查；这些读取错误未改变产品或证据文件，也不计为行为测试。

## 精确证据路径

下表所有路径均已读到并计算SHA256。按E编号用于上文；摘要与完整scope在同目录 `evidence-index.json`。

| ID | 证据与范围 |
| --- | --- |
| E01 | [productization-goal-2026-10-02.md](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/productization-goal/docs/optimization/productization-goal-2026-10-02.md) — current completion contract；gates 2/3/5/6/7 at lines72/73/75/76/77 |
| E02 | [student-work-loading-candidate.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/productization-goal/docs/optimization/evidence/product-candidate/student-work-loading-candidate.json) — current candidate aggregation；current06ab2040;645node;static24;latestcontainerNOT_RUN |
| E03 | [role-flow-fixture-pr.md](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/role-flow-fixture-pr.md) — historical fixture/actual API preparation；existing five accounts, real menu/routes, three engine units; full ordinary browser checklist |
| E04 | [api-preflight.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/role-flow-fixture/api-preflight.json) — historical actual Java API with synthetic accounts；22/22;no browser login/editor/playback |
| E05 | [role-flow-candidate.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/productization-goal/docs/optimization/evidence/product-candidate/role-flow-candidate.json) — historical candidate binding；babf2a55;browser_role_acceptance=false |
| E06 | [root-result.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/production-media-compatibility/root-result.json) — historical actual assets and real component；211media;86inventory;5video/2PDF/1MD;memorylearning API and local URL adapter |
| E07 | [browser-video-results.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/production-media-compatibility/browser-video-results.json) — historical browser media observations；5 representative videos;not authenticated platform |
| E08 | [browser-report.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/student-feedback/browser-report.json) — recent actual Vue/AntD synthetic container browser；390/768/1440;literalHTML,keyboard;no persisted teacher-to-student browser flow |
| E09 | [final-report.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/student-work-loading/final-report.json) — current source actual Vue/AntD synthetic browser；faults,retry,snapshot,pagination;no authenticated shell/global interceptors |
| E10 | [final-assertions.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/student-work-loading/final-assertions.json) — current source browser assertion aggregation；7 true assertions |
| E11 | [loading-offline.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/student-work-loading/loading-offline.json) — current source independent actual Vue/SFC offline；35/35;deferred transport;noDOM/HTTP/DB |
| E12 | [checks.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/teacher-workbench/checks.json) — historical real Vue/AntD synthetic browser；202tests;25interactionchecks;editoriframe substitute |
| E13 | [actual-backend.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/teacher-workbench/actual-backend.json) — historical actual Java API/MySQL；31/31;syntheticCLIauth;not authenticated browser |
| E14 | [admin-course-test-summary.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/admin-course-workbench/admin-course-test-summary.json) — historical real Vue/AntD synthetic browser/methods；57methods;62browser beforelastguard+4finalaffected;not authenticated maintenance |
| E15 | [admin-course-actual-api.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/admin-course-workbench/admin-course-actual-api.json) — historical actual Java/MySQL；37/37;course/unitmaintenance contract |
| E16 | [browser-summary.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/class-membership-layout/browser-summary.json) — recent actual parent/theme synthetic browser；DepartList realparent/common/theme;memoryAPI;not platformE2E |
| E17 | [browser.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/login-experience/browser.json) — historical anonymous complete application browser；10observations;captcha completion pending;authflows not verified |
| E18 | [checks.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/tiangong-branding/checks.json) — historical anonymous actual dist/browser；16real+7interception;user visual pending |
| E19 | [candidate-report.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/account-recovery/candidate-report.json) — recent anonymous complete application browser；f92cc7dd;step1only;CAPTCHA image loaded;no credentials |
| E20 | [preview-report.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/account-recovery/preview-report.json) — recent actual SFC/UserLayout synthetic browser；noCAPTCHAsolved/noSMS/no newpassword/fixturecompletion |
| E21 | [browser-observations.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/student-assignment-feedback/browser-observations.json) — historical actual SFC/modal synthetic HTTP browser；task upload/submit/feedback/zero/retry;no platformauth |
| E22 | [after-submit-error-http.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/assignment-file-submit/after-submit-error-http.json) — historical synthetic HTTP recorded calls；upload/register/submiterrors;not actualplatform |
| E23 | [browser-observations.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/scratch-editor-persistence/browser-observations.json) — historical real engine + synthetic HTTP browser；15 observations;real generated SB3/PNG |
| E24 | [real-backend.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/scratch-editor-persistence/real-backend.json) — historical actual Java API CLI；24/24;engine browser and API separate |
| E25 | [browser-observations.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/scratchjr-editor-persistence/browser-observations.json) — historical real engine + synthetic HTTP browser；18observations;real edited SJR/PNG |
| E26 | [real-backend.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/scratchjr-editor-persistence/real-backend.json) — historical actual Java API CLI；24/24;browserlogin excluded |
| E27 | [browser-observations.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/python-editor-persistence/browser-observations.json) — historical real Vue/Ace/Skulpt + synthetic HTTP browser；14observations;save/reopen;localdownload not passed |
| E28 | [real-backend.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/python-editor-persistence/real-backend.json) — historical actual Java API CLI；18/18;browserlogin excluded |
| E29 | [course-resume-live-candidate-final.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/course-draft-resume/course-resume-live-candidate-final.json) — historical actual persistence modules + real HTTP/DB；31/31;editorrender/browserlogin excluded |
| E30 | [source-and-probe-manifest.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/course-draft-resume/source-and-probe-manifest.json) — historical source manifest checked against current bytes；3currentproductfiles+2probes |
| E31 | [python-execution-candidate.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/productization-goal/docs/optimization/evidence/product-candidate/python-execution-candidate.json) — historical anonymous combined actualdist real engine browser；6/6 twoentries threeproxies;noauthentication/save |
| E32 | [student-feedback-readable-candidate.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/productization-goal/docs/optimization/evidence/product-candidate/student-feedback-readable-candidate.json) — previous exact candidate real container aggregation；45/45 only69002a14/dist4894;notcurrentdist4895 |
| E33 | [final-source-manifest.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/student-work-loading/final-source-manifest.json) — current source independent freeze binding；424 frozen src;35tests;verifiedsourcecommit |
| E34 | [verification.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/scratch-cloud-client/verification.json) — historical real Scratch VM anonymous browser + actual backend；public cloud snapshots;no authenticated author browser |
| E35 | [real-client.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/scratch-cloud-client/real-client.json) — historical actual Java/Redis/MySQL + Node WebSocket provider；15/15;VM-interface harness not browserlogin |
| E36 | [python-source-loading-candidate.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/productization-goal/docs/optimization/evidence/product-candidate/python-source-loading-candidate.json) — historical anonymous combined actualdist engine；6/6 twoentries threeproxies;noauth/save |
| E37 | [browser-final.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/python-source-loading/browser-final.json) — historical real Python UI + synthetic HTTP；20scenarios;sourcefailure/retry/threewidths |
| E38 | [save-reopen.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/python-source-loading/save-reopen.json) — historical real Python UI + synthetic HTTP；sameID save/reopen;noJava/auth |
| E39 | [chromium-save-reopen.json](/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/docs/optimization/evidence/python-execution-frame/chromium-save-reopen.json) — historical real Python UI + synthetic HTTP；actual submit/register/upload eachonce;seed-work sameID;noJava/auth |
