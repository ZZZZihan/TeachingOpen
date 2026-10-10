# 通知连接绑定认证身份，并保持多标签页正常接收

日期：2026-10-03。基于 PR #33 `fix/tomcat-maintenance`，产品提交 `10a3f167b90fe4f270792e035985c4a38aedb305`。本项处理 `/websocket/{userId}` 通知订阅及其现有前端客户端，不修改 Scratch 云变量端点。

## 实际问题与修复结果

旧版把 URL 中的用户 ID 直接写入静态 sessionPool，握手无认证。独立合成环境实际确认：匿名连接、持有另一个学生令牌的连接均能收到目标学生的定向通知；退出后的旧连接仍接收；同一账号第二个标签覆盖第一个，关闭第二个后第一个也收不到定向通知。旧 `/webSocketApi/sendUser`、`sendAll` 测试接口允许学生和教师直接发送，通知正文还会进入 INFO 日志。

新版连接在首次文本帧 `{type: "authenticate", token: "..."}` 通过既有 Shiro 令牌校验、且令牌用户 ID 与路径 ID 一致后才注册订阅。认证成功返回 `{"cmd":"authenticated"}`，后续保持 `HeartBeat` / `heartcheck` 和现有 `user` / `topic` 消息结构。令牌不放在 URL、回包或日志中。错误身份、无效/修改过的令牌、匿名心跳、非法首帧、连接中换身份均关闭为 1008。

每次应用心跳和通知投递前重新核对令牌，退出或失效后不再向该连接投递新消息。同一账号可以有多个独立连接；使用线程安全订阅集合，关闭/异常仅清除对应连接。未认证连接的空闲上限为 10 秒，认证后为 60 秒，文本接收上限 8 KiB。这里的服务端空闲超时不是抵御持续协议流量的认证截止时间或连接限流。

两个旧测试发送接口增加 admin/dev 角色限制；实际验证了管理员允许，匿名、学生和教师拒绝且没有投递。其他公告 REST 写入接口及系统内部发送来源的权限不在这两个接口的结论中。

前端可选通知客户端同步改为首帧认证、收到确认后心跳、网络断开重连；认证拒绝不循环重试。账号切换、退出和组件销毁会停止旧连接/重连计时器，旧消息不能触发新账号通知刷新。消息改用 JSON.parse，移除 eval 和正文控制台输出。原组件 mounted 中的通知 WebSocket 初始化仍然关闭，本项没有擅自开启通知功能或改变页面布局；手动启用该入口时会使用新协议。旧的无认证第三方客户端必须升级，不能继续按路径 ID 订阅。

## 验证范围

| 检查 | 结果 |
| --- | --- |
| 同一探针对旧 JAR 的行为对照 | 37/37 符合旧缺陷预期 |
| 新 JAR 实际 WebSocket/HTTP 通知专项 | 44/44 |
| 交付 JS 客户端直连实际 Java 后端 | 5/5：两个连接收发、单连接销毁、清空登录后抑制回调、数据/附件保护 |
| 同 JAR 认证/角色缓存/权限菜单/恢复业务/容器传输回归 | 7/11/34/29/9，合计 90/90 |
| 分支前端受控检查 | 52/52，包含新增 11 项客户端及组件生命周期检查 |
| 新 JS helper ESLint | 0 error / 0 warning |
| 旧 HeaderNotice.vue ESLint | 122 errors / 148 warnings；基线 212 / 211，仍未通过全文件 lint |
| 前后端构建 | Java 8u504 / Maven 3.9.16 三模块 clean package，前端生产构建成功；前端 6 条既有警告 |

新版真实服务/客户端及回归共 139 项通过，不与前端受控检查合并计数。原生 JS 客户端使用 Node 26 的 WebSocket、交付 helper 和真实 HTTP 发送接口，凭据只经 stdin 临时传递；这不是浏览器登录、验证码或通知 UI 验收。所有发送均限于专用本机合成账号和本次连接，没有向真实用户或外部系统发消息。

父 POM 仍跳过 Java 测试，构建不等于 Java 测试通过。前端沿用已存在且锁文件摘要相同的 node_modules，没有宣称新安装验证。探针首次把旧心跳常量误记为 `check`，6 项断言失败；读取实际 `WebsocketConst.CMD_CHECK` 后修正为 `heartcheck`，保留失败记录，再完成最终 37/37 对照，没有修改旧应用。

JAR SHA-256 为 `fdc60a9974eed65cc25de13e5a38931bba0f14122e0f3c2adeeb59ec03771396`。937 个应用条目中只有 WebSocket.class、TestController.class 改变；冻结包与构建 JAR 一致。新版专项覆盖普通日志中通知正文及有效凭据不出现，没有将该结果扩大为全系统日志审计。

## 数据与兼容边界

演练前后 69 表只有正常登录审计 sys_log 从 3,710 增至 3,786 行，其他 68 表和全部附件摘要一致；原联调环境全库/附件与原源码 5,634 个文件未变。演练的 13336/16409/18131/18132 服务已停止，新旧候选包和私有数据保留。没有修改数据库结构、生产配置或合并远端 PR。

本项不承诺已入队消息可在退出瞬间被撤回；令牌复核发生在每次应用收发前，已获得的字节无法收回。没有进行大量连接、慢接收客户端、跨节点广播或 TLS 容量验收。Scratch 云变量的鉴权、消息日志和其他公告写入权限继续作为独立待办，不因本项通过被视为安全。

本地组合额外发现既有 `serve-frontend.py` 只代理普通 HTTP：从 18112 请求 WebSocket Upgrade 实际返回 HTTP 400，无法建立同源通道，见 [代理限制](evidence/notification-websocket/proxy-limit.json)。直连后端的客户端检查不能代替这条路径；现有可选通知入口保持未启用，开发代理支持将作为下一项独立修复，Scratch 云变量也依赖此通道。

## 复现与证据

使用已启动的独立合成环境。输出路径须不存在，各套件顺序运行；首项运行旧包时增加 `--expect-legacy`。第二项通过 stdin 给本机 Node 子进程临时传递合成凭据，不写 token 文件或命令行参数。

```sh
python3 api/dev/verify-notification-websocket.py --runtime "$RUNTIME" --jar "$JAR" --output "$SOCKET_OUTPUT"
python3 api/dev/verify-notification-client.py --runtime "$RUNTIME" --jar "$JAR" --output "$CLIENT_OUTPUT"
cd web
npm test
```

[旧对照](evidence/notification-websocket/legacy.json)、[新专项](evidence/notification-websocket/fixed.json)、[真实 JS 客户端](evidence/notification-websocket/client.json)、[回归汇总](evidence/notification-websocket/regressions.json)、[数据核对](evidence/notification-websocket/data-preservation.json)、[候选来源](evidence/notification-websocket/candidate.json) 和 [全部证据摘要](evidence/notification-websocket/manifest.json)。
