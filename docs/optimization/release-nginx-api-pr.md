# 发布代理支持正常 API 方法与路径

教学资源编辑使用 PUT，删除使用 DELETE，但现有发布 Nginx 在 server 层直接返回 405。原 `/api` 前缀配合带 `/api/` 的 proxy_pass 还会把 `/api/probe` 传成 `/api//probe`，误将 `/apiculture` 等前端地址交给后端，并改变编码路径。本 PR 修复 Docker 发布配置、原生部署示例及 README 片段，使应用既有接口能按原始方法和 URI 到达上游。

修改范围为移除全局方法限制中的 PUT/DELETE、仅代理 `/api/` 命名空间、使用没有 URI 部分的 proxy_pass。裸 `/api` 明确返回 308 到 `/api/` 并保留查询参数；客户端须支持保持方法的 308。其他禁止的方法、静态敏感文件规则、响应头及代理容量参数保持原样。location 选择仍遵循 Nginx 对 URI 的规范化规则，不能据此声称所有任意编码路径都按字节选择 location。

用户指定 GPT-6.1-sol / ultra 子 Agent 分别实现与独立实测，主 Agent 审阅补丁并复算结果；当前委派接口没有单独 Fast 参数。分支以 github/main `2e0c1831a234c138c4c6873b56f5060e3a80aec8` 为基础，可独立审阅，无需前置产品修复 PR。

## 实际检查

- 在本机已有 Docker 中运行官方固定摘要的 Nginx 1.30.5 Linux/arm64 镜像；仅发布 loopback 18186/18187，使用自制 echo 上游和静态 canary。没有启动或改动生产系统。
- 冻结同一组 60 项契约后，两份旧配置各 31/60 通过、29 项不符合预期；两份修复配置各 60/60 通过。覆盖 GET/HEAD/POST/PUT/DELETE/OPTIONS、双斜杠和编码/中文路径、重复查询参数、前缀相似地址、裸 API 308 与同方法后续请求、SPA、静态拒绝规则和禁止的方法。
- 初始 42 项探索检查各 26/42，随后扩为 60 项并重新执行旧新对照；两种分母不混算。Docker 移除后短暂的端口释放延迟已在探针内处理，原始观察保留在本机。
- 可复用探针最终版本又执行两份修复配置，各 60/60，退出 0。独立测试说明包含命令与镜像/源码摘要。主 Agent 逐行复算旧新结果、核对两份契约文件字节一致和配置摘要一致。
- 所有本任务容器经自身 label/ID 核对后停止并删除；释放端口的结果已记录。未触碰其他 Docker 容器或全局配置。`git diff --check` 通过。

详见[作者说明](release-nginx-api-author.md)、[独立实测](release-nginx-api-tests.md)和[主 Agent 复算](evidence/release-nginx-api/root-review.json)。测试脚本为 `web/tests/release-nginx/probe.py`，要求已有可用 Docker 和已拉取的固定镜像；脚本不负责安装或启动 Docker。

这是实际 Nginx 传输与静态路由的证据。上游为合成 echo，未执行真实账号鉴权、业务写入或请求正文一致性检查。308 Location 的路径、查询与同方法后续请求已测；因容器 listener 与宿主发布端口不同，本次没有把绝对重定向的 origin/port 纳入产品结论。实际 TLS 终止、完整应用浏览器流程、目标部署平台及生产验收仍需各自验证。此 PR 不代表上线或生产故障已经发生。
