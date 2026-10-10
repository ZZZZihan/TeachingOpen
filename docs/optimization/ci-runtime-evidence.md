# HTTPS CI 回显诊断与持续监听夹具

合成 HTTPS 集成测试原先用单连接 `nc -l` 服务 API 回显，每次请求完成后退出，再由 shell 循环重新绑定端口。Nginx 已能服务静态页面和前面的 API 请求，下一次请求仍可能碰到 upstream 暂时没有监听的间隙。这个问题发生在测试夹具，不涉及 TeachingOpen Java API 或线上 Nginx 配置。

原始失败先被另一处诊断缺陷遮蔽：HTTP 回显在检查状态前直接按 `key=value` 解析，非键值响应使它抛出 `ValueError`，异常又跳过最终 JSON 输出。[PR #102 tools 日志](https://github.com/ZZZZihan/TeachingOpen/actions/runs/38068467038/job/114260831926)和[PR #103 tools 日志](https://github.com/ZZZZihan/TeachingOpen/actions/runs/38068501256/job/114260933095)均有该异常；它们未记录实际 HTTP 状态或正文，不能单独用来断言这两次都是 502。

诊断提交 `e9b2bb45` 保留原监听、就绪与请求行为，三处回显均先校验 HTTP 200、UTF-8 和键值格式，再检查业务内容。失败保留方法、路径、状态、Content-Type、最多 4096 字节的正文，并在清理测试容器前采集最多 100 行、16384 字符的 Docker 日志。未知普通异常也写入失败 JSON；日志或清理失败不会替换原验证错误。该版本的[首次真实 CI](https://github.com/ZZZZihan/TeachingOpen/actions/runs/38069177326/job/114262909216)完成 461/461 检查，其中 template 109/109、reviewed-native 352/352。这次成功没有证明间歇故障已经解决。

提交 `3d751d05` 在 bootstrap HTTP 阶段追加连续 10 轮 GET、POST、PUT、DELETE，每场景最多 40 次请求，复用原有 HTTP、回显、URI、方法、正文、scheme 和 CORP 断言，不加入 sleep 或重试。[该次真实 CI](https://github.com/ZZZZihan/TeachingOpen/actions/runs/38069426903/job/114263631429)在 template 第 10 轮 DELETE 失败，报告 184/185 检查通过，HTTP 502、157 字节 Nginx HTML，已完成 9 轮及第 10 轮前三种方法。清理前的容器日志对应同一方法和 URI：

```text
connect() failed (111: Connection refused) while connecting to upstream
request: "DELETE /api/runtime-echo/item%20one?method=DELETE&literal=a%2Fb HTTP/1.1"
upstream: "http://127.0.0.1:18080/api/runtime-echo/item%20one?method=DELETE&literal=a%2Fb"
```

这次证据确认故障发生在连续请求之间，不能用首次启动尚未就绪解释。最小修复将夹具改为 BusyBox `nc -lk`：父进程持续持有监听 socket，为连接执行独立 echo 子进程，避免每次请求都重新绑定。仍仅绑定 `127.0.0.1:18080`，保留原静态就绪条件、全部转发与 TLS/回滚断言、连续探针和失败证据；没有放宽检查或增加请求重试。[BusyBox 兼容实现](https://raw.githubusercontent.com/mirror/busybox/master/networking/nc_bloaty.c)说明并实现了 `-lk` 的持续 accept/fork 行为，固定镜像的实际兼容性由以下 CI 运行核对。

作者离线验证执行 `python3 -m unittest discover -s deploy -p 'test_ip_https.py' -v`，57/57 通过；新增诊断、连续请求及持久监听配置回归已包含在 tools 现有显式测试清单。`py_compile` 与 `git diff --check` 通过。这些测试没有启动 Docker 或 HTTP 服务，不能替代真实镜像矩阵。

持续监听修复提交 `1ff3072d`、整合候选 `aa76b8fc` 的[最终 tools 运行](https://github.com/ZZZZihan/TeachingOpen/actions/runs/38069685997/job/114264379925)完成 **783/783** 检查：template **270/270**、reviewed-native **513/513**。两个场景各完成 10 轮连续检查，40 次回显均是 HTTP 200，报告明确记录零重试、零等待。原有可信 CA/IP SAN、无 SNI、多虚拟主机、WebSocket 实际帧、伪造转发头边界、媒体 Range、配置拒绝及切换/回滚矩阵全部完成；没有跳过 reviewed-native 场景。该真实运行同时证明所固定镜像内 `nc -lk` 能完成本测试协议，独立 Agent 对诊断及监听修复的技术复核无阻塞发现。

最终报告绑定同一个固定镜像与候选源码，摘要如下；首诊断成功、旧监听连续失败和最终成功是三次不同运行，计数不能相加：

```text
image: nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
actual image ID: sha256:43d9d8c1f8968f09df8c1aa6c136ecc617e62d64fe4c0b24c97de4eb210bd973
deploy/test_ip_https_runtime.py: d3a20b53f5163118102fc6970718973b7937b56e6b3edc4c21fd6f00b2015f77
deploy/test_ip_https.py: 2ed9062daa8135c902443f180d8630166c3ebeebfa4f5e155d6eddb818dca53b
final ip-https-runtime.json: 3809ab3ef1688235cb79a8a184f3f399f7b2d3bccff703eefa19c73b605f0c5e
```

全部运行范围均是隔离的合成 Nginx/TLS 夹具、合成 CA 和本机回环端口；不访问生产、不申请公网证书、不代表真实业务或人工验收。
