# 独立本地开发环境

这组工具用于从源码构建并建立仅含合成数据的本地环境。已经验证的平台是 macOS arm64；不是生产部署脚本，也没有证明 Linux、Intel Mac、Windows 或生产定制包兼容性。

当前分支包含后端构建、启动、认证响应及课程管理角色限制。单元详情、作业等资源权限仍在后续 PR 交付；健康与环境检查不代表业务或权限已验收。

## 工具与构建

使用 Python 3.9+，以及 [固定工具清单](dev/toolchain.json) 中的 JDK 8、Maven、MySQL、Redis。该清单保留之前下载时核对的官方来源和摘要。新机器应下载对应归档并核对摘要，解压到独立工具目录；Redis 7.2.9 在其源码目录执行 `make -j4 MALLOC=libc`。脚本不会安装全局工具、下载依赖运行时或修改系统服务。

工具目录应包含 `apache-maven-3.9.16`、`mysql-8.4.6-macos15-arm64`、`redis-7.2.9` 及 `zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home`。本机已有这组工具时直接复用。

先设置本机路径；`TEACHING_REPO` 必须是包含 `api/` 和 `web/` 的实际源码仓库或 worktree。运行目录应使用项目 `.devspace/` 的一个新直接子目录，尽量保持路径简短，避免 macOS 的 Unix socket 路径长度限制。

```sh
TEACHING_WORKSPACE=/Users/xuzihan/Documents/Projects/TeachingOpen
TEACHING_REPO="$TEACHING_WORKSPACE/.devspace/worktrees/isolated-local-runtime"
TEACHING_TOOLS="$TEACHING_WORKSPACE/.devspace/backend-runtime/tools"
TEACHING_JAVA="$TEACHING_TOOLS/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home"
TEACHING_MAVEN="$TEACHING_TOOLS/apache-maven-3.9.16/bin/mvn"
TEACHING_CACHE="$TEACHING_WORKSPACE/.devspace/backend-runtime/m2"
TEACHING_RUNTIME="$TEACHING_WORKSPACE/.devspace/local-new"

cd "$TEACHING_REPO/api"
JAVA_HOME="$TEACHING_JAVA" "$TEACHING_MAVEN" -B -s dev/maven-settings.xml \
  -Dmaven.repo.local="$TEACHING_CACHE" clean package
```

首次构建需要网络；`maven-settings.xml` 只覆盖本次命令的仓库镜像，缓存路径可换成自己的新目录。本轮实际构建使用已有缓存。父 POM 跳过 Java 测试，`BUILD SUCCESS` 只证明编译打包；后续检查分别执行。

## 从空目录初始化

在源码仓库根目录执行以下命令。四个端口可以调整，必须互不相同且空闲；全部服务只绑定 `127.0.0.1`。

```sh
cd "$TEACHING_REPO"
python3 api/dev/prepare-local.py --runtime "$TEACHING_RUNTIME" --tools "$TEACHING_TOOLS" \
  --mysql-port 13316 --redis-port 16389 --backend-port 18101 --frontend-port 18102
```

初始化会立即启动独立 MySQL 和 Redis。它只从上游 SQL 提取 69 条建表定义，不导入原始 INSERT；随后创建五个合成账号、两个班级、两门课程及合成作业附件。账号是 `fixture_admin`、`fixture_teacher_a/b`、`fixture_student_a/b`。随机口令只在运行目录的私有 `config/credentials.json` 中；目录权限 700，凭据和运行配置权限 600，不复制到仓库或聊天。

脚本拒绝覆盖已有目录，端口冲突时在创建运行目录前退出。初始化中途失败可能保留该新目录或其服务；先按私有日志检查归属并处理本任务服务，再改用新目录重试，不删除未知数据。运行端口保存在 `ports.json`；旧环境没有此文件时沿用 13306/16379/18091/18092，支持继续操作原环境。

## 启动与检查

```sh
python3 api/dev/run-backend.py start --runtime "$TEACHING_RUNTIME" --java-home "$TEACHING_JAVA"
curl --fail http://127.0.0.1:18101/api/actuator/health
python3 -m unittest discover -s api/dev -p 'test_*.py'
python3 api/dev/verify-environment.py --runtime "$TEACHING_RUNTIME" \
  --output "$TEACHING_RUNTIME/environment-check.json"
```

