# GitHub CI

工作流位于 `.github/workflows/ci.yml`，在 PR 创建/更新及 `main`、`codex/registration-acceptance` 的提交时运行。所有任务使用 GitHub 托管的 Ubuntu 临时机器；没有 cron、本机 runner、云端 SSH、部署或备份下载。

## 合并检查

- **Frontend tests and build**：沿用 `web/.nvmrc` 与锁文件，禁用依赖安装脚本，运行前端测试、实际 Chromium 通知组件渲染、上传凭据及 Header/TMenu 导航回归和生产构建；缺少浏览器直接失败，不跳过浏览器检查。获取完整 Git 历史，以运行已有的旧版本回归对照测试。
- **Backup and migration tools**：执行备份、升级清单、发布包、空表提取以及 CI 守卫的合成测试，不实际运行备份或拉取服务器数据。单独执行 `api/dev/test_teaching_journey_fixture.py`，离线检查教学流程夹具的请求、认证材料、限定 SQL、缓存和上传恢复边界；该步骤不启动服务或浏览器。另运行公网 IP HTTPS 工具单元测试与固定镜像的隔离 Nginx/TLS 验证：临时测试 CA、回环端口、合成 API/WebSocket/媒体、实际配置切换与回退，不请求公网证书、不连接生产。只保存不含私钥的汇总 JSON。
- **Backend and MySQL registration**：Java 8 干净构建并显式开启 `check_java_results.py` 所列的 40 套核心 Java 测试。构建选择与 Surefire 报告校验读取同一清单，缺少或跳过任何核心测试都会失败。CI 自身回归还枚举仓库的 `*Test.java`，防止新增套件遗漏。原 `SampleTest` 依赖固定旧业务样例，`SecurityToolsTest` 仅打印加解密结果，因此不列入核心检查。
- **Select affected PR jobs**：只在 PR 上核对实际合并候选并分类改动；push 事件不使用 PR 路径分类；主分支只在下述完整历史证据复核通过时复用，否则执行全量。
- **CI required**：始终汇总任务结果，要求所有应执行任务成功；只接受有效 PR 分类明确判定不受影响的跳过，或独立在线复核通过的 main 完整历史证据。任何重量任务失败、取消或缺少结果都不能通过。分类失败或输出不完整时，不允许跳过，必须三项检查全部成功。保持同一汇总状态名称，避免路径过滤导致检查缺失。

## PR 任务选择与全量兜底

`select_jobs.py` 在 checkout 后核对 `HEAD == GITHUB_SHA`，且该合并提交的两个父提交分别等于事件中的 base/head SHA。只接受唯一 merge-base，以 PR 的三点 diff 得到完整改动，不使用有文件数量上限的 API 列表。路径使用 NUL 分隔，禁用重命名识别，使跨目录重命名同时包含原路径和新路径；删除、中文、空格和换行文件名不会被分行截断。

| 改动输入 | 需要执行的完整任务 |
| --- | --- |
| `web/**` | frontend |
| `examples/**` | frontend（展示页及测试读取示例目录） |
| `api/**`、`deploy/**` | backend + tools（部署配置、Java 测试枚举、实际探针与合成工具相互依赖） |
| `ci/**`、`.github/**` | frontend + backend + tools |
| `web/tests/public-boundaries-live.py` | frontend + backend（API 探针加载该实现） |
| `web/nginx/**`、`web/src/views/system/modules/DepartModal.vue` | frontend + tools（HTTPS、候选包及全局规则测试读取） |
| `资料/**` | tools（HTTPS 验证读取历史 Nginx 示例） |
| `docs/**`、根目录 `evidence/**` | 当前不作为上述任务输入；只有这些改动时仍执行分类和汇总检查 |
| 其他路径或根目录配置 | frontend + backend + tools |

多个改动取任务并集；每个被选中的任务仍完整运行原有检查，未缩减探针或断言。空 diff、事件缺失、对象不全、候选与事件不一致、Git 执行失败、多个 merge-base 均回退全量。分类任务自身失败或没有完整布尔输出时，三个任务也会全跑；整条工作流取消时不启动新的重量任务。`CI required` 独立再次校验分类状态及三个布尔值，拒绝意外 skipped、failure、cancelled 和缺失结果，不能靠一个不完整计划得到绿色结果。

