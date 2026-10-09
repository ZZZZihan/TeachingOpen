# 私有正式初始数据发布包

这个包冻结最新应用 JAR、完整前端 dist、注册升级 SQL 和仅保留管理员与真实课程的初始数据。它提供离线、可移植的审阅材料。它没有部署服务，不含云端域名、TLS 私钥、MySQL/Redis 新凭据或容器镜像锁；目标架构和云服务确定后还要配置并验收。

包内真实课程、原管理员的密码密文与盐必须始终留在私有目录，不能进入 Git、PR 附件、普通日志或公开文档。原管理员登录凭据须由授权操作者私下管理；发布工具不会猜测、生成或输出明文管理员密码。所有包目录为 `0700`，所有文件为 `0600`。目标服务使用独立运行副本，由操作者按实际服务用户授予必要读取权限。

## 构建与组合

使用可信、tracked 文件干净的最终候选工作区。构建需要已有 JDK 8、Maven、Maven 缓存与前端依赖，不自动安装工具。`build` 实际执行后端 `clean package` 和前端 `npm run build`，保存私有日志、源码输入清单和冻结产物；构建本身按项目默认跳过 Java 测试，功能测试和运行验收分别记录。

```sh
python3 deploy/launch_bundle.py build \
  --source "$SOURCE_DIR" --java-home "$JDK8_HOME" \
  --maven "$MAVEN_BINARY" --maven-cache "$MAVEN_CACHE" \
  --output "$NEW_PRIVATE_BUILD_DIR"

python3 api/dev/prepare_launch_data.py verify --package "$CLEAN_DATA_PACKAGE"

python3 deploy/launch_bundle.py create \
  --source "$SOURCE_DIR" --build "$NEW_PRIVATE_BUILD_DIR" \
  --data-package "$CLEAN_DATA_PACKAGE" --output "$NEW_PRIVATE_BUNDLE_DIR"

python3 deploy/launch_bundle.py verify \
  --bundle "$NEW_PRIVATE_BUNDLE_DIR" --source "$SOURCE_DIR" \
  --manifest-sha256 "$INDEPENDENTLY_FROZEN_MANIFEST_SHA256"
```

输出目录必须全新，其父目录必须已存在。输入与输出不能互相包含，路径不能经过符号链接。失败的私有目录保留供检查；缺少完成的 `build.json` 或 `manifest.json` 不能视为成功。创建和核验都不启动服务、不连接数据库、不发送 HTTP。

后续提交若只修改发布工具、文档或升级 SQL，可以复用已构建产物。工具会逐字节核对最终候选的 Java 主源码、资源、Maven POM 与前端构建输入，并分别记录 `build_source_commit` 和最终 `source_commit`。输入有任何变化则拒绝组合，必须从更新后的候选重新构建。源码清单和日志是构建方提供的证据；核验不证明恶意操作者无法同时伪造清单和产物。请由独立验收方保存返回的 manifest SHA256。

## 包内容与核验范围

```text
manifest.json                         最终源码 commit、构建 commit、输入与全部包文件的指纹
app/app.jar                           实际构建的可移植 JAR
web/dist/**                           实际构建的完整前端
web/nginx.conf                        候选已跟踪的同源 API/WebSocket 代理参考
initial-data/mysql/seed.sql            仅管理员与真实课程的 CREATE schema/数据
initial-data/uploads/**                297 个课程文件
initial-data/manifest.json             数据来源、净化计数与资源聚合指纹
initial-data/assets-manifest.json      私有资源路径与逐文件指纹
migrations/*.sql                      按最终源码冻结的注册升级 SQL
migrations/migration-manifest.json    独立升级清单；外层 manifest 钉住其 SHA256
migrations/registration_upgrade.py    明确的核验、预检、备份与应用入口
migrations/Dockerfile.db.reference     既有数据库镜像初始化次序参考
config/application-launch.properties.template
evidence/build.json                   构建工具版本、命令、源码与产物清单
evidence/*-build.log                   实际构建私有日志
tools/**                              冻结的组合/核验工具源码
RUNBOOK.md                            本说明
```

