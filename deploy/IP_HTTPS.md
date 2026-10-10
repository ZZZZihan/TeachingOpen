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

核实云端正在运行的配置，而不是直接套用旧报告：Nginx 版本/活动站点文件、前端真实目录、API 的 loopback 端口、配置额外规则、公网 IP 是否稳定、云安全组及主机防火墙的 80/443、现有应用启动方式。`render` 沿用仓库 `web/nginx/default.conf` 的业务规则，不能自动保留云端额外定制；必须审阅生成文件与当前活动站点差异。

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
sudo python3 "$SOURCE/deploy/ip_https.py" render \
  --ip "$PUBLIC_IP" --web-root "$WEB_ROOT" \
  --api-upstream "http://127.0.0.1:$API_PORT" \
  --acme-root /var/www/teachingopen-acme \
  --certificate /var/lib/teachingopen-acme/config/live/teachingopen-ip/fullchain.pem \
  --private-key /var/lib/teachingopen-acme/config/live/teachingopen-ip/privkey.pem \
  --output "$WORK/rendered"
sudo diff -u "$SITE" "$WORK/rendered/bootstrap.conf"
```

渲染目录须全新。`diff` 的非零退出只表示有差异，需要审阅路径、安全头、上传、媒体、WebSocket与自定义业务规则。当前生成器是一个明确拓扑的候选，不是任意 Nginx 配置迁移器。

把 `ip-https-proxy.properties.example` 中的配置合并进**现有完整私有应用配置**，先备份这份配置；不要用片段替换整个配置，也不要输出其中凭据。它只信任 loopback 代理，Nginx 会覆盖转发头。按实际服务方式受控重启后端，再分别核对 HTTP 正常、HTTPS 登录时 `teaching_media` Cookie 带 `Secure`。这一步使 TLS 在 Nginx 终止后 Java 仍能识别安全连接，适用于现有 Nginx 1.18，无需为 `proxy_cookie_flags` 升级 Nginx。

```sh
sudo python3 "$SOURCE/deploy/ip_https.py" activate \
  --target "$SITE" --candidate "$WORK/rendered/bootstrap.conf" \
  --backup "$WORK/before-bootstrap" --nginx /usr/sbin/nginx
```

用随机无敏感内容的 challenge 文件，从外部网络确认 `http://IP/.well-known/acme-challenge/<token>` 返回精确内容；不存在的 token 必须 404。不能以 SPA 首页的 200 代替 challenge 成功。完成后删除自己创建的探测 token。

## 2. 申请证书并试行 HTTPS

准备受维护的 Certbot **5.4 或更新版本**，本方案使用独立路径 `/opt/teachingopen-certbot/bin/certbot`；不复用不明版本的系统旧包。先运行 `--version` 核对。安装方式与版本另行按目标环境核实，工具不会自动安装软件。

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
  --backup "$WORK/before-trial" --nginx /usr/sbin/nginx
python3 "$SOURCE/deploy/check_ip_certificate.py" --ip "$PUBLIC_IP"
```

使用真实浏览器直接打开 HTTPS，不忽略证书错误。至少检查注册/登录、管理员与师生入口、视频起播/拖动、附件、三编辑器加载/保存、通知/云变量 WSS、退出。保持生产数据写入范围与已有授权一致，必要时在独立验证副本执行写入。核对返回 Cookie，而不仅是首页状态码。

现有主 API、编辑器与 socket 已有同源逻辑，历史课程内容仍可能含绝对 `http://` 链接。审计实际数据并在浏览器验证；HTTP 重定向不能替代 mixed-content 检查，不在本 PR 批量改写数据库。前端 origin 从 HTTP 变成 HTTPS 后，本地登录存储/草稿是不同 origin，应先保存未提交内容并重新登录。

## 3. 自动续期与实际服务证书检查

Let’s Encrypt IP 证书有效期为 160 小时。`teachingopen-ip-cert-renew.timer` 每天两次启动 Certbot，由 Certbot 判断是否到续期时间；只有成功续期后才执行 `nginx -t` 和 reload。专用 config/work/logs 路径及 `--cert-name` 防止触碰其他服务证书。

