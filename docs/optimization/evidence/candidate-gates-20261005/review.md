# 当前候选的产品化缺口审计

2026-10-05。独立子 Agent 只读审计，用户指定 GPT-6.1-sol / ultra；没有单独 Fast 工具参数。仅读取文件、Git 版本/状态和既有执行证据，未运行产品测试、数据库、HTTP、浏览器、ffprobe、PDF 解析、服务或生产请求；本文件是唯一新增文件。媒体兼容性后续由 root 执行，本报告不预写它的结果。

**结论：当前已经有大量可复用的局部工程和真实 API 证据；缺口主要是实际产品闭环、代表性真实媒体和发布代理/目标平台契约。下一项优先实际素材兼容性，再隔离复现 Nginx 对正常编辑/删除请求的阻断。不能用继续累积窄安全修复替代这三类用户结果。Goal 仍须 active。**

审计版本：应用工作树 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate`（下文 **C**），实际 HEAD `49bea7da3552c554a8412f777eeec48d9a5ac9f2`；tracked 无改动，既有 `.playwright-cli/`、`output/` 未跟踪目录保留。管理工作树 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/productization-goal`（**G**），HEAD `03bdbbd16c40c6d91f603076f3d56b85708d0970`。**E** 指 `G/docs/optimization/evidence/product-candidate/`，不是应用工作树内同名目录。

最新 `E/upload-resource-boundary-candidate.json:221` 绑定最终 HEAD；后端包 SHA256 `9eb18d42d365dd4fba7044d57ed33aaa0fdb543f8468dd67c10c9dc83de05869`，1031 项构建输入相同。前端沿用 #63 的 4893 文件/211629143 字节/清单 `0b38b4690bac046186f3f4127eb8dc666aada7e2a413216a1a1a917f4bf2d120`，本轮未重建。最新证据记录三本地后端健康和真实副本 12/12；本次审阅未实时复查服务，也未联网刷新 PR 状态。

## 10 项完成条件的证据与真正剩余

依据 `G/docs/optimization/productization-goal-2026-10-02.md:59–70`。

