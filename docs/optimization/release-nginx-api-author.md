# Release Nginx API 路由修复：作者记录

日期：2026-10-05。基线提交：`2e0c1831a234c138c4c6873b56f5060e3a80aec8`。工作分支：`fix/release-nginx-api`。

本次修改解决实际发布配置里的两个问题：正常业务使用的 PUT/DELETE 在到达后端前被全局返回 405；`location ^~ /api` 与带 `/api/` URI 的 `proxy_pass` 组合会改写上游路径，并把 `/apiculture` 等相似前缀当作 API。

## 现状依据

- `web/Dockerfile` 将 `web/nginx/` 加入 `/etc/nginx/conf.d/`，因此 `web/nginx/default.conf` 是前端镜像的 Nginx 源配置。
- 后端三个环境配置均设置 `server.servlet.context-path: /api`；代理需要保留 `/api` 路径前缀。
- `web/src/api/manage.js` 的 `putAction`、`deleteAction` 分别发 PUT、DELETE；`TeachingCourseController`、`TeachingCourseDeptController` 和 `TeachingWorkController` 都声明了对应编辑/删除路由。Nginx 的全局方法拒绝与这些现有业务接口冲突。
- README 的部署片段存在同样的 `/api` 前缀与 `proxy_pass .../api/` 路径组合，因此同步修改该片段。
- 独立探测 Agent 用官方 Docker Nginx 1.30.5 复现旧配置的 PUT/DELETE 405、`/api/probe` 变成 `/api//probe`、编码路径被改写，以及 `/apiculture` 被转发的问题。旧 Docker 配置 SHA256 为 `d1b42c0f1d5cea0d4b7a08272364d0308c86dbdcbf85e990240e6456b9730370`，与本分支基线文件一致。具体运行结果由独立探测报告保存。

## 最小改动与接口契约

只修改 `web/nginx/default.conf`、`资料/nginx.example.conf` 和 README 中同类 Nginx 片段：

1. 全局拒绝方法列表仅去掉 PUT、DELETE，使 API 请求可以交给后端路由及其既有鉴权处理；TRACE、TRACK 和其余原有受限方法保留。
2. API 代理使用 `location ^~ /api/`，普通 `/apiXYZ`、`/apiculture` 等请求进入既有前端静态/SPA 路由。
3. `proxy_pass` 保留原来的上游地址，但去掉 URI 部分：Docker 为 `http://api:8080`，独立部署示例为 `http://127.0.0.1:8080`。未被 Nginx 内部改写的 API 请求将原始请求 URI 传递给上游，避免额外斜线和路径编码替换。
4. 精确的 `/api` 返回 `308 /api/$is_args$args`。例如 `/api?cursor=%2F` 的 Location 指向 `/api/?cursor=%2F`。308 的契约要求客户端跟随时保留原方法及请求体；Nginx 返回重定向本身不会向上游转发该请求。正常业务接口直接使用 `/api/...`。

原有响应头、敏感文件/目录规则、静态 SPA 回退、gzip、上游头、超时、WebSocket 头、缓冲与请求体大小设置均沿用。配置仍以 Nginx 的规范化 URI 进行 location 匹配；本修复不增加新的路径清洗或后端授权规则。

## 作者自检与后续验收边界

`git diff --check` 通过；作者核对补丁仅包含上述代理及方法列表变化，以及两个原先无末尾换行配置文件的末尾换行。配置已交给独立探测 Agent 冻结后复测，作者未运行或修改服务、容器、浏览器、数据库或实际业务数据，也未提交或推送。

静态路径 PUT/DELETE 预期继续由 Nginx 静态处理返回 405，不开启静态文件写入；此行为以及路径、query、其他拒绝方法、敏感文件/目录回归由独立实际 Nginx 探测报告裁定。该探测的上游是本地 echo 服务，证明 Nginx 转发契约；它不证明实际后端鉴权、真实业务编辑/删除、生产部署或人工验收。

兼容性变化包括：裸 `/api` 从隐式改写代理变为显式 308；相似前缀不再被当作 API；原先被 Nginx 拒绝的 PUT/DELETE 到达后端。发布前需要评审这三项明确变化，尤其后端对业务写操作的既有授权责任。客户端是否跟随 308 取决于客户端实现；本次以响应状态、Location 和无上游请求作为重定向契约。

冻结文件 SHA256：

| 文件 | SHA256 |
| --- | --- |
| `web/nginx/default.conf` | `93b019f547c36b708d46ac175368aee69a234495e6456b3e48e75d681e799a40` |
| `资料/nginx.example.conf` | `00b2d82e81b4d0817de75846b6f258fc916464a809eeb2a867dacd257ee5b134` |
| `README.md` | `54931239aa55913772950ebb1d92e616bf47b3f18c83756aff56532e6debe6cd` |