`verify` 检查全部不可变文件、逐文件字节数/SHA256、目录与文件权限、JAR/dist 与构建证据及数据摘要的关系。传入 `--source` 时额外要求当前 tracked 工作区干净、commit 一致、编译输入与升级文件一致，并实际执行数据包的离线核验。没有 `--source` 时只核验冻结包，不证明当前外部源码匹配。

没有工作区时，冻结包内主核验工具仍能独立检查文件、权限、构建证据和清单之间的关系：`python3 "$BUNDLE_DIR/tools/deploy/launch_bundle.py" verify --bundle "$BUNDLE_DIR" --manifest-sha256 "$FROZEN_SHA256"`。数据语义核验必须使用最终候选工作区中的 `api/dev/prepare_launch_data.py` 及其依赖；包内该文件只供源码审阅，不能作为脱离工作区的独立数据准备入口。

当前正式数据候选 v4 必须为 1 个正常管理员、5 门课程、83 个单元、297 个课程资源。原师生、班级、成员、作品、提交、草稿、讨论、消息和操作日志等业务历史不进入包。13 项旧站视觉配置与旧站 `teaching_menu` 导航清空，旧 logo/banner 附件不再引用；保留用户指定的白底现代首页、校园长廊照片和默认简洁导航，校园及默认品牌图片由前端 dist 提供。新用户注册档案在升级后应为 0。不要向此正式数据包注册测试用户；验收需要另外复制一份独立数据库与资源目录，验收过程中生成的数据也只保留在那份私有副本中。

## 新环境初始化与已有环境升级

新数据库仅在目标数据库确认为 0 个表的全新数据库且已获初始化授权后，按 manifest 的 `migration_order_new_database` 顺序执行：CREATE schema 与初始数据 SQL，再执行手机资料注册表升级，最后显式开启手机号资料注册。初始 SQL 不含 DROP，只创建表；已有表会使初始化失败。导入前必须核对数据包并查询实际表数；非 0 表的环境拒绝使用 seed。不要使用 `mysql --force` 或忽略导入错误，以免部分创建、部分插入。导入失败应保留错误与隔离库，定位原因后另用一个新空库重试，不向业务环境继续灌入。

已有数据库只能在单独授权、备份与回滚材料完成后，执行 manifest 的 `migration_order_existing_database`，禁止导入 `seed.sql`。手机资料注册表升级脚本保留已有注册开关值；随后的 enable 脚本表示操作者显式开启注册，会把有效且唯一的开关值改为开启。注册升级的幂等性、开启步骤和管理员菜单权限由升级 SQL 的专项验证负责。Docker 官方初始化目录仅在数据库数据目录为空时执行，重启已有数据容器不会补跑升级 SQL。

包内升级目录按 `01-phone-profile-registration.sql`、`02-enable-phone-registration.sql` 排序。读取外层 manifest 的 `registration_upgrade_manifest_sha256` 作为 `$UPGRADE_MANIFEST_SHA256`，先执行离线核验：

```sh
python3 "$BUNDLE_DIR/migrations/registration_upgrade.py" verify \
  --directory "$BUNDLE_DIR/migrations" --manifest-sha256 "$UPGRADE_MANIFEST_SHA256"
```

目标已有数据库的 `preflight` 和 `apply` 需要明确 MySQL 二进制、私有 `--defaults-extra-file` 与数据库名。预检会创建并移除保留的校验存储过程，属于目标库操作；正式应用前需单独授权并停止所有应用/管理员写入。`apply` 还要求明确 mysqldump、全新的私有备份路径、`--maintenance-confirmed` 与 `--restore-check-confirmed`，先通过预检并生成新的完整备份及收据，再执行升级。恢复检查必须来自操作者实际验证，不能靠勾选替代。DDL 不可事务回滚，任何错误都保留备份并停止，不能自动删除表或继续忽略错误。