| 条件 | 可以认可的当前证据 | 仍未证明或需处理 |
| --- | --- | --- |
| 1 构建与可复现性 | 已有干净依赖安装/前后端构建和独立 macOS arm64 运行工具；#63 组合前端 581/581、构建退出0、12条告警，#65 后端输入绑定精确冻结包。`C/api/BUILDING.md:3`、`C/web/BUILDING.md:5`、`E/class-membership-layout-candidate.json:17`。 | Linux/Docker/目标环境尚未实测；Maven父POM跳过Java测试，构建不能写作Java业务测试。无需因版本未变重跑整个旧流程。 |
| 2 学生闭环 | 实际课程发现/阅读器组件、三编辑器真实引擎局部交互、对应真实 API 的保存和重开字节、文件任务/反馈有分层证据。 | 产品普通登录→课程/单元→真实视频→编辑器保存重开提交→教师反馈回读，没有同一业务ID贯通的整链实际浏览器证据。已有待答验证码操作确认只影响该动作；本审计不解决、注入或绕过登录，也不重新提问。 |
| 3 教师与管理员 | 教师工作台25/25真实组件+合成HTTP；另外真实Java/MySQL31/31含学生讨论→教师零分→学生回读。管理员课程页真实API37项和组合构建已有证据。五账号三角色真实菜单/媒体预检22/22。`C/docs/optimization/teacher-workbench-pr.md:18–20`、`E/admin-course-candidate.json`、`C/docs/optimization/evidence/role-flow-fixture/api-preflight.json`。 | 整个应用实际菜单下的班级/用户/课程维护、教师发布任务和批改、学生回读仍未成为完整浏览器流程。角色夹具已经建立，不能重复说“缺可用三角色环境”。 |
| 4 权限与数据 | #65 同冻结探针的旧新真实HTTP与恢复结果、下载88/88、69表结构/68非审计表及文件相同；历史允许/拒绝和关系变更检查仍可按原范围引用。`E/upload-resource-boundary-candidate.json:17–66`。 | 没有证据支持“所有路径/所有环境已经安全”。发布Nginx、目标TLS/代理、完整真实浏览器允许与拒绝应分别完成；已修资源映射、账号冻结、编码媒体等历史缺陷不重新开单。 |
| 5 异常体验 | 局部页面/编辑器已有断网、503、401、404、重复点击、迟到响应、失败保留和重试观察；真实上传流失败清理及正常教师删除最后引用有实际API结果。`C/docs/optimization/local-upload-boundary-pr.md:16–28`。 | 全链浏览器故障恢复未通过。取消上传仍不回收已传输/已登记孤立文件，`C/docs/optimization/assignment-file-submit-pr.md:50` 明示，不能把测试SQL恢复算普通产品清理。它适合另行有界评估，不应先做全库自动清理。 |
| 6 UI | 390/768/1440局部真实组件、实际父SFC/主题、键盘、短屏/长文和前后截图已有；#63还解决成员布局的实际遮挡。`E/class-membership-layout-candidate.json:408`。 | 局部内存/合成API页面不等于认证后的完整应用；用户审美/人工认可没有证据。保留截图成果，不称每个页面都未做。 |
| 7 媒体与创作 | Python真实引擎局部浏览器14项/真实API18项；Scratch15/24；ScratchJr18/24，包含改动、保存、重开及失败恢复。分别见 `C/docs/optimization/evidence/{python-editor-persistence,scratch-editor-persistence,scratchjr-editor-persistence}/{browser-observations.json,real-backend.json}`。它们明确限定合成服务浏览器与另外真实Java API。 | 三编辑器的同一普通认证产品链仍待完成。真实副本83个单元练习类型全NULL、案例/模板全空，不能补这项。83长视频、45 PDF、83 `.md` 之前仅字段/引用/stat，未播放或打开。Python课程保存当前 `workStatus=1`，没有独立草稿动作，应如实记录支持差异。 |
| 8 运行与恢复 | 小合成数据核心HTTP读写、真实副本有限匿名读1008/1008、首页预取395→17请求和字节对照；69表/3019行/2附件39/39冷恢复、五阶段各26/26切换/回退、云值恢复14/14已完成原范围实演。`C/docs/optimization/{tomcat-maintenance,local-backup-restore,local-candidate-switch,scratch-cloud-recovery,frontend-route-prefetch}-pr.md`、`E/production-read-benchmark-candidate.json`。 | #64性能绑定#62旧包，#65只重跑12项正确性，不能称新包性能测量；最新整包/真实来源副本完整恢复未实演。旧工具机制未变，不构成再跑全套的理由。没有公网/生产容量、异机灾备或生产RPO/RTO结论。 |
| 9 依赖与发布 | 当前209库/208外部JAR与15关注npm包、20一手来源已核对；Tomcat/Shiro过渡维护和#65资源入口修复有结果。`G/docs/optimization/evidence/dependency-release-20261005/review.md`。 | 维护债务/受支持平台路线、Servlet session与TLS代理Cookie条件仍待结论；不预设漏洞或强制重写。目标环境与生产定制源码等价未证明。发布脚本存在可复现性与正常业务代理契约缺口，见下文。 |
| 10 PR与交付 | #1–65按问题记录、确切提交/冻结包/集成候选可追溯；状态区分检查、Draft、待人工验收、未合并/未部署。 | 其余实质条件未齐，PR数量不能作为完成比例。证据中的远端状态是记录时状态，本次没有最新远端核实。只有全部约定条件达成才关闭Goal。 |

## 优先的两个独立推进目标