push 不接受 PR 分类作为跳过依据。`codex/registration-acceptance` 始终全量；`main` 在没有合格完整历史证据时也必须全量。工作流层不设置 `paths` / `paths-ignore`，因此纯文档 PR 仍会产生 `CI required` 状态。新增跨目录输入时，同步更新分类器和 `test_job_selection.py` 的行为用例；新增未知目录默认执行全部任务。分类回归使用临时 Git 仓库验证真实 diff、rename/delete、损坏事件及全部汇总状态组合，不连接业务服务。

后端构建后还用当前依赖执行 `deploy/test_ip_https_proxy.py`：实际 Spring Boot 配置绑定、Tomcat RemoteIpValve 与原 MediaCookie 源码，核对仅信任 127.0.0.1 的协议转发及 Secure Cookie。该测试无需数据库或监听 socket，不能代替线上登录验收。

每个 PR 的新提交取消同一 PR 的旧运行。没有定时触发。Node/npm 版本遵循现有项目；Actions 使用完整提交 SHA 固定，任务只有读取权限；复用检查与最终汇总另有 `actions: read` 用于读取运行状态和收据，不使用生产凭据。

菜单浏览器回归使用 `--ref "$GITHUB_SHA"` 编译真实 Header/TMenu，在 1440×1000 和 390×1200 视口通过 Chromium 鼠标输入测试危险链接、合法子菜单、站内路由、静态编辑器和 HTTPS 同页/新页跳转。HTTPS 目标全部在发起网络连接前拦截为合成响应，任何意外外联或浏览器错误均失败。`check_menu_browser_results.py` 要求本次 checkout 的完整 SHA、6 份源码的 Git blob 哈希、至少完整的 28 项行为和 18 次点击、8 张截图及一致计数；拒绝旧版本模式、其他提交、Node/JSDOM 替代和不完整报告。前端单独保存合成 JSON 与 PNG，不上传编译 bundle 或浏览器用户目录。

## 同树完整 PR 证据复用

`ci_reuse.py` 只为普通 `main` push 寻找该目标提交实际合并的同仓库 PR。PR 本身仍按上述依赖选择任务；其他 push、fork、直接提交、强制推送、没有可确认关联的 squash/rebase 等情况全量运行。**复用历史完整测试证据不等于当前 push 重新执行了测试**：汇总明确列出原始实际 merge checkout SHA、来源 run/attempt、目标 SHA 和共同 tree；原浏览器、Java、HTTP/SQL 报告不改写、不搬成目标提交的执行报告。

所有条件必须同时满足：

- GitHub 当前 workflow/head 的最新 PR run 已成功且为第一次执行，三个重量任务与 `CI required` 均实际执行成功。选择性跳过得到的绿色 PR、重跑、失败、取消、遗漏、未知新任务和不同 attempt 拼接均不可复用。
- 每个重量任务在成功后生成独立 `fresh` 收据；API artifact 的仓库、run、PR head、唯一名称与 SHA-256 摘要匹配。收据记录实际 checkout、两个父提交、完整 tree、工作流 blob、原始 PR 身份和实际运行时版本。三个收据一致，再用 GitHub Git commit 对象核实原 merge 的 tree/parents，不能拿 PR head 的 tree 代替实际测试树。
- 目标完整 tree 与实际测试 tree 完全一致，涵盖跨目录源码、锁文件、POM、CI 脚本和工作流。Node/npm、Python、Temurin Java、Actions 提交和 MySQL/Redis/Nginx 镜像均固定；环境契约遇到动态依赖版本或不支持的配置就回退全量。
- 三个来源 runner 的 `ImageOS`/`ImageVersion` 与当前验证机器一致。来源 backend 记录实际全部 dpkg 包版本的摘要；候选证据初步通过后，验证机器执行同一客户端安装，再比较全部包版本，包含间接依赖变化。最终汇总在另一台机器重新读取来源状态并复核环境。
- 从来源 run 开始时间到复核不超过 6 小时，且仍为同一上海业务日期；跨日期、过期和未来时间均拒绝。未来增加新的时间/外部可变输入时，需先扩展契约或关闭复用。