启动命令派生后台进程，返回 PID 不表示服务健康；等待健康接口为 `UP` 后再运行检查。日志使用新的私有文件，路径记录在 `backend-process.json`。若启动失败，检查该私有日志；不要直接发布完整日志或配置。

`verify-environment.py` 核对 MySQL/Redis 归属、实际运行 JAR 与当前 worktree 的摘要、69 张表、合成账号/角色、课程读取和附件。它不验证三角色业务或越权边界。`test_extract_schema.py` 验证 DDL 提取不会混入 INSERT 数据。

前端按 [前端构建说明](../web/BUILDING.md) 生成 `web/dist/`，然后执行：

```sh
python3 api/dev/serve-frontend.py --runtime "$TEACHING_RUNTIME" --dist "$TEACHING_REPO/web/dist"
```

浏览器访问 `http://127.0.0.1:18102/courseList`。代理跟随运行目录端口；后端停机时返回 502，不断开连接而不给响应。请求日志不记录路径、查询、正文或请求头，避免旧接口把凭据放在路径中时被记录。CSP 阻止遗留远程统计脚本；该本地代理不支持 WebSocket，也不是生产服务器。

## 停止与再次启动

先在前端终端 Ctrl+C，然后停止本任务后端及数据库/Redis：

```sh
python3 api/dev/run-backend.py stop --runtime "$TEACHING_RUNTIME" --java-home "$TEACHING_JAVA"
python3 api/dev/stop-local.py --runtime "$TEACHING_RUNTIME"
```

后端停止操作核对 PID 对应的完整 JAR 路径和 profile，并等待进程退出；数据库和 Redis 停止前核对真实数据目录及端口。数据、凭据、附件和日志保留。Redis 不持久化，重启后会话和验证码失效。

再次启动保留环境，不重新导入或覆盖数据：

```sh
python3 api/dev/start-local.py --runtime "$TEACHING_RUNTIME"
python3 api/dev/run-backend.py start --runtime "$TEACHING_RUNTIME" --java-home "$TEACHING_JAVA"
# 健康接口 UP 后：
python3 api/dev/verify-environment.py --runtime "$TEACHING_RUNTIME" \
  --output "$TEACHING_RUNTIME/environment-after-restart.json"
```

本轮还保留了 [环境与重启结果](../docs/optimization/local-runtime-pr.md)。后续切换源码分支时，先用旧 worktree 的停止脚本停止其后端，再从新 worktree 构建并启动；不要覆盖正在运行的 JAR。若要使用已有数据之外的新 fixture，另建环境。

## 数据库与附件备份、全新隔离恢复

`backup-local.py` 将本地合成环境的数据库和 `uploads/` 作为同一份快照保存。仅适用于上述 macOS arm64 工具和合成账号环境；不用于生产、在线备份、跨版本迁移或导入来历不明的 SQL。先停止该环境的后端和其他附件写入程序；快照期间工具保持本机 MySQL 全局读锁，完成后释放。失败时不会写入有效的完成清单，但可能保留私有的不完整目录。

在包含此工具的源码仓库中执行；停止和启动后端必须使用实际运行该 JAR 的 worktree 中的 `run-backend.py`。以下假设它就是 `$TEACHING_REPO`：

```sh
TEACHING_SNAPSHOT="$TEACHING_WORKSPACE/.devspace/local-snapshot-new"
TEACHING_RESTORED="$TEACHING_WORKSPACE/.devspace/local-restored-new"
python3 api/dev/run-backend.py stop --runtime "$TEACHING_RUNTIME" --java-home "$TEACHING_JAVA"
python3 api/dev/backup-local.py create --runtime "$TEACHING_RUNTIME" --snapshot "$TEACHING_SNAPSHOT"
# 无论备份成功或失败，检查后恢复原环境的后端，并等待健康接口 UP。
python3 api/dev/run-backend.py start --runtime "$TEACHING_RUNTIME" --java-home "$TEACHING_JAVA"
python3 api/dev/backup-local.py inspect --snapshot "$TEACHING_SNAPSHOT"

python3 api/dev/backup-local.py restore --snapshot "$TEACHING_SNAPSHOT" \
  --runtime "$TEACHING_RESTORED" --tools "$TEACHING_TOOLS" \
  --mysql-port 13336 --redis-port 16409 --backend-port 18131 --frontend-port 18132
python3 api/dev/run-backend.py start --runtime "$TEACHING_RESTORED" --java-home "$TEACHING_JAVA"
# 等待 http://127.0.0.1:18131/api/actuator/health 为 UP 后：
python3 api/dev/verify-recovered-business.py --runtime "$TEACHING_RESTORED" \
  --snapshot "$TEACHING_SNAPSHOT" \
  --jar "$TEACHING_REPO/api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar" \
  --output "$TEACHING_RESTORED/recovered-business-check.json"
```