**1. 代表性真实媒体兼容性，作为本轮主线。** 前次只读覆盖 `G/docs/optimization/evidence/production-copy-coverage-20261005/review.md` 和 `aggregate.json` 已证明297清单文件属性匹配；83 MP4、45 PDF、83 `.md` 没有内容/播放验收。这是可新增且不依赖浏览器平台认证的证据。先在授权私有副本做离线容器/codec/音轨、时长/分辨率/MP4索引位置、PDF魔数/解析页数、Markdown实际格式汇总，路径和正文只留私有报告；再按差异选择3–5视频（覆盖不同课程、最长/最大、特殊音轨/索引布局）和2 PDF、1长Markdown，实际检查加载、播放时间前进、seek后继续、文档打开。若使用独立只读媒体壳或静态选样，明确写成“真实素材兼容性”，不宣称正式受保护路由、三角色或登录全链通过。实际UnitViewModal消费者接入的检查另有增量价值。

可沿用 `C/api/dev/verify-production-content.py` 的 `guard(runtime, requested_jar)`、固定SELECT的 `sql`（server READ ONLY/ROLLBACK）、`business_snapshot`；`production_fixture.py:494` 的 `ordinary_asset` 拒绝链接与越界；`production_read_benchmark.py:73` 的 `asset_snapshot` 对size/mtime/mode/inode作前后摘要。私有 `assets-result.json` 结构为 `{files:{relative:{bytes,sha256}},count,bytes}`，`resource-references.json` 为 `{paths,external_references,unsafe_references,scope}`；用清单引用选样，不扫描学生目录、不访问两个外部正文引用。新结果绑定当前候选、新JAR、dist与清单摘要，并核对资源和业务摘要保持。

`C/api/dev/serve-media-probe.py` 会真实API登录和插入sys_file，并生成合成媒体；不能直接指向真实副本作“只读”检查。`benchmark-local-http.py` 也会写合成作品。此次素材检查由root统一执行，本审阅不重复读取或另开服务。

**2. 正常编辑/删除穿过发布Nginx，先实证再最小修复。** `C/web/nginx/default.conf:36–39` 的server级if返回405给全部PUT/DELETE，`C/web/Dockerfile` 会打包该配置。真实UI `C/web/src/views/system/DepartList.vue:569` 用PUT，`C/web/src/mixins/JeecgListMixin.js:181` 用DELETE；后端 `TeachingCourseUnitController.java:168/208`、`TeachingWorkController.java:512/557/576` 声明对应方法。当前本地 `C/api/dev/serve-frontend.py:223–224` 允许PUT/DELETE，两者不是同一发布路径。这里已证明静态业务契约冲突，尚未运行Nginx证明用户故障。

可在任务自有loopback Nginx代理与合成运行环境复现：正常管理员编辑班级/单元、正常教师删本班自制作品能到真实后端并重开/确认；匿名、学生和跨班身份仍按真实后端规则拒绝，拒绝前后数据相同。修复应仅让受支持API方法交给现有后端授权，同时保留静态资源方法和TRACE/TRACK/WebDAV限制；不能全局宣称所有方法安全。完成一个功能兼容PR，不访问生产，不混入平台升级。

## 部署支持边界

存在deploy文件不等于本候选可重现部署。`C/api/BUILDING.md:3` 明示只验证macOS arm64；`C/deploy/docker-compose.yml` 使用上游`:latest`，不能绑定当前49bea7/9eb18d42/app.fff8dd9f；`C/deploy/build.sh` 无fail-fast，仍以Node16/yarn构建，和 `C/web/BUILDING.md:5–13` 已验证Node26/npm ci锁文件路径不同。静态证据足以列为准备缺口，但不证明脚本此次运行失败、远端镜像有何内容或Linux不能运行。

在真实媒体和发布方法兼容之后，有价值的有界目标是冻结当前JAR/dist/配置的部署包与可评审启动/停止/回退步骤，再在经授权的全新本地Linux/Docker环境验证health、代表性CRUD、授权媒体HEAD/Range、WebSocket和TLS终止Cookie。必须分别记录“准备完成”和“目标环境已实测”；当前没有生产发布、采购、迁移或生产服务修改授权。没有目标环境时先完成包/说明和静态契约核对，不把macOS结果推广成Linux支持。

本报告只识别证据覆盖和后续操作；没有实施修复、完成媒体验收、更新产品文档、改动候选版本或关闭Goal。
