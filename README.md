# TeachingOpen · 天工人工智能课程科普系统

基于 Teaching 在线教学平台 v2.8 的教学应用，面向人工智能与编程课程，提供课程学习、在线创作、班级作业、教师批改和教学管理。界面采用天津工业大学校园视觉与天工紫主题。

本仓库保存上游源码历史、产品改进及对应的检查记录。当前交付为可供小范围试用的本地集成候选；用户视觉认可、真实师生试用和目标环境部署仍需分别完成。

## 当前版本与交付范围

README 更新于 **2026-10-09**。本分支 `integration/product-candidate` 的产品代码基于 `4f30e51b7121b7f102cfe1c71bba3183cd21b7e2`，包含截至 PR #76 的 75 个实现 PR 精确提交。此次 README 更新只改文档。

- **集成源码**：本分支包含前后端、开发工具和各项修复，适合查看完整候选。
- **目标与验收记录**：[管理 PR #1](https://github.com/ZZZZihan/TeachingOpen/pull/1) 保存计划、PR 追溯和验收摘要；其中的证据文件位于 `feature/productization-goal` 分支。
- **后续功能**：[免手机号账号注册 PR #78](https://github.com/ZZZZihan/TeachingOpen/pull/78) 单独交付，尚未纳入本候选。
- **GitHub 与生产**：实现 PR 和本地集成分别保留；推送分支不代表合入 `main` 或完成生产部署。

最新完整角色链路记录来自 **2026-10-05**。本次更新核对已有源码与冻结记录，没有重新执行全部业务验收，也不据此声称本机预览服务仍在运行。

## 核心能力

| 使用者 | 主要流程 |
| --- | --- |
| 学生 | 浏览和筛选课程、读取单元正文与视频/PDF、使用 Python/Scratch/ScratchJr 创作、提交文件作业、阅读教师评分与评语 |
| 教师 | 查看班级任务与学生作品、筛选学生和作品、预览与下载、批改并在失败后保留输入重试 |
| 管理员 | 维护课程和单元、管理用户与班级成员、调整角色与账号状态、在手机端访问成员表格操作列 |
| 开发与运维 | 创建独立合成环境、核对权限及附件边界、备份恢复、冻结候选、切换回退、执行本机容器验证 |

课程、班级、作品、附件和媒体读取使用相应的身份与资源范围检查；会话失效、请求失败和迟到响应有对应的恢复处理。完整行为及检查范围见各项 PR 记录，这些检查不代表穷尽所有权限组合。

## 技术栈与目录

| 层 | 当前源码配置 |
| --- | --- |
| 前端 | Vue 2.7、Vue CLI 3、Ant Design Vue、Vue Router、Vuex |
| 后端 | Java 8、Spring Boot 2.1.3.RELEASE、MyBatis-Plus 3.1.2 |
| 认证与容器 | Apache Shiro 1.13.0、JWT、内嵌 Tomcat 9.0.122 |
| 数据与资源 | MySQL、Redis、本地附件；保留上游云存储等集成入口，按环境单独配置 |
| 已有构建工具记录 | Node 26.7.0、npm 11.19.0、JDK 8、Maven 3.9.16 |

版本以 `web/package-lock.json`、`web/.nvmrc`、`api/pom.xml` 和 [本机工具清单](api/dev/toolchain.json) 为准。保留旧框架是当前兼容性选择，维护债务及正式发布条件仍有待处理。

```text
api/                         Java 后端与 Maven 多模块工程
  dev/                       隔离环境、合成夹具、权限及恢复检查工具
  db/                        上游 SQL 与升级材料
web/                         Vue 前端
  src/                       页面、组件、状态与接口调用
  public/                    Scratch、ScratchJr、Python 等创作资源
  tests/                     前端行为与回归检查
deploy/                      Nginx、候选冻结与容器验证工具
docs/optimization/           各项改进、审阅与脱敏证据
```

## 本地开发

### 获取集成分支

仓库为私有仓库，使用有访问权限的 GitHub 账号获取：

```sh
git clone --branch integration/product-candidate https://github.com/ZZZZihan/TeachingOpen.git
cd TeachingOpen
```

已有工作区应先核对当前分支及未提交改动，再选择集成分支或独立工作树；不要覆盖已有开发数据。

### 前端安装、检查与构建

按 `web/.nvmrc` 和 `packageManager` 使用已有记录的 Node/npm 版本，在 `web/` 执行：

```sh
cd web
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run lint:changed
npm run build
```

构建产物位于 `web/dist/`。锁文件固定依赖，项目 `.npmrc` 保留旧工程需要的 `legacy-peer-deps` 设置；构建已关闭旧 Terser 的 MD4 磁盘缓存。

`lint:changed` 只检查脚本中列出的早期课程与启动文件。默认 ESLint 配置忽略整个 `src/`，因此默认 `lint` 成功不代表全量源码通过；检查新改动时应显式执行 `eslint --no-ignore <修改文件>`。部分旧组件仍有已记录的 lint 问题，构建也保留 CSS 顺序和包体警告。

前端开发服务可执行 `npm run serve -- --host 127.0.0.1 --port 8082`。开发配置中的 `/api` 默认代理到本机 `8081`；联调自定义后端端口时需相应调整。端口和后端就绪情况应由实际运行状态确认。详细说明见 [web/BUILDING.md](web/BUILDING.md)，其中 32 项测试等数字属于早期记录。

### 后端与隔离环境

按 [api/BUILDING.md](api/BUILDING.md) 准备 JDK 8、Maven、MySQL、Redis 的本机工具路径，并设置其中的 `TEACHING_JAVA`、`TEACHING_MAVEN` 和 `TEACHING_CACHE`。在仓库根目录执行：

```sh
cd api
JAVA_HOME="$TEACHING_JAVA" "$TEACHING_MAVEN" -B -s dev/maven-settings.xml \
  -Dmaven.repo.local="$TEACHING_CACHE" clean package
```

父 POM 跳过 Java 测试；`BUILD SUCCESS` 表示编译打包成功，Java 检查需按对应 PR 说明另行执行。

隔离环境工具从上游 SQL 提取空表定义并创建合成账号和教学数据，数据库、Redis、附件、日志和随机凭据保存在独立运行目录。入口包括 `prepare-local.py`、`run-backend.py`、`serve-frontend.py`、`start-local.py` 和 `stop-local.py`，参数、端口及停止/重启步骤见后端构建说明。

`api/BUILDING.md` 的部分业务状态是早期 PR 的历史描述；本候选的后续权限、WebSocket、Scratch 云变量恢复及角色链路进展应结合下面的专项记录阅读。合成环境和真实课程私有副本分别使用，业务写入与故障测试在合成环境完成。

### 冻结、验证与恢复

- [冻结候选与 Linux/arm64 本机容器验证](deploy/CANDIDATE.md)：显式绑定源码、JAR 和完整 dist 的摘要，创建私有包后核对不可变文件。`create`/`verify` 属于离线步骤；实际启动与 HTTP 探针另行执行。
- [数据库、附件及恢复演练](docs/optimization/local-backup-restore-pr.md)：记录已有合成环境的备份、全新恢复和数据核对范围。
- [候选切换与回退](docs/optimization/local-candidate-switch-pr.md)：记录正常切换、失败恢复及中断后的处理，不自动回退数据库内容。

运行目录、生产数据库、真实用户资料、上传文件、凭据和构建私有配置留在仓库之外。正式目标环境的架构、TLS、可信代理、外部集成与生产定制对应关系需在发布前分别核对。

## 已有检查与证据

下面是对应版本的历史结果，保留原始范围与绑定；此次文档更新没有重跑这些检查。

| 证据 | 已有结果与范围 |
| --- | --- |
| 最终角色链路前端 | 实际构建源 `1b23551257b3f922f7fc4b125dfd9a85e5090a0c`；688/688 前端检查通过，构建成功，12 条已有 warning 保留。随后集成文档的 `4f30e51` 与它的 web tree 相同 |
| 普通认证页面操作 | 五个合成角色普通登录；Python、Scratch、ScratchJr 与文件作业四条代表链完成学生提交、教师批改、学生回读；编辑器另外核对保存、重开与同一作品 ID |
| 响应式与恢复 | 主要页面覆盖 390/768/1440 宽度；最终完整后台成员表格可用键盘滚到操作列。提交、批改、上传与过期会话的选定失败恢复有浏览器及数据记录 |
| 后端构建 | 空 Maven 缓存构建成功，包内容与冻结运行包对应；父 POM 跳过 Java 测试 |
| 最终包离线核对 | 4,906 个不可变文件核对通过，其中 4,895 个前端文件与实际构建一致；最终包未重跑容器运行探针 |
| 先前容器运行 | 旧冻结组合在本机 Linux/arm64 容器完成 45/45 运行检查；该结果保留旧版本绑定，不作为最终包再次运行的证明 |
| 真实课程私有副本 | 2026-10-03 快照中的 5 门课程、83 个单元、297 项资源用于读取与代表媒体检查；不代表生产最新状态或真实师生写入验收 |

完整证据见：

- [最终角色链路、原十项条件与保留边界](https://github.com/ZZZZihan/TeachingOpen/blob/205e1ca10d68b7341c9f23fec9ece379365f5f9a/docs/optimization/authenticated-role-flow-2026-10-05.md)
- [精确候选摘要、PR 关联及选定合成截图](https://github.com/ZZZZihan/TeachingOpen/tree/205e1ca10d68b7341c9f23fec9ece379365f5f9a/docs/optimization/evidence/authenticated-role-flow-20261005)
- [完整产品化目标与 PR 追溯](https://github.com/ZZZZihan/TeachingOpen/blob/205e1ca10d68b7341c9f23fec9ece379365f5f9a/docs/optimization/productization-goal-2026-10-02.md)
- [各项改进与专项记录](docs/optimization/)

工程自检、独立 Agent 审阅、实际浏览器操作和用户人工验收分别记录。复杂创作项目、未覆盖的外部集成、生产容量、用户审美认可和真实课堂效果不由上述代表链结果证明。

## 上游来源与许可

上游源码来自 [chengyu2333/teaching-open](https://gitee.com/chengyu2333/teaching-open)，本地改进基线为 `513b05fcddc5da63e0e58c3752cc34ee73252dde`。上游项目包含 CRM、教务、题库、赛事、社区等更多模块，本候选的声明与检查聚焦上文的教学主流程。使用与分发遵循 [LICENSE](LICENSE) 及各组件的许可文件。

[原始上游 README](https://github.com/ZZZZihan/TeachingOpen/blob/513b05fcddc5da63e0e58c3752cc34ee73252dde/README.md) 保留在 Git 历史中，包含原演示入口与部署教程。示例账号和默认口令属于上游演示说明，本地隔离环境使用随机凭据；部署及工具选择以本仓库当前构建、候选验证说明和实际目标环境为准。
