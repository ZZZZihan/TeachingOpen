# 用户名注册与登录

学生或教师打开各自注册入口，填写用户名、密码、姓名和学校，注册成功后使用该用户名登录。注册不再采集手机号。成功页显示刚注册的用户名，并在进入登录页时自动填入；不传递或保存明文密码。

用户名沿用现有账号体系的 3–100 位规则，允许英文字母、数字、下划线、`@`、点和短横线，提交时去掉首尾空白。服务端和页面共同校验；用户名与已有用户名、已有手机号、已删除账号占位冲突时拒绝。数据库原有唯一索引继续处理并发重复。姓名、学校及密码要求保持原有契约，两个入口仍仅授予基础学生角色，教师资料身份不等于教学管理权限。

旧手机号注册账号的用户名、密码和盐均不修改，因此仍能输入原手机号和密码登录；不新增任意手机号别名登录能力。新注册账号 `phone=NULL`，无数据库结构迁移。发布后仍开着旧注册页的客户端若只提交 `phone`，会收到明确提示，刷新后填写用户名即可。未绑定手机号的新账号无法使用现有短信找回密码流程，忘记密码沿用管理员重置方式；本轮不新增另一套找回机制。

验收覆盖填写与格式拒绝、注册成功、成功页到登录的用户名传递、真实密码/图形验证码登录、同入口与跨入口重名、网络失败后保留输入并重试、并发去重、事务回滚、拒绝后数据状态和原手机号账号兼容。最终实现基于 `fe96225c4a77b24787a5187984c07118d9e45d0a`；[证据摘要](evidence/username-registration-20261015/summary.json)绑定改动文件 SHA-256 与实际 JAR。所有写入检查均使用全新本机合成数据库及独立 Redis DB3。

本地已实际完成：

- 前端 865 项测试、变更产品文件 ESLint、生产构建、依赖门禁与初始资源预算检查通过。
- Java 干净构建，40 套必需测试共 377 项通过；CI 工具契约 47 项通过。
- [真实 HTTP/SQL 检查](evidence/username-registration-20261015/http-registration.json) 186/186，包括 3 位、100 位混合大小写及纯数字用户名，旧账号登录，失败前后 10 张业务表摘要及角色边界。
- 完整生产构建 SPA 与真实接口：学生、教师均完成注册、成功页、用户名预填、真实图形验证码与密码登录、首页显示相应合成用户。学生路径验证无效用户名不发请求和网络故障重试；教师路径验证跨入口重名后保留输入，修改用户名后成功。
- 两个注册入口均检查 390px 和 1440px，无横向溢出，学校字段到按钮保持至少 24px 间距。
- [独立技术复核](evidence/username-registration-20261015/independent-review.json)未发现阻断，另行执行相关前端 55 项、字符边界 138 项及最终 ESLint；[只读持久化检查](evidence/username-registration-20261015/account-persistence.json) 16/16，七个新合成账号均无手机号、资料身份正确且只有基础角色。

首次变更文件 lint 检出一个多余正则转义，修复后重新执行前端全量测试、lint 和构建。原始失败记录保留在任务本机证据目录。浏览器存在既有远程统计脚本被 CSP 拒绝的记录；学生网络故障由测试主动注入，随后真实重试成功。这些记录没有被删除或当作成功请求。

测试结束保留七个合成账号及私有日志；旧手机号测试夹具已清理，正常认证审计保留。本轮没有生产连接、合并或部署，人工体验验收仍独立于技术检查。GitHub CI 状态以本 PR 的检查页为准。

界面证据：

- [修改前：用户提供的注册页](evidence/username-registration-20261015/before-user-screenshot.png)
- [学生 390px](evidence/username-registration-20261015/student-390.png) · [学生 1440px](evidence/username-registration-20261015/student-1440.png)
- [教师 390px](evidence/username-registration-20261015/teacher-390.png) · [教师 1440px](evidence/username-registration-20261015/teacher-1440.png)
- [学生成功页](evidence/username-registration-20261015/student-success-390.png) · [学生登录后](evidence/username-registration-20261015/student-logged-in-390.png)
- [教师成功页](evidence/username-registration-20261015/teacher-success-1440.png) · [教师登录后](evidence/username-registration-20261015/teacher-logged-in-1440.png)
- [网络失败保留输入](evidence/username-registration-20261015/student-network-error-390.png) · [重名保留输入](evidence/username-registration-20261015/teacher-duplicate-1440.png)
