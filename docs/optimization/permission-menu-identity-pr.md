# 菜单加载使用当前认证身份，并支持空菜单

日期：2026-10-03。分支 `fix/permission-menu-identity`，基于 PR #18 的 `1bc4468934b353aafda5609d71533bb65fb2d326`。

## 问题与结果

旧接口 `/sys/permission/getUserPermissionByToken` 由请求头完成登录验证，却另外解码 URL 参数中的 token 来确定菜单用户名。真实学生会话携带管理员的查询参数，甚至携带声明管理员用户名但签名无效的查询 JWT，都能取得管理员菜单和按钮集合。此证据是菜单身份混淆，不等同所有管理员业务 API 均可越权。旧接口还记录完整查询令牌；权限表为空时，强制读取默认首页的 `get(0)` 导致失败。

修复后只使用 Shiro 已认证的 `LoginUser`。旧路径保留，旧 query token 参数忽略，因此已有携带合法请求头的客户端仍可使用。匿名、只有 query token、无效或退出后的请求头返回 HTTP 401。前端 API wrapper 和原 store 调用移除查询凭据；旧 wrapper 调用者即使继续传 token，也不会把它写进 URL。

没有菜单时返回合法的 `menu/auth/allAuth` 数组；首页依据现有权限查询返回，不再无条件插入未分配首页。角色、部门的查询与树形序列化不变；已删除的权限不返回，隐藏子路由、缓存设置及按钮配置语义保留。`allAuth` 仍包含全局非删除按钮的开启/关闭配置，不能把其中每一项当作当前用户已获授权。原 mapper 共享 `/online` 与隐藏的 `/online…:code` 辅助路由规则未改动。

菜单响应添加 `Cache-Control: no-store`。查询失败返回 HTTP 503 和通用提示，服务端保留异常诊断，不再将完整查询 token 写入日志，也不向前端返回数据库异常细节。权限数据恢复后，同一有效会话可重新加载。

## 检查与复现

- 旧候选真实前后对照中的旧行为 **23/23**，新候选专项 **34/34**。覆盖三角色、部门独立分配、隐藏子菜单、按钮开关、混淆查询身份、未登录/无效/退出凭据、空表、权限撤销与恢复、真实数据库查询失败及恢复、日志凭据扫描和数据清理。
- 在相同新 JAR 上串行重跑认证 **7/7**、角色缓存 **11/11**、课程权限 **188/188**，合计 **206/206**；未把旧候选的其他套件计作本候选重跑。
- 前端 **41/41**（既有 39，加 API/store 请求凭据链路 2 项）。新增检查执行实际 API wrapper、GET helper、Axios 0.18 和请求拦截器，只控制网络 adapter；不作为浏览器验收。
- 前后端构建成功。Maven 父 POM 仍跳过 Java 测试，行为检查来自实际 HTTP/数据库脚本。前端仍有 6 个既有 CSS 顺序和资源体积警告，以及过期的 Browserslist 数据提示。
- 两个改动的旧前端文件显式 ESLint 仍未通过：基线 392 errors / 282 warnings，当前 380 / 280，各规则计数没有增加。本 PR 不顺带重排全部旧文件。
- `git diff --check`、Python 编译、自检通过。原工作区 5,634 个源码摘要未变，18091/18101/18111 健康 UP；18102 和 18112 页面 HTTP 200 不代表认证后浏览器流程通过。

准确 JAR、源码与产物摘要及范围见 [candidate.json](evidence/permission-menu/candidate.json)，逐项结果在同目录。

```sh
python3 api/dev/verify-permission-menu.py --runtime /absolute/path/to/course-role-runtime --output /tmp/permission-menu.json
python3 api/dev/verify-auth-status.py --runtime /absolute/path/to/course-role-runtime --output /tmp/auth-status.json
python3 api/dev/verify-role-cache.py --runtime /absolute/path/to/course-role-runtime --output /tmp/role-cache.json
python3 api/dev/verify-course-management.py --runtime /absolute/path/to/course-role-runtime --output /tmp/course-management.json
npm test --prefix web
```

专项脚本先核对本机合成环境、进程、JAR 和数据库/Redis 归属，要求五张菜单/分配表初始为空，拒绝覆盖既有菜单。故障检查临时重命名合成菜单表，让实际查询失败，并在 `finally` 中恢复；不删除业务表。完成后五表全列摘要与原值一致，临时表和记录已清除，会话已退出。只能在独占的合成测试环境执行，不能在生产或其他人同时写入的数据库执行。脚本输出不包含密码或令牌。

## 集成与未完成范围

本项没有产品视觉样式变化。#19 的新登录/会话界面是单独的 Draft，包含有效空菜单的前端处理、加载重试和会话切换保护；本分支的旧 store 尚不接受空数组。最终集成应保留 #19 的处理，移除其直接 Axios 调用中的 `params: { token }`，并使用本 PR 的后端。两个分支尚未完成这一组合，也没有把真实验证码登录、认证后的路由恢复或三角色浏览器流程算作通过。

当前 18111 运行本候选。18112 仍是 #19 的原前端构建，现代理本候选后端；旧 query token 会被忽略，但前端 URL 的移除仍待集成。18102 原公共预览保留。没有迁移数据库结构，没有修改生产或合并 PR。将本 PR 的前端单独用于旧后端会失败，因为旧接口强制要求 query token；更新时应先后端再前端。回退前端仍可连接新后端，回退后端会重新引入旧身份与日志问题。

菜单隐藏不是后端业务授权。本 PR 未审查或修复所有菜单/角色管理的写入接口；部分旧管理注解被注释，是后续需要单独核验的入口。完整后台资源维护、编辑器保存重开、性能、备份恢复与依赖风险仍属于未完成的产品化工作。
