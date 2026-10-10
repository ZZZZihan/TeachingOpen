# 公网 IP HTTPS 试行 PR：方案与验证记录

日期：2026-10-10。基线：`github/main` 的 `6da25b9`，独立分支 `feature/ip-https`。目标是让现有公网 IPv4 入口具备可选择启用、可分阶段验证、可回退的 HTTPS 流程。交付包括源码、测试、操作说明、PR，以及获准的目标主机准备和隔离验证；已准备独立证书工具和私有候选，尚未切换活动配置、申请真实证书、合并或启用公网 HTTPS。

## 改动与取舍

默认 `web/nginx/default.conf`、前后端业务源码和数据库不变。`deploy/ip_https.py` 基于现有 Nginx 业务规则生成三个阶段：HTTP + ACME、HTTP/HTTPS 并行试行、HTTPS 业务 + HTTP 临时页面跳转。API URI、WebSocket、Range 媒体和 Python 资源策略保留；最终阶段拒绝 HTTP API/写请求，避免重放明文凭据。无 HSTS 或永久入口跳转，便于试行回退。

仅支持同机原生 Nginx → IPv4 loopback Java。后端配置片段通过当前 Spring Boot 的属性让 Java 识别可信代理的 HTTPS，媒体 Cookie 因而可带 Secure；只信任 `127.0.0.1`，Nginx 覆盖客户端传入的转发头。不能套用于跨容器代理或未经核对的线上配置。

切换工具先备份，再原子替换、检查、reload；失败尝试恢复。回退核对配置摘要，拒绝覆盖其他改动。备份中间状态支持进程被杀后显式恢复；恢复失败会明确报告，不能把 reload 命令成功当成业务通过。

已有原生站点可传入审阅过的源配置及 SHA-256，生成器严格校验受支持的单站点形态，保留最新前端路径、HTML 缓存规则、缺失 JS/CSS 的 404、原安全头及本机 8088 业务入口。最终阶段公网 HTTP 跳转，本机 8088 仍提供业务。额外未知 include/listener/规则会拒绝生成。激活时传预期活动配置摘要，在锁内、Nginx 命令和备份之前拒绝其他发布造成的配置漂移。

证书使用 Let’s Encrypt 免费 IP 证书方案；主要持续成本是自动续期、实际证书检查、发现失败和维护。提供隔离的 Certbot 状态目录、每天两次续期及每小时实际服务证书检查的 systemd 示例。检查失败只进入 systemd/journal，没有配置主动消息通知。具体启用和回退步骤见 [操作说明](../../deploy/IP_HTTPS.md)。

## 本地已经执行的验证

- HTTPS 工具单元测试 **34 项通过**：保留原 23 项正常切换/回退、错误配置、reload 失败、恢复失败、证书依赖损坏、摘要漂移、符号链接、并发锁和真实 SIGKILL 后恢复；新增源摘要/形态约束、本机入口与缓存规则保留，以及激活摘要漂移拒绝。
- 固定官方镜像 `nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94` 的真实 Nginx/TLS 测试 **409 项通过**：仓库模板 91 项、已审阅原生形态 318 项。汇总由 `deploy/test_ip_https_runtime.py` 输出并在 GitHub CI 保存；所有客户端 TCP 目的地址为本机动态端口，`8.8.8.8` 只用于配置及证书身份。临时测试 CA 和私钥不上传。覆盖可信 TLS/IP SAN、证书失败分支、API 读写、真实 WebSocket 握手及消息回显、Range 206、CORP、ACME 精确响应和缺失 404、阶段切换和逐级回退。
- 实际 Spring Boot 2.1.3 配置绑定 → Tomcat 9.0.122 RemoteIpValve → 原始 MediaCookie 源码 **14 项通过**，另核对全部 7 个属性受实际依赖支持。包括可信 HTTPS 设置/清除 Secure Cookie、HTTP 及不可信来源无法伪造安全协议。未启动应用上下文或数据库。
- 前端相关 8 组测试 **101 项通过**：通知 socket、Scratch 云变量、Python URL、课程材料链接、阅读器及三个编辑器桥接。
- 既有备份、迁移清单、发布包、空表提取及 CI 守卫 **45 项通过**。`git diff --check` 通过。
- 另一子 Agent 对实现、测试、配置与操作说明进行了独立代码审查，没有发现阻止 PR 的 P1/P2 问题。独立审查不是用户人工验收。

新增原生场景覆盖原站点 → bootstrap → trial → https 及逆序精确回退；各阶段实测本机 8088、缓存/404/安全头、Range、API 请求体，另验证激活前摘要漂移拒绝。本轮 macOS Docker 共享挂载在原子替换后短暂读到新内容与旧长度的组合；容器与宿主配置摘要不一致证实为夹具传递层问题。测试 shim 增加有期限的 SHA-256 一致等待后完整 409 项通过，生产切换逻辑未因此变更。

