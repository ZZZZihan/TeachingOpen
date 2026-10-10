> 历史方案：本 PR 的免手机号注册已由 #82 手机号、姓名、学校和身份注册替代。2026-10-10 汇总历史分支时仅保留本记录及证据；当前实现与测试以 AccountRegistrationService 和手机号注册流程为准。

# 账号注册（不填写手机号）

登录页开启注册后，用户填写账号、姓名、密码和确认密码即可注册。成功页展示账号，跳转登录时只预填账号。注册页面不收集手机号或短信验证码，注册服务不调用短信供应商、不依赖注册验证码 Redis key。

## 接口及配置

`POST /sys/user/register` 接受 JSON 中的 `username`、`realname`、`password` 三个字符串。账号为 4–32 位英文字母、数字或下划线；姓名为 100 字以内非空文本；密码为 8–64 位可打印 ASCII，包含字母、数字和现有密码规则认可的特殊符号。确认密码仅在前端检查。成功返回 `result: {"username": "..."}`。

服务端重新检查 `allowReg=1`。未开启时页面显示联系教师或管理员的提示，接口拒绝创建账号。`_defaultRole`、`_defaultDepart` 沿用后台配置：空值表示不分配，不为空则逐项验证并去重；禁止默认 admin/dev 角色，拒绝不存在、已删除或停用的班级。账号、默认角色和班级在一个事务中保存，任一关系保存失败即全部回滚。

客户端提交的 id、角色、班级、状态、身份、手机号、短信码和邮箱等额外字段均不绑定到新用户。手机号保持数据库 NULL，既有唯一索引允许多个 NULL，无需表结构变更。注册失败保留表单以便重试，成功或页面销毁时清除密码。路由、错误提示和注册结果不携带密码。该账号使用账号密码登录；注册本身不会绑定手机号供短信登录或找回密码使用。

## 验证范围及前置条件

分支基于 PR #70（`fix/account-recovery-ui`），保留现有登录页和天工公共布局。本 PR 只包含注册实现及针对性验证。PR #70 仍未合并，需要按现有分支链集成。

该分支继承的旧 Oracle Maven 坐标本身无法解析，已由 PR #2 修正。为验证本 PR Java 源码，在隔离源码副本中仅叠加 PR #2 的 Oracle 坐标；完整 Maven package 和 RegistrationServiceTest 均通过。未把 Oracle 修复混入本 PR。另一个运行环境基于 PR #69（`fix/account-recovery-api`）的后端前置链叠加本注册修改，使用本机独立端口、合成 MySQL/Redis 和附件目录进行真实 HTTP 与浏览器验证。组合运行结果不等于该分支单独部署验收。

- 前端 `npm test`：593/593（新增注册测试 9 项）；构建及 4 个修改文件的显式 ESLint 检查通过。
- 后端 `RegistrationServiceTest`：10/10，0 跳过；上述两个隔离构建上下文均通过完整 package。
- 真实 HTTP/SQL：29/29，结果见 [http-no-phone.json](evidence/account-registration/http-no-phone.json)。覆盖关闭注册、非法输入、越权字段隔离、默认配置、无手机号注册及登录、NULL 唯一索引、多线程同名冲突、角色/班级写入故障回滚及重试。结束时逐字段核对四张测试表恢复原状。
- 浏览器：使用最终构建，在 390px 和 1440px 检查字段及横向溢出；实际执行无手机号注册、成功页、预填账号登录，并使用新密码和服务端 CAPTCHA 登录；另检查关闭注册状态。证据及来源见 [summary.json](evidence/account-registration/summary.json)。

本地代理通过 CSP 阻止遗留远程 telemetry 脚本，控制台因此有一条拦截记录；注册组件未出现额外异常。验证均为工程自检和本机合成数据，不代表人工验收或生产交付。生产配置、部署及数据未修改，没有合并 PR。

## 复现

前端在 `web` 目录执行：

```sh
npm test
npm run build
./node_modules/.bin/eslint --no-ignore src/views/user/Register.vue src/views/user/RegisterResult.vue src/api/registration.js src/utils/registration.js
```

后端需先集成已有 PR #2 驱动坐标，或在隔离副本叠加该坐标；使用 Java 8 和项目 Maven 配置执行：

```sh
mvn -DskipTests=false -Dtest=RegistrationServiceTest -Dsurefire.failIfNoSpecifiedTests=false package
```

真实接口脚本依赖 PR #4 的 `api/dev` 隔离运行辅助代码。先创建只有五个 fixture 账号、无注册配置和触发器的专用 `.devspace/registration-*` 环境，并启动明确的候选 JAR，然后运行：

```sh
python3 api/dev/verify-registration.py --runtime /absolute/.devspace/registration-example --jar /absolute/candidate/teaching-open-2.8.0.jar --support /absolute/integrated/api/dev --output /absolute/fresh-report.json
```

脚本拒绝非专用路径、已有输出文件、非预期数据库、非明确候选进程及非测试用 Redis。不包含短信发送或生产访问步骤。
