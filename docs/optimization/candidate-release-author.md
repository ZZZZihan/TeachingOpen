# 冻结候选验证包：作者记录

日期：2026-10-05。分支：`feature/candidate-release-bundle`。基线：Nginx #66 后的 `8b444cd35330f26283aa9ff8b85c9b291d836c48`。

本项增加 `deploy/candidate_release.py` 与 `deploy/CANDIDATE.md`，提供标准库 Python 的 `create` / `verify`。独立测试文件及其记录由其他 Agent 负责；作者不把自己的自检称为独立审查或人工验收。

实际产品候选通过显式 `--source` 输入，要求 tracked-clean 和全部实际 helper 输入被该 commit 跟踪。PR 分支基线并未包含完整产品候选的原生夹具工具；因此这个工具不会宣称自己的分支就是冻结 JAR 的完整构建源。manifest 记录所用 commit、helper 哈希、构建产物的用户指定 SHA256 和工具自身 SHA256，不证明构建来源。

范围为纯离线打包：原样复制 JAR、完整 dist、#66 Nginx 配置；抽取 69 表空 schema；通过可信 source 的纯函数生成五账号、两班、三课程、角色菜单和自制素材；用 JDK 8 在私有临时目录编译既有密码 helper，密码/盐只经 stdin；每次创建独立随机私有凭据和 localtest 派生配置。拒绝已存在 output、tracked dirty、未跟踪 helper、输入 SHA256 不符、重复 JSON key、非法路径、symlink 和特殊文件。复制前后对输入和输出做完整哈希核对。

固定 Compose 使用官方 Linux/arm64 不可变镜像、四服务共同连接的 `candidate` internal 网络、仅 web 连接的 `ingress` 普通 bridge、随机项目名、唯一 loopback web 端口、只读冻结输入和 bundle 内独占 data。沿用官方 MySQL/Redis entrypoint；公开 dist 使用 Nginx worker 可读权限，私有根目录隔离宿主其他用户。API 有固定 JVM heap 和容器内存上限。既有 logback 的 `../logs` 显式挂到独占 `data/logs`。服务启动和停止由标准 Compose 操作完成，工具本身不执行 Docker。

`verify` 检查不可变输入清单、必需静态闭包、权限与固定 Compose/Nginx/image 契约，只检查五个运行目录本身为普通目录，并不进入数据库、Redis、上传、webapp 或日志运行内容。它不提供对恶意 manifest 重写的防护；公开和私有素材的初始化预期哈希单独记录，便于后续真实探针核对。

作者实际执行的检查：

- Python `ast.parse` 语法检查通过。
- 使用真实临时目录的小自检通过：路径穿越/非 canonical 路径拒绝、重复 JSON key 拒绝；最终 Compose 的自检确认四服务共享 internal 网络、仅 web 额外连接普通 bridge、仅 web 发布指定 loopback 端口。
- 最终工具 SHA256 为 `ee6eae518411b09290c68a81ab76c40a43f55c83c7e3e80ce5bff2417beb1f67`，已通知根 Agent。独立测试发现 Python 的 `True == 1` 会使 manifest `format: true` 被接受，作者补充了整数类型守卫并重新冻结。后续若修复改变它，需更新本文并重新冻结。

根 Agent 的真实 Docker 首次启动进一步发现：MySQL 完成 schema 与夹具初始化后，`mysqladmin` 健康检查拒绝 `[client]` 中的 `local-infile=0`。作者将这个仅适用于 mysql CLI 的选项移至 `[mysql]` 分组，保留 `[client]` 的通用连接项和原有健康判据。这个发现来自真实启动，不是静态配置检查；根 Agent 保留该失败 bundle 与运行记录，并重新创建新 bundle 验证修复，结果另记。

后续 fresh bundle 的真实启动确认 MySQL healthy、API Started，但 Docker 29.4 仅有 internal 网络时，HostConfig 声明的 loopback PortBindings 没有形成实际 NetworkSettings.Ports 映射，宿主无法访问 web。作者按 [Docker 官方前端双网络布局](https://docs.docker.com/engine/network/#connecting-to-multiple-networks) 给 web 单独增加本项目拥有的 `ingress` 普通 bridge，同时保留四服务的 internal 网络及唯一 loopback 发布。API、MySQL、Redis 的网络没有放宽。根 Agent 保留旧 bundle 并创建新的 bundle 执行真实验证；静态配置声明不能代替实际端口可达证据。

根 Agent 随后在 fresh bundle04 的真实探针得到 45/45 通过，并在 MySQL 查询中确认版本 `8.4.6`、`lower_case_table_names=2`、69 表和五个用户。工具没有显式设置大小写参数；本次 macOS 宿主 bind 文件系统上的值 `2` 不能作为大小写敏感 Linux 文件系统或实际 Z820 的 `0` 值兼容性证明。作者仅修正文档中先前“Linux MySQL 保留默认表名大小写行为”的过强表述，冻结代码未改变。最终运行和探针证据仍由根 Agent 记录。

作者没有启动 Docker、服务、HTTP 或数据库，没有读取真实生产副本，没有提交或推送。完整 create/verify 负例由独立测试 Agent 运行；真实冻结输入创建和 Linux 容器运行由根 Agent 完成后另记证据。本记录只覆盖上述作者实现与自检。
