# 独立本地开发环境

这组工具用于从源码构建并建立仅含合成数据的本地环境。已经验证的平台是 macOS arm64；不是生产部署脚本，也没有证明 Linux、Intel Mac、Windows 或生产定制包兼容性。

当前分支包含后端构建及禁用第三方登录的启动修复。课程/作业权限修复在后续 PR 中交付，此处的健康与环境检查不代表业务或权限已验收。

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
