# 公网 IPv4 HTTPS 试行、续期与回退

适用于同一台 Linux 服务器上的 Nginx → `127.0.0.1:<API端口>` 原生部署。保留公网 IP，不购买域名。默认 HTTP 模板、Java/前端产物、数据库和业务数据保持原样；本目录的工具只有被明确执行时才生成或切换配置。Docker 跨容器代理、IPv6、其他反向代理拓扑需要另外验证。

本 PR 的本地自签测试 CA 仅用于隔离验证；正式入口必须使用浏览器信任的证书。PR、CI 通过不等于已经签发证书、开放云端 443、部署、完成真实角色流程或人工验收。现有网站能经 IP 访问也不说明已满足备案要求。

## 方案与验收行为

- `bootstrap.conf`：原 HTTP 业务与独立 ACME challenge；尚无证书时可运行。
- `trial.conf`：保留 HTTP，新增 HTTPS。先直接测试 HTTPS，不先切换所有用户。
- `https.conf`：HTTPS 提供业务；HTTP 保留 challenge，普通 GET/HEAD 临时跳转至固定 HTTPS IP。HTTP API 和写请求返回 426，不把带凭据的明文请求自动转发给后端。
- 不设置 HSTS 或永久重定向，避免试行产生长期浏览器状态；IP 地址本身也不适用域名 HSTS 策略。登录会话在 HTTP/HTTPS 间不能视为连续安全会话，切换后应重新登录。
- 切换先备份、校验 Nginx 配置再 reload；失败恢复上一份配置。人工回退核对当前配置摘要，拒绝覆盖别人之后的修改。
- 续期只作用于本服务独立的 ACME 状态。续期或检查失败报错，保留当前 HTTPS，不自动降级为 HTTP。

## 上线前取得实际参数

核实云端正在运行的配置，而不是直接套用旧报告：Nginx 版本/活动站点文件、前端真实目录、API 的 loopback 端口、配置额外规则、公网 IP 是否稳定、云安全组及主机防火墙的 80/443、现有应用启动方式。默认 `render` 沿用仓库 `web/nginx/default.conf`；已有原生站点应传入已审阅的 `--source-config` 和 `--source-sha256`。当前受支持形态保留现场的 HTML `no-cache`、缺失 JS/CSS 的 404、现有前端目录及 `127.0.0.1:8088` 本机业务入口。它严格匹配已审阅的单站点形态，额外 include、listener 或未知业务规则会拒绝生成，需要先审阅并扩展支持；不是通用 Nginx 解析器。

工具要求 `--target` 为已存在的普通文件；若 `sites-enabled` 是符号链接，请核实并使用其实际 `sites-available` 目标路径。不要替换整个 `/etc/nginx/nginx.conf`，不要把三个候选同时 include，避免重复监听和 map 冲突。确认其他站点无冲突后再试行。

证书及 ACME 状态不进入仓库、webroot、PR 附件和普通日志。ACME webroot 只放临时挑战文件。下列命令是获准在目标上试行后的操作说明，本 PR 不自动执行它们。

## 1. 准备 HTTP 验证路径与后端可信代理

先填写已核实的参数；`SITE` 是真实活动配置文件，`WEB_ROOT` 是现有前端目录，`API_PORT` 是现有 loopback API 端口。所有工具路径使用绝对路径。示例以 Ubuntu 的 `/usr/sbin/nginx` 为准。

```sh
PUBLIC_IP=101.201.225.116
SITE=/实际的站点配置文件
WEB_ROOT=/实际的前端目录
API_PORT=实际的端口
SOURCE=/实际的本PR工作区
WORK=/var/lib/teachingopen-https-trial
```

准备新工作目录与挑战目录，后者需允许 Nginx 读取：

