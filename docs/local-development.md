# 本地开发与运行指南

本指南对应 `integration/product-candidate` 的完整教学版本。首次获取代码时明确选择该分支；默认 `main` 尚未包含全部产品代码。以下命令用于创建新的本地合成环境，不用于修改既有服务或导入生产数据。

## 工具准备

前端使用仓库 `web/.nvmrc` 记录的 Node 26.7.0 和 `web/package.json` 中的 npm 11.19.0。后端使用 JDK 8、Maven 3.9.16，开发工具需要 Python 3.9+、MySQL 8.4.6 和 Redis 7.2.9。

原生初始化工具依赖 macOS arm64 工具目录布局。归档来源和摘要见 [工具清单](https://github.com/ZZZZihan/TeachingOpen/blob/integration/product-candidate/api/dev/toolchain.json)；新机器先准备对应工具，不要将整台电脑的配置复制到项目。工具根目录应包含：

```text
apache-maven-3.9.16/bin/mvn
mysql-8.4.6-macos15-arm64/bin/mysql
mysql-8.4.6-macos15-arm64/bin/mysqld
redis-7.2.9/src/redis-server
zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home/bin/java
```

Redis 归档需在源码目录完成构建。初始化工具不会替你下载或安装这些程序。Linux/arm64 本机容器验证使用 [候选包工具](https://github.com/ZZZZihan/TeachingOpen/blob/integration/product-candidate/deploy/CANDIDATE.md)，不是同一套原生初始化步骤。

在刚获取的仓库根目录设置路径。把 `/absolute/path/to/teaching-tools` 替换成真实工具根目录，保持开发路径较短，避免 macOS Unix socket 路径长度限制：

```sh
TEACHING_REPO="$(pwd)"
TEACHING_TOOLS="/absolute/path/to/teaching-tools"
TEACHING_JAVA="$TEACHING_TOOLS/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home"
TEACHING_MAVEN="$TEACHING_TOOLS/apache-maven-3.9.16/bin/mvn"
TEACHING_RUNTIME="$TEACHING_REPO/.devspace/role-flow-dev"
TEACHING_CACHE="$TEACHING_REPO/.devspace/m2"
mkdir -p "$TEACHING_REPO/.devspace"
```

`TEACHING_RUNTIME` 必须是 `.devspace/` 下尚不存在的直接子目录。三角色示例工具另要求名称以 `role-flow-` 开头。初始化失败或已经运行过的目录不重复初始化，保留现场并另选新目录。

## 1. 构建前端与后端

```sh
cd "$TEACHING_REPO/web"
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run lint:changed
npm run build

cd "$TEACHING_REPO/api"
JAVA_HOME="$TEACHING_JAVA" "$TEACHING_MAVEN" -B -s dev/maven-settings.xml \
  -Dmaven.repo.local="$TEACHING_CACHE" clean package
cd "$TEACHING_REPO"
```

前端产物为 `web/dist/`，后端产物为 `api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar`。首次 Maven 构建需要网络，镜像与缓存参数只作用于本次命令。

前端锁文件固定依赖，项目 `.npmrc` 保留旧依赖所需的 `legacy-peer-deps`，生产构建关闭旧 Terser 的 MD4 磁盘缓存。Java 父 POM 跳过测试，`BUILD SUCCESS` 只表示编译打包成功。`lint:changed` 只检查列出的早期课程与启动文件；检查其他修改时，在 `web/` 显式执行 `./node_modules/.bin/eslint --no-ignore <修改文件>`，默认 lint 成功不能代表全量源码通过。

## 2. 创建全新教学示例环境

以下四个端口必须空闲且互不相同。初始化会启动独立 MySQL 与 Redis，创建空表和五个合成账号：

```sh
cd "$TEACHING_REPO"
python3 api/dev/prepare-local.py --runtime "$TEACHING_RUNTIME" --tools "$TEACHING_TOOLS" \
  --mysql-port 13316 --redis-port 16389 --backend-port 18101 --frontend-port 18102
```

标准账号夹具主要用于 API 回归。完整页面体验还需要后台菜单、三角色课程和有效视频/编辑器模板，因此在**启动后端与前端之前**执行：

```sh
python3 api/dev/seed-role-flows.py create --runtime "$TEACHING_RUNTIME"
python3 api/dev/seed-role-flows.py verify --runtime "$TEACHING_RUNTIME"
```

该步骤仅接受全新、未启动应用、符合标准种子的 `role-flow-*` 环境。不能在已经操作过的环境上补跑 `create` 或重复覆盖数据。示例工具的完整约束见 [三角色教学夹具说明](https://github.com/ZZZZihan/TeachingOpen/blob/integration/product-candidate/docs/optimization/role-flow-fixture-pr.md)。

配置、数据库、Redis、附件与日志都保存在 `TEACHING_RUNTIME` 中。随机口令位于 `config/credentials.json`；该文件保持私有，不复制到仓库、截图或问题报告。

## 3. 启动与访问

启动后端：

```sh
python3 api/dev/run-backend.py start --runtime "$TEACHING_RUNTIME" --java-home "$TEACHING_JAVA"
```

返回 PID 后等待应用启动完成，再检查健康接口；返回内容应包含 `UP`：

```sh
curl --fail http://127.0.0.1:18101/api/actuator/health
```

健康确认后启动前端服务器。这条命令会占用当前终端，保持它运行：

```sh
python3 api/dev/serve-frontend.py --runtime "$TEACHING_RUNTIME" --dist "$TEACHING_REPO/web/dist"
```

在本机浏览器打开 `http://127.0.0.1:18102/index`。服务器使用 `ports.json` 中的端口，将 HTTP API 与 WebSocket 请求代理到这个环境的后端。

五个示例账号为 `fixture_admin`、`fixture_teacher_a`、`fixture_teacher_b`、`fixture_student_a`、`fixture_student_b`，登录密码使用本机 `credentials.json` 中的 `test_user_password`。通过正常登录页面与图形验证码进入；没有公开统一默认密码。

学生可进入示例课程并打开三种编辑器，教师可查看负责班级的任务和作品，管理员可进入维护页面。A/B 账号用于检查班级数据范围。示例是合成数据，不需要真实学生资料。

如果只需要热更新前端，可在 `web/` 执行 `npm run serve -- --host 127.0.0.1 --port 8082`；其 `/api` 代理在 `web/vue.config.js` 中默认指向本机 8081，必须改为当前环境的后端端口。完整角色体验优先使用上面的 dist 服务器。

## 4. 停止与继续运行

先在前端服务器终端按 Ctrl+C，再在保留上述路径变量的终端执行：

```sh
python3 api/dev/run-backend.py stop --runtime "$TEACHING_RUNTIME" --java-home "$TEACHING_JAVA"
python3 api/dev/stop-local.py --runtime "$TEACHING_RUNTIME"
```

停止保留数据库、附件和私有配置。再次使用同一环境时启动已有服务，不重新初始化或重新生成教学示例：

```sh
python3 api/dev/start-local.py --runtime "$TEACHING_RUNTIME"
python3 api/dev/run-backend.py start --runtime "$TEACHING_RUNTIME" --java-home "$TEACHING_JAVA"
```

等待健康接口 `UP` 后，再启动同一个前端命令。Redis 的开发配置没有常规持久化，冷停会丢失会话与验证码；需要保留 Scratch 云变量时先按 [备份恢复说明](https://github.com/ZZZZihan/TeachingOpen/blob/integration/product-candidate/api/BUILDING.md) 执行显式快照，不把普通重启当成备份。

## 5. 常见问题与交付

- **看到旧版网页**：先核对代码分支、构建产物和访问地址。仓库没有提供本项目的公开演示域名，本机示例地址也需要服务已启动。
- **后台菜单为空或没有示例课程**：确认在新环境启动应用前执行了三角色教学示例 `create`/`verify`；标准五账号种子不包含完整页面菜单。
- **代理返回 502**：确认本环境后端健康、实际端口以及 JAR 归属，查看运行目录的私有日志。
- **端口冲突或目录已有内容**：保留旧环境，改用新目录和空闲端口；四个端口要保持互不相同。
- **无法初始化原生工具**：确认 macOS arm64 平台和上面的工具目录布局；其他系统使用单独适配的工具或候选容器方案。

版本冻结、Linux/arm64 本机容器、数据库附件恢复和候选回退都有专门工具与记录，入口见 [候选运行说明](https://github.com/ZZZZihan/TeachingOpen/blob/integration/product-candidate/deploy/CANDIDATE.md) 和 [后端运行说明](https://github.com/ZZZZihan/TeachingOpen/blob/integration/product-candidate/api/BUILDING.md)。实际服务器上线需要另外准备目标配置、域名/TLS、持久化存储和恢复方案；开发数据与口令不直接用于上线。
