# 公网 IP HTTPS 试行 PR：方案与验证记录

日期：2026-10-10。基线：`github/main` 的 `6da25b9`，独立分支 `feature/ip-https`。目标是让现有公网 IPv4 入口具备可选择启用、可分阶段验证、可回退的 HTTPS 流程。交付范围为源码、测试、操作说明和 PR；没有操作生产配置、申请真实证书、合并或部署。

## 改动与取舍

默认 `web/nginx/default.conf`、前后端业务源码和数据库不变。`deploy/ip_https.py` 基于现有 Nginx 业务规则生成三个阶段：HTTP + ACME、HTTP/HTTPS 并行试行、HTTPS 业务 + HTTP 临时页面跳转。API URI、WebSocket、Range 媒体和 Python 资源策略保留；最终阶段拒绝 HTTP API/写请求，避免重放明文凭据。无 HSTS 或永久入口跳转，便于试行回退。

仅支持同机原生 Nginx → IPv4 loopback Java。后端配置片段通过当前 Spring Boot 的属性让 Java 识别可信代理的 HTTPS，媒体 Cookie 因而可带 Secure；只信任 `127.0.0.1`，Nginx 覆盖客户端传入的转发头。不能套用于跨容器代理或未经核对的线上配置。

切换工具先备份，再原子替换、检查、reload；失败尝试恢复。回退核对配置摘要，拒绝覆盖其他改动。备份中间状态支持进程被杀后显式恢复；恢复失败会明确报告，不能把 reload 命令成功当成业务通过。

证书使用 Let’s Encrypt 免费 IP 证书方案；主要持续成本是自动续期、实际证书检查、发现失败和维护。提供隔离的 Certbot 状态目录、每天两次续期及每小时实际服务证书检查的 systemd 示例。检查失败只进入 systemd/journal，没有配置主动消息通知。具体启用和回退步骤见 [操作说明](../../deploy/IP_HTTPS.md)。

## 本地已经执行的验证

- HTTPS 工具单元测试 **23 项通过**：正常切换/回退、错误配置、reload 失败、恢复失败、证书依赖损坏、摘要漂移、符号链接、并发锁和真实 SIGKILL 后恢复。
- 固定官方镜像 `nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94` 的真实 Nginx/TLS 测试 **91 项通过**。汇总由 `deploy/test_ip_https_runtime.py` 输出并在 GitHub CI 保存；所有客户端 TCP 目的地址为本机动态端口，`8.8.8.8` 只用于配置及证书身份。临时测试 CA 和私钥不上传。覆盖可信 TLS/IP SAN、证书失败分支、API 读写、真实 WebSocket 握手及消息回显、Range 206、CORP、ACME 精确响应和缺失 404、阶段切换和逐级回退。
- 实际 Spring Boot 2.1.3 配置绑定 → Tomcat 9.0.122 RemoteIpValve → 原始 MediaCookie 源码 **14 项通过**，另核对全部 7 个属性受实际依赖支持。包括可信 HTTPS 设置/清除 Secure Cookie、HTTP 及不可信来源无法伪造安全协议。未启动应用上下文或数据库。
- 前端相关 8 组测试 **101 项通过**：通知 socket、Scratch 云变量、Python URL、课程材料链接、阅读器及三个编辑器桥接。
- 既有备份、迁移清单、发布包、空表提取及 CI 守卫 **45 项通过**。`git diff --check` 通过。
- 另一子 Agent 对实现、测试、配置与操作说明进行了独立代码审查，没有发现阻止 PR 的 P1/P2 问题。独立审查不是用户人工验收。

集成测试开发中修正过生成目录必须全新、reload 后旧 worker 可暂时共存两项测试夹具问题；测试现等待旧 worker 退出再验收新阶段。首轮 GitHub CI 的工具任务在运行时就绪检查失败，独立审查在 Linux 容器复现为临时目录 0700 阻止非 root worker 读取。后续将顶层改为 0711、公开内容改为可读，同时保留证书目录 0700 和私钥 0600；新增原生 Linux 文件系统及实际 worker UID 的访问检查，完整重跑 91 项通过。前后端首轮 CI 已通过，最终以修复提交的完整 CI 为准。

复现入口：

```sh
python3 -m unittest discover -s deploy -p 'test_ip_https.py' -v
docker pull nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
python3 deploy/test_ip_https_runtime.py --output ci-results/ip-https-runtime.json
python3 deploy/test_ip_https_proxy.py --java-home "$JAVA_HOME" --m2 "$MAVEN_CACHE"
```

集成脚本不自动拉取镜像；调用方准备固定镜像。代理测试使用已安装 JDK 和项目 Maven 依赖，不安装软件。GitHub CI 已加入以上检查，并保留原全量前端构建、后端核心测试和合成 MySQL 注册流程；CI 实际结果以对应提交的 Actions 检查为准。

## 仍需目标环境验证

- 实际活动 Nginx 文件、定制规则、前端目录、API 端口、后端监听地址，以及公网 80/443 和稳定 IP。
- 本地运行镜像为 Nginx 1.30.5；已知公网响应头为 1.18.0，尚未在该目标版本/主机运行配置检查。
- 真实 CA staging/正式签发、Certbot 5.4+ 续期演练、systemd 单元的目标主机验证和失败发现责任。
- 真实浏览器、注册登录及各角色路径、视频附件、编辑器保存和 WSS；历史内容中的绝对 HTTP 资源需要实际数据审计。
- HTTP→HTTPS 会改变浏览器 origin；用户应保存未提交内容并重新登录。真实业务验证完成后才更新注册二维码和入口。

这些事项未被本地合成测试覆盖。未授权的生产操作不作为本 PR 完成条件，也不宣称已完成线上验收。