```sh
sudo install -d -m 0700 "$WORK" /var/lib/teachingopen-acme
sudo install -d -m 0755 /var/www/teachingopen-acme/.well-known/acme-challenge
sudo install -m 0600 "$SITE" "$WORK/reviewed-site.conf"
SOURCE_SHA=$(sudo sha256sum "$WORK/reviewed-site.conf" | cut -d ' ' -f 1)
sudo python3 "$SOURCE/deploy/ip_https.py" render \
  --source-config "$WORK/reviewed-site.conf" --source-sha256 "$SOURCE_SHA" \
  --ip "$PUBLIC_IP" --web-root "$WEB_ROOT" \
  --api-upstream "http://127.0.0.1:$API_PORT" \
  --acme-root /var/www/teachingopen-acme \
  --certificate /var/lib/teachingopen-acme/config/live/teachingopen-ip/fullchain.pem \
  --private-key /var/lib/teachingopen-acme/config/live/teachingopen-ip/privkey.pem \
  --output "$WORK/rendered"
sudo diff -u "$SITE" "$WORK/rendered/bootstrap.conf"
```

渲染目录须全新。`diff` 的非零退出只表示有差异，需要审阅路径、安全头、上传、媒体、WebSocket与自定义业务规则。当前生成器是一个明确拓扑的候选，不是任意 Nginx 配置迁移器。

源配置摘要绑定审阅过的原始字节；下面每次 `activate` 还传入预期的活动配置摘要。工具在加锁后、执行 Nginx 命令和创建备份前拒绝摘要不匹配。若其他发布改变了活动配置，重新核对、生成与验证候选，不要临时读取新摘要来绕过这个保护。仅使用同一工具的操作共享该锁；仍需避免与其他发布同时切换配置。

```sh
sudo python3 "$SOURCE/deploy/ip_https.py" activate \
  --target "$SITE" --candidate "$WORK/rendered/bootstrap.conf" \
  --expected-target-sha256 "$SOURCE_SHA" \
  --backup "$WORK/before-bootstrap" --nginx /usr/sbin/nginx
```

用随机无敏感内容的 challenge 文件，从外部网络确认 `http://IP/.well-known/acme-challenge/<token>` 返回精确内容；不存在的 token 必须 404。不能以 SPA 首页的 200 代替 challenge 成功。完成后删除自己创建的探测 token。

**先激活 bootstrap 并确认 HTTP 正常，再启用后端的转发头信任。** 原 HTTP 配置未覆盖所有转发头；顺序颠倒会出现旧 Nginx 透传客户端头、而 Java 已信任该头的窗口。

把 `ip-https-proxy.properties.example` 中的配置合并进**现有完整私有应用配置**，先备份这份配置；不要用片段替换整个配置，也不要输出其中凭据。它只信任 loopback 代理，Nginx 会覆盖转发头。按实际服务方式受控重启后端，先核对 HTTP 正常及后端仅监听 loopback；HTTPS 登录 Cookie 检查放在后续 trial 证书与监听就绪后。这一步使 TLS 在 Nginx 终止后 Java 仍能识别安全连接，适用于现有 Nginx 1.18，无需为 `proxy_cookie_flags` 升级 Nginx。

若完整后端候选提前准备，应用前比较活动配置与准备时备份的 SHA-256；不一致时基于新的完整配置重新合并 7 个属性，不能用旧候选覆盖后来修改的数据库连接或业务参数。

## 2. 申请证书并试行 HTTPS

准备受维护的 Certbot **5.4 或更新版本**，本方案使用独立路径 `/opt/teachingopen-certbot/bin/certbot`；不复用不明版本的系统旧包。先运行 `--version` 核对。2026-10-10 的目标主机准备已在独立 Python 3.10 虚拟环境安装 Certbot/acme 5.8.0，19 个 wheel 与官方 PyPI SHA-256 一致，`pip check` 通过。安装准备不等于签发；仓库工具不会自动安装软件。

先使用测试 CA 验证流程，状态目录与正式目录分开。`ACME_EMAIL` 由操作者填写，日志留在服务器私有目录：

```sh
sudo /opt/teachingopen-certbot/bin/certbot certonly --staging \
  --non-interactive --agree-tos --email "$ACME_EMAIL" \
  --preferred-profile shortlived --cert-name teachingopen-ip \
  --webroot --webroot-path /var/www/teachingopen-acme --ip-address "$PUBLIC_IP" \
  --config-dir /var/lib/teachingopen-acme/staging/config \
  --work-dir /var/lib/teachingopen-acme/staging/work \
  --logs-dir /var/lib/teachingopen-acme/staging/logs
```

