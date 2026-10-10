# GitHub CI

工作流位于 `.github/workflows/ci.yml`，在 PR 创建/更新及 `main`、`codex/registration-acceptance` 的提交时运行。所有任务使用 GitHub 托管的 Ubuntu 临时机器；没有 cron、本机 runner、云端 SSH、部署或备份下载。

## 合并检查

- **Frontend tests and build**：沿用 `web/.nvmrc` 与锁文件，禁用依赖安装脚本，运行前端测试和生产构建。获取完整 Git 历史，以运行已有的旧版本回归对照测试。
- **Backup and migration tools**：执行备份、升级清单、发布包、空表提取以及 CI 守卫的合成测试，不实际运行备份或拉取服务器数据。另运行公网 IP HTTPS 工具单元测试与固定镜像的隔离 Nginx/TLS 验证：临时测试 CA、回环端口、合成 API/WebSocket/媒体、实际配置切换与回退，不请求公网证书、不连接生产。只保存不含私钥的汇总 JSON。
- **Backend and MySQL registration**：Java 8 干净构建并显式开启四组核心 Java 单元测试。额外核对 Surefire 报告，缺少或跳过任何核心测试都会失败。原 `SampleTest` 依赖固定旧业务样例，`SecurityToolsTest` 仅打印加解密结果，因此不列入核心检查。
- **CI required**：汇总前三项，只有全部成功才通过；失败、取消或跳过均不能通过。作为分支必需状态检查使用，避免单项路径过滤导致检查缺失。

后端构建后还用当前依赖执行 `deploy/test_ip_https_proxy.py`：实际 Spring Boot 配置绑定、Tomcat RemoteIpValve 与原 MediaCookie 源码，核对仅信任 127.0.0.1 的协议转发及 Secure Cookie。该测试无需数据库或监听 socket，不能代替线上登录验收。

每个 PR 的新提交取消同一 PR 的旧运行。没有定时触发。Node/npm 版本遵循现有项目；Actions 使用完整提交 SHA 固定，任务只有仓库读取权限，不使用生产凭据。

## 注册数据库验证

后端任务启动临时 MySQL 8.0 和 Redis 7.2 服务容器，使用固定测试端口 33306/36379。`registration_mysql.py` 只接受 GitHub 托管运行环境和当前工作区；在本地或自托管 runner 上直接拒绝。

脚本新建 `teachingopen_check_ci`，已存在即失败，不覆盖任何已有数据库。从版本库 SQL 提取 69 张空表，不导入原始 INSERT，只添加合成 student 角色及关闭状态的注册开关。真实注册迁移按顺序执行两次，检查重复执行兼容性，然后启动本次构建 JAR，使用完整外部配置替换内置环境配置。应用数据库账号只拥有测试库的读写权限，测试探针通过独立账号注入隔离库触发器故障。

复用 `deploy/verify_registration.py` 的 32 项 HTTP/SQL 检查：姓名/学校与补充汉字、手机号与口令保存、学生/教师身份、禁止提权、重复与并发注册、验证码登录、管理接口拒绝、资料写入失败时事务回滚、失败后重试及公开目录脱敏。结果记录 MySQL 版本、表数和实际 CI 提交。

GitHub 仅保留不含真实用户数据的 JSON 测试结果 7 天。运行配置、凭据、数据库和应用日志不作为 artifact 上传，临时容器由 GitHub 在任务结束后回收。CI 不能代替线上运行检查、备份恢复演练或人工验收。

## 维护

新增核心 Java 测试时，同步更新工作流的 `-Dtest` 与 `check_java_results.py` 中的必需测试集。注册验证数量变化时，审查新增/删除的行为，再更新完整执行数量。不要通过跳过失败项或 `continue-on-error` 获得绿色状态。

首次工作流须在真实 GitHub PR 上通过，review 后再合并并启用 `CI required` 分支规则。当前交付目标是 `codex/registration-acceptance`；工作流到达其他集成分支后，才为对应分支启用该必需检查，避免给尚无工作流的分支制造无法满足的合并条件。
