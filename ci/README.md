# GitHub CI

工作流位于 `.github/workflows/ci.yml`，在 PR 创建/更新及 `main`、`codex/registration-acceptance` 的提交时运行。所有任务使用 GitHub 托管的 Ubuntu 临时机器；没有 cron、本机 runner、云端 SSH、部署或备份下载。

## 合并检查

- **Frontend tests and build**：沿用 `web/.nvmrc` 与锁文件，禁用依赖安装脚本，运行前端测试、实际 Chromium 通知组件渲染、上传凭据及 Header/TMenu 导航回归和生产构建；缺少浏览器直接失败，不跳过浏览器检查。获取完整 Git 历史，以运行已有的旧版本回归对照测试。
- **Backup and migration tools**：执行备份、升级清单、发布包、空表提取以及 CI 守卫的合成测试，不实际运行备份或拉取服务器数据。单独执行 `api/dev/test_teaching_journey_fixture.py`，离线检查教学流程夹具的请求、认证材料、限定 SQL、缓存和上传恢复边界；该步骤不启动服务或浏览器。另运行公网 IP HTTPS 工具单元测试与固定镜像的隔离 Nginx/TLS 验证：临时测试 CA、回环端口、合成 API/WebSocket/媒体、实际配置切换与回退，不请求公网证书、不连接生产。只保存不含私钥的汇总 JSON。
- **Backend and MySQL registration**：Java 8 干净构建并显式开启 `check_java_results.py` 所列的 39 套核心 Java 测试。构建选择与 Surefire 报告校验读取同一清单，缺少或跳过任何核心测试都会失败。CI 自身回归还枚举仓库的 `*Test.java`，防止新增套件遗漏。原 `SampleTest` 依赖固定旧业务样例，`SecurityToolsTest` 仅打印加解密结果，因此不列入核心检查。
- **CI required**：汇总前三项，只有全部成功才通过；失败、取消或跳过均不能通过。作为分支必需状态检查使用，避免单项路径过滤导致检查缺失。

后端构建后还用当前依赖执行 `deploy/test_ip_https_proxy.py`：实际 Spring Boot 配置绑定、Tomcat RemoteIpValve 与原 MediaCookie 源码，核对仅信任 127.0.0.1 的协议转发及 Secure Cookie。该测试无需数据库或监听 socket，不能代替线上登录验收。

每个 PR 的新提交取消同一 PR 的旧运行。没有定时触发。Node/npm 版本遵循现有项目；Actions 使用完整提交 SHA 固定，任务只有仓库读取权限，不使用生产凭据。

菜单浏览器回归使用 `--ref "$GITHUB_SHA"` 编译真实 Header/TMenu，在 1440×1000 和 390×1200 视口通过 Chromium 鼠标输入测试危险链接、合法子菜单、站内路由、静态编辑器和 HTTPS 同页/新页跳转。HTTPS 目标全部在发起网络连接前拦截为合成响应，任何意外外联或浏览器错误均失败。`check_menu_browser_results.py` 要求本次 checkout 的完整 SHA、6 份源码的 Git blob 哈希、至少完整的 28 项行为和 18 次点击、8 张截图及一致计数；拒绝旧版本模式、其他提交、Node/JSDOM 替代和不完整报告。前端单独保存合成 JSON 与 PNG，不上传编译 bundle 或浏览器用户目录。

## 注册数据库验证

后端任务启动临时 MySQL 8.0 和 Redis 7.2 服务容器，使用固定测试端口 33306/36379。`registration_mysql.py` 只接受 GitHub 托管运行环境和当前工作区；在本地或自托管 runner 上直接拒绝。

脚本新建 `teachingopen_check_ci`，已存在即失败，不覆盖任何已有数据库。从版本库 SQL 提取 69 张空表，不导入原始 INSERT，只添加合成 student 角色及关闭状态的注册开关。真实注册迁移按顺序执行两次，检查重复执行兼容性，然后启动本次构建 JAR，使用完整外部配置替换内置环境配置。应用数据库账号只拥有测试库的读写权限，测试探针通过独立账号注入隔离库触发器故障。

复用 `deploy/verify_registration.py` 的 32 项 HTTP/SQL 检查：姓名/学校与补充汉字、手机号与口令保存、学生/教师身份、禁止提权、重复与并发注册、验证码登录、管理接口拒绝、资料写入失败时事务回滚、失败后重试及公开目录脱敏。结果记录 MySQL 版本、表数和实际 CI 提交。

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