测试 CA 不受浏览器信任，不能给真实师生使用。测试签发通过后，明确接受 CA 协议并执行正式签发：

```sh
sudo /opt/teachingopen-certbot/bin/certbot certonly \
  --non-interactive --agree-tos --email "$ACME_EMAIL" \
  --preferred-profile shortlived --cert-name teachingopen-ip \
  --webroot --webroot-path /var/www/teachingopen-acme --ip-address "$PUBLIC_IP" \
  --config-dir /var/lib/teachingopen-acme/config \
  --work-dir /var/lib/teachingopen-acme/work \
  --logs-dir /var/lib/teachingopen-acme/logs
sudo python3 "$SOURCE/deploy/ip_https.py" activate \
  --target "$SITE" --candidate "$WORK/rendered/trial.conf" \
  --expected-target-sha256 "$(sudo python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["files"]["bootstrap.conf"]["sha256"])' "$WORK/rendered/manifest.json")" \
  --backup "$WORK/before-trial" --nginx /usr/sbin/nginx
python3 "$SOURCE/deploy/check_ip_certificate.py" --ip "$PUBLIC_IP"
```

使用真实浏览器直接打开 HTTPS，不忽略证书错误。至少检查注册/登录、管理员与师生入口、视频起播/拖动、附件、三编辑器加载/保存、通知/云变量 WSS、退出。保持生产数据写入范围与已有授权一致，必要时在独立验证副本执行写入。核对 HTTPS 登录及退出时 `teaching_media` Cookie 的 `Secure`、`HttpOnly`、`SameSite=Strict`，而不仅是首页状态码。

现有主 API、编辑器与 socket 已有同源逻辑，历史课程内容仍可能含绝对 `http://` 链接。审计实际数据并在浏览器验证；HTTP 重定向不能替代 mixed-content 检查，不在本 PR 批量改写数据库。前端 origin 从 HTTP 变成 HTTPS 后，本地登录存储/草稿是不同 origin，应先保存未提交内容并重新登录。

## 3. 自动续期与实际服务证书检查

Let’s Encrypt IP 证书有效期为 160 小时。`teachingopen-ip-cert-renew.timer` 每天两次启动专用续期程序，由 Certbot 判断是否到续期时间。专用 config/work/logs 路径及 `--cert-name` 防止触碰其他服务证书。定时器已有最多 30 分钟的随机调度，因此程序和下方演练命令使用 `--no-random-sleep-on-renew`，避免 Certbot 5.8 默认额外等待最多 8 分钟而触发 300 秒服务超时；已在目标安装版本核对参数解析。

Certbot 的 deploy-hook 失败不保证续期命令返回非零。`renew_ip_certificate.py` 因此还会比较专用 `live/teachingopen-ip/cert.pem` 与 Nginx 实际提供的叶证书，校验证书链、IP 身份及至少 48 小时有效期。磁盘证书与服务证书不一致时，执行一次 `nginx -t` 和 reload，再有界核验；后续续期无需换证时也会做这个检查和恢复，不为修复加载故障反复申请证书。Certbot 最终失败且没有已更新的可核验证书、加载失败或最后核验失败，均使服务失败。Certbot 尝试窗口上限 240 秒，整个程序预算 295 秒，systemd 最终上限为 300 秒；详细 ACME 日志留在专用私有目录。

Certbot 失败或超时后，在共享的 240 秒尝试窗口内最多执行三次，重试分别等待 5 秒和 10 秒，等待也计入窗口；时间不足时提前停止，为后续证书核验与加载恢复保留预算。找不到命令、公网 IP 或本地证书输入错误和 Nginx 错误不通过重新申请证书处理。对 Certbot 非零退出码无法仅凭返回值精确区分网络与其他失败，因此这里是有限重试，而不是已识别全部网络根因的自动修复。失败后若磁盘叶证书已经变化，则停止申请尝试，转入实际证书核验和必要的加载恢复；JSON 会保留命令失败及尝试次数，不能把状态恢复成功描述为所有命令都成功。未使用强制续期参数，短时失败不会停止正在使用有效证书的站点。

