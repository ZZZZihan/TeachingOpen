# 本地同源 WebSocket 转发

前置为 PR #34 `20f52ca`。产品代码 `a99f0ec3440071300730ddf12f48674d40619392`；改动仅本地开发代理与验证脚本，Java 业务和前端页面均未修改。

原 `serve-frontend.py` 删除 Connection 请求头并以普通 HTTP 缓冲响应，合法 WebSocket 13 握手在冻结旧包的 18132 上实际返回 HTTP 400。新代理对 `/api/websocket/` 的 GET 升级校验 key/version/Connection，核对上游 HTTP 101 和 accept，保留子协议/扩展头，再双向转发原始字节。浏览器 Origin 限制为当前本机前端端口的 127.0.0.1/localhost；无 Origin 的原生客户端仍由后端执行身份认证。

读取 HTTP 头时不预读，避免吞掉紧随握手的首帧；普通 POST 改为循环读完 Content-Length，保持分段上传完整。每方向待写队列最多 64 KiB，读写受背压控制；上游握手限时 5 秒，隧道无数据进展 90 秒关闭。任何一侧 TCP 结束，排空已接收队列后关闭连接；网络错误释放上游。消息、令牌和 URL 不进入代理日志。保留同源 CSP，没有添加依赖、开启通知 UI 或修改生产代理。

实现核对依据：[RFC 6455 握手协议](https://www.rfc-editor.org/rfc/rfc6455)、[Python socketserver 传输接口](https://docs.python.org/3/library/socketserver.html)。这是本机开发服务器，不提供生产反向代理、TLS、HTTP/2 或连接容量承诺。

## 验证

- 42/42 Python 检查，包括新增 12 项受控 TCP 传输检查：握手后立刻跟随的数据、客户端提前送帧、二进制/control-frame 字节保真、1 MiB 流及另一个连接并行、双向断开、空闲清理、非法请求/Origin、拒绝/错误/超大/超时握手、上游故障后恢复、普通静态/SPA/HTTP、重复 Cookie 和分段 POST。受控后端是测试夹具，不声称这些都是真实 Java 业务检查。
- 真实 Java 后端经前端端口：通知 44/44（WebSocket 经代理，发送权限对照 REST 仍直连）、实际发布 JS helper 加 Node 原生 WebSocket 5/5（连接和发送均经代理）、multipart/容器 ping/pong/close 9/9、登录 Cookie/课程/受保护媒体字节/Range/拒绝/静态 SPA 13/13，共 71 项。最后一组真实验证码登录由既有 CLI 合成夹具完成，不是浏览器登录验收。
- 错账号、匿名和退出会话的通知限制继续生效；两标签收到本人通知，关一个后另一个继续接收。Scratch 只测协议 ping/pong/close，没有发送任何云变量业务消息，不能证明云变量权限已修复。
- 首轮传输夹具误用了 17 字节握手 key，导致合法场景被校验拒绝；更正为标准 16 字节后全量重跑通过，应用校验未放宽。原始失败日志保留在私有 `.devspace`。
- 新冻结包复用 PR #34 JAR `fdc60a9974eed65cc25de13e5a38931bba0f14122e0f3c2adeeb59ec03771396`，以及本地组合 `0caaab3` 的既有前端产物（实际构建代码 `7a0fe01`，4,884 文件）。旧复现包的页面版本较旧；对照只针对同一后端上的代理握手，未声称两包页面相同。没有重新构建或重复前端检查。
- 演练 69 表仅 sys_log 3,786→3,807，其他 68 表和附件摘要一致。原联调环境全库/附件一致；本轮保护集合为 Git 跟踪和非忽略未跟踪文件共 5,731 项，前后摘要相同。原通知阶段的 5,634 项是不同范围的历史记录。所有检查数据为自己的合成夹具。
- `recovery-a` 的 MySQL/Redis/后端/前端已停止，13336/16409/18131/18132 端口关闭；数据库、候选包和私有日志保留。

逐项结果及摘要见 [证据清单](evidence/local-websocket-proxy/manifest.json)、[候选与范围](evidence/local-websocket-proxy/candidate.json)。工程自检，没有其他 Agent 审查、人工 UI 验收或生产部署。

## 重跑入口

在保留的隔离环境启动真实候选后，从仓库根目录执行；所有路径均指向任务自己的合成环境。

```sh
python3 -m unittest discover -s api/dev -p 'test_*.py'
python3 api/dev/verify-notification-websocket.py --runtime "$runtime" --jar "$jar" --via-frontend --output "$output/notifications.json"
python3 api/dev/verify-notification-client.py --runtime "$runtime" --jar "$jar" --via-frontend --output "$output/client.json"
python3 api/dev/verify-container-http.py --runtime "$runtime" --jar "$jar" --via-frontend --output "$output/container.json"
python3 api/dev/verify-frontend-http.py --runtime "$runtime" --jar "$jar" --dist "$dist" --output "$output/http.json"
```

普通 HTTP 仍采用现有内存缓冲方式，本项没有升级成流式媒体/大文件代理；大量连接、长期弱网和生产域名需要另行验证。真实浏览器完整角色流程、用户视觉评阅、Scratch 云变量及其他通知写入入口授权仍待后续。GitHub 不自动合并。
