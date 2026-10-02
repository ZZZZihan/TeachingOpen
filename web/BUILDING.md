# 本地前端构建与课程列表验证

本记录对应 2026-10-02 的本地开发版本。已验证的工具为 Node `26.7.0`、npm `11.19.0`；`.nvmrc` 和 `packageManager` 记录这组版本。当前沿用 Vue `2.7.16` 与 Vue CLI `3.12.1`，没有迁移框架。

在 `web/` 目录执行：

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run lint:changed
npm run build
```

- `npm ci` 使用固定锁文件；所有保留依赖都记录官方 npm registry 的下载地址与完整性校验信息。保留依赖的版本没有升级。
- `.npmrc` 的 `legacy-peer-deps=true` 用于保持旧工程的依赖解析方式，不影响其他项目。
- 当前前端构建不需要依赖安装脚本，使用 `--ignore-scripts` 已通过安装和构建。新增依赖后重新核查这一前提。
- 原 `npm run pre` 也改为上述固定锁文件安装命令。
- `npm test` 使用 Node 内置测试运行器，执行课程列表 SFC 的实际方法及实际启动协调代码，32项受控检查覆盖失败重试、分页、响应顺序、15秒启动期限、迟到响应和401/403菜单撤销；它不访问后端，不替代三角色业务验收。
- 上游 `.eslintignore` 忽略整个 `src`。`lint:changed` 显式检查课程页面、Header.vue、main.js及启动辅助模块；默认 `lint` 返回成功不能代表全部源码通过检查。
- Terser 1.x 的磁盘缓存依赖 MD4。生产构建关闭该缓存，以兼容本轮 Node/OpenSSL；压缩仍然启用。

产物在 `dist/`，属于可重建的忽略文件。构建仍会报告其他页面的 CSS 顺序和资源体积警告，详见仓库 `docs/optimization/evidence/build.txt`。

前端构建不需要数据库或后端。需要联调时，可使用：

```sh
npm run serve -- --host 127.0.0.1 --port 8082
```

开发地址为 `http://127.0.0.1:8082`，`/api` 代理仍指向现有配置中的本机 `8081`。该命令是后续联调入口；本轮浏览器验证使用实际生产构建产物与本机合成接口，未启动完整Java后端；启动后端前必须准备独立测试数据库、Redis 和附件目录。不要把代理指向生产服务进行开发写入。

## 变更与恢复

本地分支为 `feature/frontend-course-stability`，上游基线为 `513b05fcddc5da63e0e58c3752cc34ee73252dde`。私有GitHub远端为 `github`，原Gitee远端 `origin` 保留。最新提交与同步状态以 `git log`、`git status -sb` 及 `git ls-remote github refs/heads/main` 为准。

恢复前先保存并审阅当前差异，定位优化提交，再对相应提交执行 `git revert`；不要重置整个工作区或改写已推送历史。构建链恢复会重新引入原先确认的Terser/MD4兼容问题。验证证据及后续发布条件见 `docs/optimization/2026-10-02.md`。