```sh
sudo install -d -m 0755 /opt/teachingopen-https
sudo install -m 0644 "$SOURCE/deploy/check_ip_certificate.py" /opt/teachingopen-https/
sudo install -m 0644 "$SOURCE/deploy/renew_ip_certificate.py" /opt/teachingopen-https/
sed "s/@PUBLIC_IP@/$PUBLIC_IP/g" "$SOURCE/deploy/teachingopen-ip-cert-renew.service" \
  | sudo tee /etc/systemd/system/teachingopen-ip-cert-renew.service >/dev/null
sudo install -m 0644 "$SOURCE/deploy/teachingopen-ip-cert-renew.timer" /etc/systemd/system/
sudo install -m 0644 "$SOURCE/deploy/teachingopen-ip-cert-check.timer" /etc/systemd/system/
sed "s/@PUBLIC_IP@/$PUBLIC_IP/g" "$SOURCE/deploy/teachingopen-ip-cert-check.service.template" \
  | sudo tee /etc/systemd/system/teachingopen-ip-cert-check.service >/dev/null
sudo systemd-analyze verify /etc/systemd/system/teachingopen-ip-cert-*.service /etc/systemd/system/teachingopen-ip-cert-*.timer
sudo systemctl daemon-reload
```

先对正式专用配置执行续期演练，确认 challenge、证书加载与服务保持正常，再启用两个 timer。演练成功时 deploy-hook 会 reload Nginx，仍加载正式证书。不可只以定时器存在证明续期成功。

```sh
sudo /opt/teachingopen-certbot/bin/certbot renew --dry-run --run-deploy-hooks --no-random-sleep-on-renew \
  --non-interactive --cert-name teachingopen-ip \
  --config-dir /var/lib/teachingopen-acme/config \
  --work-dir /var/lib/teachingopen-acme/work \
  --logs-dir /var/lib/teachingopen-acme/logs \
  --deploy-hook '/usr/sbin/nginx -t && /bin/systemctl reload nginx'
sudo systemctl start teachingopen-ip-cert-check.service
sudo systemctl enable --now teachingopen-ip-cert-renew.timer teachingopen-ip-cert-check.timer
systemctl list-timers 'teachingopen-ip-cert-*'
```

每小时的检查连接本机 443，使用公网 IP 验证 TLS 身份，检查**正在提供**的证书链、IP SAN、至少 48 小时剩余时间，以及它与磁盘叶证书的 SHA-256 一致性。检查单元以 root 运行，以便穿过原有私有 ACME 目录读取公开叶证书；不读取私钥，也不放宽证书目录权限，保留只读文件系统等 systemd 限制。它不依赖云端 NAT 回流；不证明外部安全组可达。外部网络还应执行不带 `--connect-host` 的相同检查。

检查失败会产生非零状态并保留 systemd/journal 记录。磁盘与服务证书指纹的比较会发现仍在提供旧证书的情况，即使旧证书剩余有效期尚超过 48 小时。服务器本身没有短信或邮件发送功能；当前试行选择通过本机 Codex 对话的每小时检查接收告警，具体依赖与边界见下文。

### 本机只读告警检查

`monitor_ip_https.py` 通过已配置的 Workbench profile 查询四个 systemd 单元、实际 TLS 证书和经过筛选的续期结果，并从本机检查公网 HTTP/HTTPS 入口。它不申请证书、不控制服务、不登录业务，也不读取或输出账号密码、证书私钥或原始服务器配置。检查结果与本机上次状态比较，健康基线或无变化时不要求通知；新故障、严重度升高、恢复及首次确认新正式证书已加载会产生需关注的变化。

```sh
python3 "$SOURCE/deploy/monitor_ip_https.py" \
  --ip "$PUBLIC_IP" --workbench "$WORKBENCH" \
  --profile teachingopen --region cn-beijing --instance-id "$INSTANCE_ID" \
  --state-file "$MONITOR_STATE"
```

上述变量应指向已核对的实例、可信 CLI 绝对路径和本机私有状态文件。状态文件不进入 Git；工具保存的只有脱敏健康摘要和证书信息，不复制 Workbench 凭据。用 Codex 的 heartbeat 自动化每小时调用检查，明确要求状态无变化保持安静，只在可操作的变化发生时通知。监控不可达或缺少必要数据不能视为健康，也不能据此清除既有告警。

