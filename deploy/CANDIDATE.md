# 冻结候选的 Linux 本机隔离验证包

`candidate_release.py` 把明确指定的可信集成候选、冻结 JAR 和完整前端 dist 复制到一个新的私有目录，并生成合成数据库初始化材料、随机凭据和 Docker Compose 配置。`create` 与 `verify` 都不启动 Docker、服务、HTTP 请求或数据库。这个包用于本机 Linux/arm64 容器验证；生产部署、真实数据迁移和人工验收另有各自的证据与授权。

工具所在的 PR 分支以 Nginx 修复 #66 为基础。这个分支本身不包含全部产品修复和原生夹具工具。`--source` 必须指定已经集成所需产品修复、`api/dev/` 夹具工具及自制素材的候选 Git 工作树。工具要求该工作树的 tracked 文件干净，且实际调用的 helper、模板、原始 schema SQL、自制素材和 Nginx 配置均由该 commit 跟踪；无关 untracked 文件可以保留，构建得到的 `web/dist` 也可以是 untracked。

`--source` 会执行其中的 Python 纯夹具函数，并用其中的 `FixturePassword.java` 与 `PasswordUtil.java` 临时编译密码工具。这里的“可信”是使用者明确选择可信源码的边界，不是对不可信代码的沙箱。工具不调用既有 macOS 运行时的 `create`、`cold_runtime`、`seed` 或服务操作，也不改动其平台守卫。

## 创建和核对

Python 3 标准库足够运行本工具。创建时另外需要明确的本机 JDK 8 路径，工具仅临时编译密码算法的两个 Java 文件；不会构建后端或前端。密码和盐通过 Java 子进程 stdin 传入，不放进命令参数或输出报告。

先由构建方冻结 JAR SHA256 和 dist manifest SHA256，再显式传给创建命令。dist manifest 是一个扁平 JSON 对象，每个相对 POSIX 文件路径对应 `{ "bytes": 123, "sha256": "64位小写十六进制" }`。它必须列出 `--source/web/dist` 的全部文件；缺失、多余、重复 JSON key、特殊文件、符号链接和路径穿越都会被拒绝。工具不假定文件总数。

```sh
python3 deploy/candidate_release.py create \
  --source "$SOURCE_DIR" \
  --jar "$FROZEN_JAR" \
  --jar-sha256 "$FROZEN_JAR_SHA256" \
  --dist-manifest "$FROZEN_DIST_MANIFEST" \
  --dist-manifest-sha256 "$FROZEN_DIST_MANIFEST_SHA256" \
  --java-home "$JDK8_HOME" \
  --output "$NEW_BUNDLE_DIR" \
  --port 18190

python3 deploy/candidate_release.py verify --bundle "$NEW_BUNDLE_DIR"
```

输出目录必须不存在，其父目录必须已存在，且必须位于 source 和两个输入文件所在目录之外。工具拒绝输入路径、输出路径及其任何父路径上的符号链接。macOS 的 `/var`、`/tmp` 常为符号链接，使用这些临时目录时需传入其真实路径。创建失败时保留私有的不完整目录，缺少 `manifest.json` 表示它没有创建成功；工具不会覆盖它重试。

输出 JSON 仅包含目录、源 commit、manifest SHA256、文件数量、端口、Compose 项目名等摘要。其中 `services_started: false` 表示这条离线命令没有启动服务，并非查询 Docker 后得出的运行状态；`runtime_data_checked: false` 表示没有核验运行数据。随机凭据、密码哈希和盐保存在私有 bundle 内，不能复制到 Git、公开报告或共享目录。`config/credentials.json` 的五个合成账号共用 `test_user_password`：`fixture_admin`、`fixture_teacher_a`、`fixture_teacher_b`、`fixture_student_a`、`fixture_student_b`。MySQL root、应用 MySQL 账号和 Redis 各有独立随机密码。

## 文件和权限

```text
manifest.json                         冻结输入和不可变文件的 SHA256/bytes
compose.json                          四个标准官方镜像的明确隔离配置
app/app.jar                           原样复制的冻结 JAR
web/dist/**                           dist manifest 对应的全部公开应用文件
web/nginx.conf                        #66 的原样 Nginx 配置
config/application-localtest.properties
config/credentials.json
config/mysql-root-password
config/mysql-app-password
config/mysql-client.cnf
config/redis.conf
init/01-schema.sql                    原 SQL 中抽取的 69 个空表定义
init/02-fixtures.sql                  纯合成的五账号、两班、三课程和角色菜单
data/mysql/                          MySQL 独占运行数据
data/redis/                          Redis 独占运行数据
data/uploads/                        自制素材、合成作业，后续允许应用修改
data/webapp/                         应用独占运行目录
data/logs/                           既有 logback 的 /logs 输出
```

bundle 根目录是 `0700`，`config/`、`app/` 和 `data/` 初始为 `0700`，其他私有文件为 `0600`。Nginx 使用官方默认 worker，因此公开 dist 文件和 Nginx 配置为 `0644`，`web/` 及 dist 内目录为 `0755`。MySQL 初始化 SQL 和单独只读挂载的 MySQL 密码文件为 `0444`；`init/` 是 `0755`。Redis 的单独只读配置也为 `0444`，使官方 entrypoint 切换到 redis 用户后能读取。宿主上其他用户仍受 bundle 根目录和 `config/` 的 `0700` 阻挡。

MySQL、Redis 沿用官方 entrypoint，由它们初始化并调整自己的独占 data 目录权限。工具不绑定宿主 UID，也不把 Redis 改为 root 服务。`verify` 只确认 `data/` 下恰有五个约定的普通目录且目录本身无符号链接，不进入运行目录，不检查运行后 UID、mode、数据库记录或上传内容。`manifest.fixtures` 冻结公开 `role-flow/cover.png` 和私有 `role-flow/lesson.mp4` 的字节数与 SHA256，供另行的真实运行探针核对。