```sh
sudo install -d -m 0755 /opt/teachingopen-https
sudo install -m 0644 "$SOURCE/deploy/check_ip_certificate.py" /opt/teachingopen-https/
sudo install -m 0644 "$SOURCE/deploy/teachingopen-ip-cert-renew.service" /etc/systemd/system/
sudo install -m 0644 "$SOURCE/deploy/teachingopen-ip-cert-renew.timer" /etc/systemd/system/
sudo install -m 0644 "$SOURCE/deploy/teachingopen-ip-cert-check.timer" /etc/systemd/system/
sed "s/@PUBLIC_IP@/$PUBLIC_IP/g" "$SOURCE/deploy/teachingopen-ip-cert-check.service.template" \
  | sudo tee /etc/systemd/system/teachingopen-ip-cert-check.service >/dev/null
sudo systemd-analyze verify /etc/systemd/system/teachingopen-ip-cert-*.service /etc/systemd/system/teachingopen-ip-cert-*.timer
sudo systemctl daemon-reload
```

先对正式专用配置执行续期演练，确认 challenge、证书加载与服务保持正常，再启用两个 timer。演练成功时 deploy-hook 会 reload Nginx，仍加载正式证书。不可只以定时器存在证明续期成功。

```sh
sudo /opt/teachingopen-certbot/bin/certbot renew --dry-run --run-deploy-hooks \
  --non-interactive --cert-name teachingopen-ip \
  --config-dir /var/lib/teachingopen-acme/config \
  --work-dir /var/lib/teachingopen-acme/work \
  --logs-dir /var/lib/teachingopen-acme/logs \
  --deploy-hook '/usr/sbin/nginx -t && /bin/systemctl reload nginx'
sudo systemctl start teachingopen-ip-cert-check.service
sudo systemctl enable --now teachingopen-ip-cert-renew.timer teachingopen-ip-cert-check.timer
systemctl list-timers 'teachingopen-ip-cert-*'
```

每小时的检查连接本机 443，使用公网 IP 验证 TLS 身份，检查**正在提供**的证书链、IP SAN 和至少 48 小时剩余时间。它不依赖云端 NAT 回流；不证明外部安全组可达。外部网络还应执行不带 `--connect-host` 的相同检查。

检查失败会产生非零状态并保留 systemd/journal 记录；**本 PR 没有配置短信、邮件或其他主动通知**。正式长期使用前，接入已有告警渠道，或明确由维护者查看失败状态。不能把日志存在描述为已通知用户，也不能忽略 Certbot 退出为零但未触发 reload 的情形；实际服务证书检查会发现仍在提供旧证书。

## 4. 切换入口与回退

业务验证、续期演练和失败发现方式均就绪后：

```sh
sudo python3 "$SOURCE/deploy/ip_https.py" activate \
  --target "$SITE" --candidate "$WORK/rendered/https.conf" \
  --backup "$WORK/before-https" --nginx /usr/sbin/nginx
```

新注册二维码直接编码 HTTPS。旧 HTTP 页面链接可临时跳转；已经以 HTTP 发出的凭据无法靠后续重定向补救，接口调用方须直接改为 HTTPS。HTTP API 返回 426 是刻意的边界，不应为“兼容”继续传递敏感请求。

人工回退先退回上一阶段：

```sh
sudo python3 "$SOURCE/deploy/ip_https.py" rollback \
  --target "$SITE" --backup "$WORK/before-https" --nginx /usr/sbin/nginx
```

这恢复到保留 HTTP 的 HTTPS 试行状态。若要再退到 bootstrap，使用 `before-trial`；再回到最初站点使用 `before-bootstrap`，按实际激活的逆序执行。每一步都先核对摘要、校验再 reload。配置有其他人的改动时工具拒绝覆盖，应先人工比较处理。

进程被 SIGKILL、主机断电等情况无法执行自动恢复；已提前落盘的备份和中间状态供下次显式 `rollback` 使用。工具允许恢复中断时已知的原配置/候选配置，仍拒绝未知改动。若报告 `recovery_required`，需按备份处理并核查 Nginx；不要反复启用新候选。成功返回仅证明配置检查和 reload 命令通过；旧 worker 可能短暂共存，之后还须用新连接确认实际响应、证书及业务。

回到纯 HTTP 是明确的运维决定，真实用户的传输保护将暂时撤销。回退不恢复数据库、账号、课程或期间新增的数据；应用数据持续保留。HTTPS 签发资料和私钥也保留以便诊断。若完全撤下 HTTPS，停止本 PR 的两个 timer，保留日志/证书；后端可信代理片段可以保留（HTTP 下仍报告非安全请求），若需撤销则从备份恢复相应配置并受控重启后端。

## 官方依据与本地验证

- [Let’s Encrypt IP 证书与 160 小时有效期](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability)
- [Certbot IP 证书、webroot 和续期加载](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)
- 本地单元、真实 Nginx/TLS、可信代理验证和未完成项记录在 `docs/optimization/ip-https-pr.md`。