集成测试开发中修正过生成目录必须全新、reload 后旧 worker 可暂时共存两项测试夹具问题；测试现等待旧 worker 退出再验收新阶段。首轮 GitHub CI 的工具任务在运行时就绪检查失败，独立审查在 Linux 容器复现为临时目录 0700 阻止非 root worker 读取。后续将顶层改为 0711、公开内容改为可读，同时保留证书目录 0700 和私钥 0600；新增原生 Linux 文件系统及实际 worker UID 的访问检查，完整重跑 91 项通过。前后端首轮 CI 已通过，最终以修复提交的完整 CI 为准。

复现入口：

```sh
python3 -m unittest discover -s deploy -p 'test_ip_https.py' -v
docker pull nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
python3 deploy/test_ip_https_runtime.py --output ci-results/ip-https-runtime.json
python3 deploy/test_ip_https_proxy.py --java-home "$JAVA_HOME" --m2 "$MAVEN_CACHE"
```

集成脚本不自动拉取镜像；调用方准备固定镜像。代理测试使用已安装 JDK 和项目 Maven 依赖，不安装软件。GitHub CI 已加入以上检查，并保留原全量前端构建、后端核心测试和合成 MySQL 注册流程；CI 实际结果以对应提交的 Actions 检查为准。

## 目标主机已完成的准备与隔离验证

2026-10-10 核对活动 Nginx 1.18.0、80 入口、本机 8088、Java 的 loopback 8080、最新前端目录及站点配置。源配置 SHA-256 为 `638956b0492059a92e5db906c52de4a87ed52eb2dbe3f285d9b63bae3a671585`，它与生成器支持的已审阅形态逐字节一致。三阶段候选从该源生成；实际切换前仍需核对摘要。

- 专用 Python 3.10 环境 `/opt/teachingopen-certbot` 已安装 Certbot/acme 5.8.0、pip 26.2。19 个 wheel 使用官方 PyPI 元数据验证 SHA-256，依赖检查及 IP/webroot 参数检查通过；已核实包都安装在该虚拟环境。只读取 staging/正式 ACME directory，未注册账户或申请证书。
- 目标 Nginx **45 项隔离检查通过**：三阶段配置语法、当前首页内容、HTML `no-cache`、缺失 JS/CSS 的 404、ACME 精确内容、可信测试证书/IP/剩余有效期、临近过期失败检测、最终 HTTP 页面 307 与 API 426、目标 systemd 单元校验。运行时使用独立 Nginx 进程与随机 loopback 端口；测试证书仅由本轮客户端显式信任，未安装系统 CA。进程退出后测试端口关闭。
- 验证前后活动站点及首页摘要、Nginx/Java 主进程 PID 均相同。没有 reload 现有 Nginx、重启后端、开放云安全组 443、启用 timer 或修改应用数据。首次隔离 ACME 探测因测试目录受 umask 限制不可读而失败；修正公开测试目录权限后完整 45 项通过，证书目录继续私有。
- 在服务器私有目录准备了完整后端配置备份和加入 7 个可信代理属性的候选；没有替换活动文件，凭据未复制到本地或 Git。HTTPS 真实登录 Cookie 仍待后端配置应用与试行后检查。
- 当前发布清单 **4909 个文件**全部匹配；为旧标签页保留的 **566 个文件、27,324,333 字节**与新清单不重合，已另存清单和恢复包，未删除。旧标签页可能延迟加载旧分块；清理会让这些标签页需要刷新，不是 HTTPS 启用前提。静态缺失 404 与 HTML 缓存规则仍应保留。

这些结果只证明准备和目标版本隔离行为。线上继续提供 HTTP；云安全组仍未开放 443，主机防火墙已允许 443。

## 仍需实际试行验证

- 应用候选前再次核对活动配置和稳定公网 IP；云安全组 443 放行后从外网验证可达。
- 真实 CA staging/正式签发、正式状态上的续期演练、服务加载新证书、timer 启用和失败发现责任。`systemd-analyze verify` 不是执行了续期，ACME directory 可达也不是签发成功。
- 真实浏览器、注册登录及各角色路径、视频附件、编辑器保存和 WSS；历史内容中的绝对 HTTP 资源需要实际数据审计。
- HTTP→HTTPS 会改变浏览器 origin；用户应保存未提交内容并重新登录。真实业务验证完成后才更新注册二维码和入口。

这些事项未被本地合成测试覆盖。未授权的生产操作不作为本 PR 完成条件，也不宣称已完成线上验收。