私有 `mysql-client.cnf` 的 `[client]` 分组只放 mysql 和 mysqladmin 共用的连接项，`local-infile=0` 放在 `[mysql]`，以免健康检查读取不支持的选项。

初始化 SQL 由既有 quote-aware `extract_schema` 提取 CREATE 定义，并由 `base_records`、`generated_assets`、`ui_records`、`expected_after` 合成夹具；原 SQL 的 INSERT、生产配置和真实用户资料不进入 bundle。自制素材来自被 helper 检查过的固定文件及其纯生成内容。每次 create 都生成新凭据和五个独立盐，不读取既有运行环境的凭据。

## Compose 的固定边界

Compose 使用随机 `teaching-candidate-` 项目名，拥有两个独占网络。四个服务 `db`、`redis`、`api`、`web` 共同连接 `candidate` internal 网络，只有 web 另外连接 `ingress` 普通 bridge（显式 `internal: false`），用于宿主访问。只有 web 发布 `127.0.0.1:18190:80`，指定 `--port` 时只改变这个 loopback 端口。API 的 8080、MySQL 的 3306、Redis 的 6379 仍只在 internal 网络内。这个布局对应 [Docker 官方的前端双网络示例](https://docs.docker.com/engine/network/#connecting-to-multiple-networks)：前端连接普通 bridge 与 internal 后端网络，后端服务保持 internal 隔离。没有固定 `container_name`、host 网络、预建 external 网络、Docker socket 或 bundle 外的宽目录挂载。JAR、dist、Nginx、配置和初始化材料均为只读 bind；运行 data 是各服务的独占可写 bind。

四个镜像均固定官方不可变 digest 和 `linux/arm64` 平台。JRE、MySQL、Redis 使用平台 child digest，Nginx 使用已核验的本机缓存 index digest并显式选择同一 arm64 平台。锁定的版本来源与实际镜像运行证据由该候选的外部 image-lock 记录提供；离线创建工具本身不访问 registry 或核验 daemon 缓存。

API 启动命令固定 `dev,localtest` 和 `spring.config.additional-location=file:/app/config/application-localtest.properties`，保留已验证的 dev 必需配置，再用派生 localtest 覆盖。覆盖仅连接 `db:3306`、`redis:6379`、容器 `0.0.0.0:8080` 和自身 uploads/webapp。外部邮件、第三方登录、云存储、短信、搜索等沿用已审查模板的 disabled 或 loopback sink。JVM 固定 `-Xms256m -Xmx1g`，API 内存上限 1536 MiB；MySQL、Redis、Nginx 上限分别为 1 GiB、256 MiB、128 MiB。

工具没有显式设置 MySQL 的 `lower_case_table_names`。本次在 macOS 宿主 bind 目录上运行 Linux/arm64 MySQL 8.4.6，实际查询值为 `2`；Linux 容器镜像本身并不能证明底层文件系统大小写敏感。这份本机运行证据尚未证明大小写敏感 Linux 文件系统上的值 `0` 及兼容性，也没有实际 Z820 运行证据。

创建成功并完成 verify 后，由操作者通过标准 Compose 生命周期启动和停止：

```sh
docker compose --project-directory "$NEW_BUNDLE_DIR" \
  -f "$NEW_BUNDLE_DIR/compose.json" up -d

docker compose --project-directory "$NEW_BUNDLE_DIR" \
  -f "$NEW_BUNDLE_DIR/compose.json" down
```

`down` 保留 bind 的 data 目录。这个工具没有 prune、自动删除数据、重置数据库或自动恢复的入口。MySQL 的 init SQL 仅在其数据目录首次初始化时执行，已有运行数据上的重新启动不会重新灌入夹具。

## 独立运行探针

`probe_candidate_runtime.py` 用于新建合成包在本机 `18190` 端口的受控验证，需要当前 Docker context 指向启动这个包的 daemon，且 `docker` 在 PATH 中。它会先执行相同冻结工具的 verify，核对自有容器、镜像、网络、挂载和实际端口映射，再通过真实 HTTP 执行固定 45 项检查。探针不适用于已有生产数据包，也不接受另一个测试端口。

```sh
python3 deploy/probe_candidate_runtime.py \
  --bundle "$NEW_BUNDLE_DIR" \
  --release-tool deploy/candidate_release.py \
  --output "$NEW_PRIVATE_REPORT_DIR/runtime.json"
```

报告路径必须全新，父目录若已存在则必须已经私有；探针不改变既有目录权限。报告只记录状态、摘要与证据指纹。探针为五个自制账户读取自有 Redis 的对应挑战值并调用普通登录 API，不能把这一步视为普通浏览器登录验收。管理员课程/单元创建、修改、删除检查会核对数据库；Python 流程只验证个人草稿与上传文件，保留合成草稿和附件作为本包私有证据。再次执行整套探针需新建包，不能在旧数据上冒充首次运行。探针不自动启动或停止容器，完成后仍由操作者执行前述 down。

`verify` 证明当前不可变文件与当前私有 manifest 中的清单一致，同时核对必需文件、权限、固定 Compose、镜像和 Nginx 契约。它不证明 JAR 确由所记 commit 编译，也不抵御一个能同时重写文件和 manifest 的操作者。调用者可以在独立证据中保存返回的 manifest SHA256 作为自身的冻结参考。服务是否真实启动、数据库是否正确初始化、页面和媒体是否可用，以及人工验收是否通过，必须分别报告。
