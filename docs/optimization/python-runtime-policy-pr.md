# Python 发布环境运行与加载失败恢复

日期：2026-10-09。基线：`integration/product-candidate` 的 `6eee9aa`，依赖集成候选 PR #79。范围为一个故障修复 PR，不包含其他产品功能或生产部署。

## 问题与修复

正式 Nginx 配置向所有静态资源发送 `Cross-Origin-Resource-Policy: same-site`。Python 的 `sandbox="allow-scripts"` iframe 使用不透明来源，其运行脚本和样式因此被浏览器以 `ERR_BLOCKED_BY_RESPONSE.NotSameSite` 拦截。普通本地预览没有该响应头，所以之前的预览运行不能覆盖这个发布问题。

两份 Nginx 配置改用精确 URI 映射，只对 Python 执行器需要的 8 个公开脚本/样式返回 `cross-origin`。页面、Python 源文件、其他静态资源、API 和附件路径仍为 `same-site`；原有其他响应头、API 路由和敏感文件拒绝规则保留。

iframe 的 `load` 事件在脚本加载失败时仍会触发。旧协调器在该事件里交出代码和消息端口，超时后又等待未启动运行器的停止确认，最终卡在“停止尚未确认”。现在必须同时收到当前 iframe 的加载事件和可信运行器的 `host-ready` 通知才交出代码；通知只接受当前 iframe 的 `WindowProxy`，程序结果与停止确认仍通过私有消息端口传输。尚未交出代码时可以安全清理失败的 iframe；已经交出代码后继续等待真实的停止确认。

这让加载失败明确显示“运行环境加载失败，请重新运行”，保留当前程序并允许重试，同时保留原有 Worker 隔离和停止边界。

## 验证方式

- Node 内置测试执行仓库的实际协调器、运行器和组件代码；新增检查覆盖脚本被拦截、两种就绪顺序、过期/伪造来源、加载中停止/替换、Worker 尚未就绪时的停止确认。
- 扩展已有 `web/tests/release-nginx/probe.py`，保留原有 60 项 API/路由检查，增加 43 项资源策略和安全响应头检查。使用固定官方 Nginx 镜像、只读挂载和本机监听；后端为合成 HTTP 回显服务。
- 浏览器检查使用实际公开 Python 静态文件、两份正式配置的副本和 Chromium。只替换监听端口、静态目录和合成后端地址，映射与响应头规则来自被审阅配置。
- `web/tests/python-execution-frame/nginx-browser-check.js` 复用已有 6 个浏览器场景，另外阻断 `runner.js`，检查无 Worker 启动、错误状态、代码保留及同页点击运行恢复，最后检查海龟绘图。每个入口使用独立测试标签页，不提交或保存作品。

## 验证结果

- 前端完整测试：692/692 通过；变更的两个公开 JS 文件 ESLint 检查为 0 错误、0 警告。
- Nginx 1.30.5 的真实 HTTP 检查：Docker 发布配置与原生示例配置各 103/103 通过，共 206 项。相同检查在旧基线上各有 32 项运行资源策略失败，原有 60 项路由检查仍通过。
- Chromium 实际页面：两份配置分别覆盖编辑器与播放器，共四组；每组原有 6 个运行场景通过，并验证阻断脚本后的清理、代码保留、零 Worker 启动、同页重试恢复和海龟绘图。旧基线实际浏览器出现 6 次 `ERR_BLOCKED_BY_RESPONSE.NotSameSite`，输出为空并进入 `stop-error`。
- 新增的 4 个生命周期回归检查在旧协调器上为 1 通过、3 失败，在修复后全部通过。
- 已查看编辑器和播放器的绘图截图，确认线段及 `NGINX_TURTLE_OK` 输出。测试工具曾被未保存程序的离页提示中断，最终结果来自使用独立标签页后的完整运行。

结果摘要和候选文件 SHA-256 见 [summary.json](evidence/python-runtime-policy/summary.json)，绘图截图见 [编辑器](evidence/python-runtime-policy/index-turtle.png) 和 [播放器](evidence/python-runtime-policy/player-turtle.png)。完整命令日志保留在本机任务产物目录，未提交到仓库。

## 复跑入口

安装项目既有依赖后执行：

```sh
cd web
npm test
```

已有 Docker 环境并准备好脚本中的固定官方镜像后，从仓库根目录执行：

```sh
python3 web/tests/release-nginx/probe.py \
  --output-dir /tmp/teachingopen-python-policy-check \
  --expect-pass
```

浏览器检查从仓库根目录运行：先用 Playwright CLI 打开自有的本机 Nginx Python 页面，再把 `web/tests/python-execution-frame/nginx-browser-check.js` 的完整函数作为 `run-code` 参数。浏览器脚本只接受 `127.0.0.1` 地址。图片写入 `output/playwright/`。

## 交付与边界

由当前 Agent 实施和自检。没有独立 Agent 审查或用户人工验收。本轮使用既有本地前端依赖；改动为直接发布的静态 JS 和 Nginx 配置，实际浏览器直接执行这些文件，没有重新构建完整 Vue 应用。未修改后端、数据库、作品数据或线上服务。

发布时需要同时更新运行器静态资源和 Nginx 配置。新增 `map` 应放在 Nginx 的 `http` 上下文，与 `server` 同级；镜像的 `conf.d` 文件已经在该上下文内。示例配置也应保留文件顶部的映射，不能只复制 `server` 块。上线前仍需在实际目标服务上执行配置检查和浏览器回归。

本地验证不等于线上已修复，也不证明操作系统层面的瞬间 CPU 终止、所有 Python 库兼容性或多浏览器完整验收。