初始 uploads 应复制到新的运行上传目录。保留原文件名和目录大小写，先核对资源 manifest，再允许应用写入。运行 uploads、webapp、日志、MySQL 与 Redis 各用独立可写目录，不在冻结包内写入。正式包不包含测试账号、Redis 挑战值或测试服务配置。

## 目标侧配置与启动

JAR、dist、SQL 和课程资源本身可跨 Linux amd64/arm64 迁移；JRE、MySQL、Redis、Nginx 镜像/安装包需要与目标 CPU 和文件系统相符。此包未锁定云端镜像，也未证明大小写敏感 Linux 文件系统上的数据库兼容性。目标确定后需记录工具/镜像版本、实际 `lower_case_table_names`、备份方式、资源容量、磁盘权限与数据库字符集。

把模板复制到目标侧 `0700` 私有配置目录，文件设为 `0600`。按目标填写所有 `@PLACEHOLDER@`：数据库完整 JDBC URL/应用用户名/密码、Redis 主机/端口/独占 database/密码、API 绑定地址/端口、对外 origin、运行 uploads/webapp/临时文件目录。MySQL 应用账号应限定所需数据库；数据库与 Redis 不公开暴露。模板单独声明所有应用必需配置，并禁用外部邮件、短信、第三方登录、云存储和搜索功能。

旧页头和登录组件仍用 `qiniu.staticDomain` 这个配置名拼接本地品牌素材地址，因此模板把它设为 `/api/sys/common/static`，与本地素材路径一致。这只是兼容旧组件的本地 URL 别名；`uploadType=local`，不会开启七牛上传，也不提供云存储凭据。

使用 Spring 的 `spring.config.location` 明确替换 JAR 内嵌配置，只启用 `launch`。不要使用内嵌 `dev`、`prod` 或测试 profile，也不要使用 `spring.config.additional-location` 叠加旧配置。目标配置包含凭据，启动命令只引用配置路径：

```sh
java -Xms256m -Xmx1g -jar "$RUNTIME_APP_JAR" \
  --spring.profiles.active=launch \
  --spring.config.location="file:$PRIVATE_CONFIG_FILE"
```

先在目标的 loopback/内部网络验证配置和数据库初始化。前端同源代理需要 `/api/` 保留 URI、API 后端实际地址、WebSocket 转发、上传限制和媒体 Range 支持。`web/nginx.conf` 的 `api:8080` 以及静态目录是容器参考值，必须按目标运行布局调整；TLS、域名、证书、反向代理暴露端口和运维凭据尚未配置。

通过目标侧启动不等于业务验收。独立验证副本至少检查：1admin/0历史业务/0注册档案、5课程83单元、297课程文件指纹、白底现代首页的长廊照片/默认导航/真实课程与封面、管理员登录与课程列表/媒体权限、学生/教师手机号注册与完整资料、初始首页人数、学校搜索与同名注册、禁止越权接口、刷新/退出与服务重启恢复。注册、媒体和课程行为通过后仍需用户人工验收。云目标与域名确定后再交付二维码。

## 交付状态与回滚

冻结包核验、实际构建、隔离运行、云端部署和人工验收是五项独立证据。manifest 中的 `services_started`、`runtime_data_checked`、`cloud_deployed`、`human_accepted` 固定为 `false`，只描述离线创建动作；运行验收结果另存摘要，不能改写冻结 manifest 冒充已经部署。

早于 v4 的数据包与 `bundle-b245245cbfcc` 留在本机私有目录作历史证据；该 bundle 的包外状态记录为历史候选，不能拿它代替用户修正首页视觉后的最终包。每次正式组合都使用新的目录、最终源码 commit 和当前数据 manifest，不覆盖旧候选。

上线前保存旧 JAR/dist/实际配置、数据库备份、uploads 备份以及目标运行版本。注册升级新增数据后，代码回滚与数据库回滚必须由操作者协调；不要以删除注册表代替备份恢复。发布工具不停止服务、不清理数据、不执行回滚，也不自动推送、合并或发布。