主分支的 `Verify identical-tree PR evidence` 默认输出不复用；证据缺失、API 超时/分页不完整、收据损坏、版本漂移等均恢复原有三个完整任务。最终 `CI required` 再次在线校验同一来源，只允许三个任务全部执行成功，或三项全部跳过且证据仍有效。若选中复用后来源发生重跑、过期或复核接口失败，汇总失败；重新运行该目标工作流会重新评估，不能静默放绿。整条工作流取消仍会停止新任务。

依赖契约核对固定的版本声明和已解析系统包，不声称远端 Maven 仓库永远不会替换同版本制品，也不以历史证据证明依赖仓库此刻可用。普通全量 CI 的安装、干净构建、全部浏览器/Java/HTTP/SQL 断言都保留。只有新协议生成的三个完整收据可复用，旧运行不会被追认。收据保留 2 天，有效期仍只有上述 6 小时；不包含凭据、业务数据或构建产物。

本地守卫验证：`python3 -m unittest discover -s ci -p 'test_*.py' -v`；工作流语法用 `actionlint`。升级运行时/镜像或改变检查集合时，同时审查 `reuse_environment.py`、`ci_reuse.py` 和相应回归；未知配置默认增加全量运行，不减少检查。

## 注册数据库验证

后端任务启动临时 MySQL 8.0 和 Redis 7.2 服务容器，使用固定测试端口 33306/36379。`registration_mysql.py` 只接受 GitHub 托管运行环境和当前工作区；在本地或自托管 runner 上直接拒绝。

脚本新建 `teachingopen_check_ci`，已存在即失败，不覆盖任何已有数据库。从版本库 SQL 提取 69 张空表，不导入原始 INSERT，只添加合成 student 角色及关闭状态的注册开关。真实注册迁移按顺序执行两次，检查重复执行兼容性，然后启动本次构建 JAR，使用完整外部配置替换内置环境配置。应用数据库账号只拥有测试库的读写权限，测试探针通过独立账号注入隔离库触发器故障。

复用 `deploy/verify_registration.py` 的 186 项 HTTP/SQL 检查：姓名/学校与补充汉字、用户名与口令保存及手机号为空、3位/100位/纯数字用户名、用户名格式与已有或已删除账号占位拒绝、旧手机号账号的验证码登录与凭据不变、旧手机号注册请求拒绝、纯数字与纯字母及64位密码的注册和验证码登录、两入口密码长度与字符边界拒绝及拒绝前后数据不变、普通入口固定学生资料、独立教师入口固定教师资料、两入口仅授予学生角色、请求身份与权限伪造、同入口及跨入口重复、混合并发注册、管理接口拒绝及拒绝前后数据不变、两入口关闭注册与资料写入失败时事务回滚、失败后重试及公开目录脱敏。结果记录 MySQL 版本、表数和实际 CI 提交。

注册验收结束后，`review_mysql.py` 新建另一套五账号合成数据库，串行运行 `PROBES` 中的 27 组完整 HTTP/MySQL 必需清单，包括课程修改、作品提交、反馈保留、菜单/日志/共享素材/全局管理权限、历史附加作业读取、编码文件引用和文件删除锁竞争。注册入口及独立 review 入口都会先检查全部文件；任一探针缺失或改名，在创建运行目录、连接数据库、启动应用前失败。当前门禁不提供静默缩减或历史提交兼容模式。

文件并发探针使用受控触发器、命名锁和实际 `performance_schema` 等待记录，双向竞争各执行 3 次，并验证文件删除失败、元数据 SQL 失败及重试。AutoLog 探针最后执行，只对本次合成教师/作业的审计 INSERT 注入真实 SQL 故障，验证业务提交、统计仅一次、无敏感内容的 WARN 和后续正常审计。它通过与当前进程绑定的私有 `backend-process.json` 读取固定日志路径；适配器把 PID、JAR 哈希、配置和日志绑定到当前候选，拒绝不匹配、符号链接、缺失或非私有文件。日志内容不作为 artifact 上传。OSS/Minio 的 HTTP 检查不调用真实云，正常云操作仅由 Java mock 覆盖。

运行器统一提供 `runtime/jar/output/expect_legacy=False` 参数，保留真实 `FixtureApi` HTTP 和验证码登录逻辑。`ci/test_ci_guards.py` 离线加载全部 27 个实际探针模块，核对所需参数、固定 CI 端点及客户端绑定，并检查 adapter 异常退出时恢复原依赖；这些接口检查不执行探针的业务 HTTP/SQL 场景。