临近到期按 48 小时和 24 小时区分风险级别；单次成功的续期检查不证明发生了换证。首次新证书加载需要前后指纹变化、有效期前移、服务器磁盘与实际服务一致，并由公网可信 TLS 复核；没有定时触发证据时，只报告新证书已加载，不宣称自动续期。另保留独立的首次调度证据事件：成功 wrapper 的 invocation、换证结果与磁盘/公网叶证书相符，并且 timer 触发时间与 service 启动时间紧邻时，报告“与定时调度记录相符”；这仍不是触发因果的严格证明。新叶已观察到而日志尚未到齐时保留候选，后续补齐证据仍可报告。

**Codex 对话告警依赖本机在线、Codex 自动化可运行及 Workbench 可用，离线期间不能保证及时通知。** 服务器的续期和每小时证书检查仍独立运行。创建自动化及手动跑通相同探针，不等于已经验证未来告警的实际投递；长期无人值守需另外评估独立于本机的通知渠道。现阶段继续保留 HTTP/HTTPS 并行，不因监控成功而自动切换最终入口。

## 4. 切换入口与回退

业务验证、续期演练和失败发现方式均就绪后：

```sh
sudo python3 "$SOURCE/deploy/ip_https.py" activate \
  --target "$SITE" --candidate "$WORK/rendered/https.conf" \
  --expected-target-sha256 "$(sudo python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["files"]["trial.conf"]["sha256"])' "$WORK/rendered/manifest.json")" \
  --backup "$WORK/before-https" --nginx /usr/sbin/nginx
```

新注册二维码直接编码 HTTPS。旧 HTTP 页面链接可临时跳转；已经以 HTTP 发出的凭据无法靠后续重定向补救，接口调用方须直接改为 HTTPS。HTTP API 返回 426 是刻意的边界，不应为“兼容”继续传递敏感请求。

人工回退先退回上一阶段：

```sh
sudo python3 "$SOURCE/deploy/ip_https.py" rollback \
  --target "$SITE" --backup "$WORK/before-https" --nginx /usr/sbin/nginx
```

这恢复到保留 HTTP 的 HTTPS 试行状态。若要再退到 bootstrap，使用 `before-trial`；恢复最初站点前还须按下一段处理后端信任配置。每一步都先核对摘要、校验再 reload。配置有其他人的改动时工具拒绝覆盖，应先人工比较处理。

若撤销整个并行试行，先用 `before-trial` 回到 bootstrap（撤下 TLS，但仍覆盖转发头），停止本次两个 timer，再恢复完整后端配置并重启，确认 HTTP 正常后用 `before-bootstrap` 恢复原 Nginx。不要在后端仍信任转发头时先恢复会透传这些头的原站点。云安全组只撤销本轮实际新增的精确 443 规则，保留原有规则和其他人的后续变更。

进程被 SIGKILL、主机断电等情况无法执行自动恢复；已提前落盘的备份和中间状态供下次显式 `rollback` 使用。工具允许恢复中断时已知的原配置/候选配置，仍拒绝未知改动。若报告 `recovery_required`，需按备份处理并核查 Nginx；不要反复启用新候选。成功返回仅证明配置检查和 reload 命令通过；旧 worker 可能短暂共存，之后还须用新连接确认实际响应、证书及业务。

回到纯 HTTP 是明确的运维决定，真实用户的传输保护将暂时撤销。回退不恢复数据库、账号、课程或期间新增的数据；应用数据持续保留。HTTPS 签发资料和私钥也保留以便诊断。若停留在仍覆盖转发头的 bootstrap，后端可信代理片段可以保留；若恢复未覆盖这些头的原站点，必须先恢复后端配置并受控重启。完全撤下 HTTPS 时停止本 PR 的两个 timer，保留日志和证书。

## 官方依据与本地验证

- [Let’s Encrypt IP 证书与 160 小时有效期](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability)
- [Certbot IP 证书、webroot 和续期加载](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)
- 本地单元、真实 Nginx/TLS、可信代理验证和未完成项记录在 `docs/optimization/ip-https-pr.md`。