快照和恢复目录都必须是 `.devspace/` 的非符号链接直接子目录，且目的地必须不存在；恢复端口必须空闲、互不相同并与源环境不同。工具先核对快照清单和文件 SHA-256，再初始化新 MySQL/Redis，以仅有新数据库权限的账号导入。恢复时重新生成数据库和 Redis 口令，保留合成用户登录口令；Redis 会话不恢复，必须重新登录。恢复后的每张表结构、逐列编码的行摘要和附件文件摘要全部相等才写 `restore-result.json`。该文件的 `business_read_verified: false` 表示尚须单独运行接口检查，不能凭导入成功声称业务通过。

快照含数据库、用户密码散列及合成账号口令，必须保留在权限 700 的本机私有目录，不提交 Git、不复制到共享成果。SHA-256 清单检测意外损坏，不提供来源认证或加密。只恢复本任务自己创建、可信的快照。工具拒绝附件符号链接、特殊文件，以及包含视图、触发器、存储过程或事件的定制数据库，避免静默漏备份；空附件目录不参与文件摘要。恢复失败时保留新目录及其服务用于诊断，不覆盖、回滚或删除其他环境，也不自动启动应用。

业务检查使用真实 HTTP 合成账号登录，读取恢复后的课程、作品和附件，验证拒绝路径；会产生正常认证审计日志，作品查看计数在结束时复原。后续切换演练发现，现有作品详情接口还会改写 `update_time/update_by`；这个脚本目前未复原这两个字段，不能据此声称目标全库不变。该业务问题另行修复。它不是浏览器验收。完成演练后可用上述停止命令停掉新环境，数据仍保留。此次实际恢复、故障拒绝和源环境保护结果见 [恢复演练记录](../docs/optimization/local-backup-restore-pr.md)。异机灾备、定时保留策略另行验证，本地候选切换见下节。

## 冻结候选包、切换与回退

`candidate-local.py` 面向专用的本机合成环境，把已经构建的 JAR、前端和本地代理复制到新的候选目录；文件摘要和来源工作区提交写入清单，目录/文件设为仅所有者可读（目录可进入）。它不构建、不证明产物来自某次构建，也不签名；先核对对应构建记录和产物摘要。候选目录必须是 `.devspace/` 的新直接子目录，源工作区必须干净。运行配置和凭据仍留在运行目录，不放进候选包。

前置条件：已按本文件准备隔离数据库/Redis和构建工具；运行环境的应用端口没有由其他方式启动的进程。如果普通 `run-backend.py` 或手动前端还在运行，先通过原工作区的停止方式处理，工具不会接管未知进程。保留至少前后两份候选，不覆盖正在运行或用于回退的包。