review fixture 单独使用 JDBC Quartz，真实验证任务增改、暂停、恢复和拒绝操作前后的数据库状态；保持 `auto-startup=false`、`overwrite-existing-jobs=false` 与 `initialize-schema=never`。仅在新建的空合成库中，将历史 DDL 的 11 张小写 Quartz 表名及外键目标规范为 `StdJDBCDelegate` 使用的 `QRTZ_` 大写名称，保留定义及其他表名；同时核验 MySQL 的 `lower_case_table_names=0` 和实际表名。汇总报告记录这一配置。没有修改服务器大小写设置、历史源 SQL 或生产配置。

候选包的上线模板仍为内存 Quartz、禁用自动启动；旧 `dev/prod/test` profile 使用 JDBC 和 `QRTZ_` 前缀。大小写敏感数据库直接导入历史小写 DDL 时，该旧 profile 需要独立的 schema 适配和上线前验证。CI 合成库的规范化不代表已有生产 schema 自动兼容，也不执行生产迁移或启用任务调度。

每份探针报告必须有非空且全部通过的 `cases` 或 `checks`、一致的执行数量以及当前进程候选 JAR 的 SHA-256。汇总保存必需清单、实际探针数、总检查数、候选 JAR 哈希与 CI 提交；拒绝旧版本期望模式、异常报告、空报告、错误计数和其他 JAR 的结果。`unit-view-events.sql`、`work-events.sql` 和 `local-media-references.sql` 在两个合成库各执行两次，检验迁移幂等性。媒体迁移只创建引用结构、元数据索引和 `version=0` 状态；当前 JAR 首次启动在事务中回填后写入 `version=1`。Java 必需清单包含 `LocalMediaReferenceIndexTest`，HTTP 必需清单包含 `verify-local-media-index.py`，覆盖引用更新、拒绝、失败回滚和规模下查询行为。探针失败即停止，不能把部分结果计作完整验收。

必需探针中，单元访问统计、新闻正文、追加任务权限、作品克隆、分页、课程修改、作品提交、作品引用权限、文件并发删除和编码引用删除这 10 个，通过 `media_index_fixture.py` 同步 SQL 夹具涉及的六类媒体引用源。它们在原始 SQL 成功执行后，显式登录合成管理员并调用重建端点；原始 SQL 失败或重建被拒绝都会使探针失败。每个探针先只读记录引用表和 state 的原始摘要，清理后检查两者恢复。helper 只识别直接源表写入，忽略读取、其他表、字符串、注释和触发器定义；它用于夹具准备和清理，不包裹 API 业务写入，也不是生产运行补偿。`verify-local-media-index.py` 不使用该 helper，以独立暴露业务事务同步失败。保留显式 `expect_legacy` 的旧探针在旧基线模式下不访问新表或端点；CI 仍拒绝把旧基线结果作为当前候选验收。`ci/test_media_index_fixture.py` 随 CI 的 Python discover 自动执行识别、失败传播、这 10 个实际 wrapper 和旧基线兼容测试。

GitHub 仅保留不含真实用户数据的 JSON 测试结果 7 天。运行配置、凭据、数据库和应用日志不作为 artifact 上传，临时容器由 GitHub 在任务结束后回收。CI 不能代替线上运行检查、备份恢复演练或人工验收。

## 维护

新增核心 Java 测试时，更新 `check_java_results.py` 中的必需测试集，工作流通过 `--list` 使用同一集合。新增核心 HTTP 探针时，更新 `review_mysql.py` 的 `PROBES`；保留 `verify(args)` 与 `runtime/jar/output/expect_legacy` 接口，并使用 `FixtureApi` 及合成环境 SQL 工具，避免绕过运行器绑定。注册验证数量变化时，审查新增/删除的行为，再更新完整执行数量。不要通过跳过失败项或 `continue-on-error` 获得绿色状态。

首次工作流须在真实 GitHub PR 上通过，review 后再合并并启用 `CI required` 分支规则。当前交付目标是 `codex/registration-acceptance`；工作流到达其他集成分支后，才为对应分支启用该必需检查，避免给尚无工作流的分支制造无法满足的合并条件。