```sh
# 在含本 PR 脚本的源码 worktree 根目录执行，数据库/Redis 已启动。
# 路径按实际工作区调整。两份 web/dist 必须分别构建并有对应构建记录。
TEACHING_BACKEND_REPO="$TEACHING_WORKSPACE/.devspace/worktrees/assignment-list-contract"
TEACHING_OLD_WEB="$TEACHING_WORKSPACE/.devspace/worktrees/candidate-switch-previous"
TEACHING_NEW_WEB="$TEACHING_WORKSPACE/.devspace/worktrees/product-candidate"
TEACHING_OLD_BUNDLE="$TEACHING_WORKSPACE/.devspace/release-old-new"
TEACHING_NEW_BUNDLE="$TEACHING_WORKSPACE/.devspace/release-new-new"

python3 api/dev/candidate-local.py package --runtime "$TEACHING_RUNTIME" \
  --bundle "$TEACHING_OLD_BUNDLE" --backend-repo "$TEACHING_BACKEND_REPO" --frontend-repo "$TEACHING_OLD_WEB"
python3 api/dev/candidate-local.py package --runtime "$TEACHING_RUNTIME" \
  --bundle "$TEACHING_NEW_BUNDLE" --backend-repo "$TEACHING_BACKEND_REPO" --frontend-repo "$TEACHING_NEW_WEB"
python3 api/dev/candidate-local.py activate --runtime "$TEACHING_RUNTIME" \
  --bundle "$TEACHING_OLD_BUNDLE" --java-home "$TEACHING_JAVA"
python3 api/dev/candidate-local.py activate --runtime "$TEACHING_RUNTIME" \
  --bundle "$TEACHING_NEW_BUNDLE" --java-home "$TEACHING_JAVA"
python3 api/dev/candidate-local.py rollback --runtime "$TEACHING_RUNTIME" --java-home "$TEACHING_JAVA"
python3 api/dev/candidate-local.py status --runtime "$TEACHING_RUNTIME"
```

每次切换先校验目标及上一候选全部文件摘要、运行环境归属和表结构。表结构比较忽略自增计数器，不执行迁移、数据库回滚或兼容性推断；不同结构拒绝切换。进程 PID、启动时间、命令中的候选/配置路径，以及真实监听端口的 PID 都要匹配；先检查两个进程，再停止其中任何一个。操作锁阻止并发切换，候选状态用原子替换保存。

切换会短暂停服务。新后端须健康 UP，新前端须提供字节匹配的 HTML，才记录 ready；这不是业务验收，随后应跑真实业务检查。新候选启动失败时尝试恢复上一候选，成功也返回失败状态/非零退出码，表示请求的新版本没有上线。若恢复同样失败，保留 `recovery-required` 及新旧引用，按私有日志检查。`--timeout` 是每次后端启动的等待秒数，默认 45，范围 1–120；过短会同时影响失败后的恢复。

控制脚本被终止后，先查看 `status` 的 recorded 与 observed（实时进程/端口）。如果记录为 switching 或 recovery-required，明确恢复到中断前的版本：

```sh
python3 api/dev/candidate-local.py recover --runtime "$TEACHING_RUNTIME" --java-home "$TEACHING_JAVA"
python3 api/dev/candidate-local.py stop --runtime "$TEACHING_RUNTIME" --java-home "$TEACHING_JAVA"
python3 api/dev/stop-local.py --runtime "$TEACHING_RUNTIME"
```

演练覆盖了新后端 PID 已记录、就绪前终止控制脚本的场景；没有证明任意时刻断电或强杀都能自动恢复。进程刚创建但 PID 尚未写入等窗口需要人工核对，工具拒绝停止未知进程。新方式在 `runtime/webapp` 中运行冻结 JAR，使遗留相对日志目录落在本环境的 `logs/`；原普通启动命令保持原工作目录。快照、数据库、附件不会随版本回退而回退。实际范围、五阶段业务检查和发现的作品审计字段问题见 [候选切换演练](../docs/optimization/local-candidate-switch-pr.md)。

## 课程管理权限检查

在新建合成环境启动本候选后运行：

```sh
python3 api/dev/verify-course-management.py --runtime "$TEACHING_RUNTIME" \
  --output "$TEACHING_RUNTIME/course-management-check.json"
```

脚本校验实际 JAR、数据库和缓存归属后，执行真实登录、管理请求及数据/附件核对；只写本次探针数据，结束后恢复业务表和测试角色。角色切换会清理该合成账号在隔离 Redis 中的权限缓存，不用于生产。导入只检查权限及空文件请求校验，完整角色页面尚未验收。行为、源码摘要及已知缓存问题见 [课程管理 PR 记录](../docs/optimization/course-management-pr.md)。

权限缓存数据库不一致问题在当前后续候选中已修复。可运行 `python3 api/dev/verify-role-cache.py --runtime "$TEACHING_RUNTIME" --output "$TEACHING_RUNTIME/role-cache-check.json"` 检查实际缓存位置、退出清理及角色变化后的重新登录；被测转换期间不直接清理缓存。范围与结果见 [权限缓存 PR 记录](../docs/optimization/role-cache-pr.md)。
