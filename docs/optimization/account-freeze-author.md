# 账号冻结状态修复作者记录

本次基于 PR54 `c1ab0f80e1179ee4f81c3e1865741bf6a6fc159b`。上一轮主 Agent 与测试 Agent 通过正常管理员 `/sys/user/frozenBatch` 操作，在旧 PR43 和 Shiro 维护候选上均观察到数据库已变为 status=2、已登录学生旧 JWT 仍返回 HTTP200；两次专项均为 5/6，不能计为通过。本次修复这个既有缺陷及同入口的失败、批次与权限契约，不修改 POM、ShiroConfig、前端或其他用户管理入口。

产品只改四个 Java 文件：`SysUserController.frozenBatch` 调用新增的 `ISysUserService.updateUserStatus(String userIds, String status, String operatorId)`；`SysUserServiceImpl` 实现整批事务；`ShiroRealm.checkUserTokenIsEffect` 使用数据库当前状态判定是否可认证。

端点在 try 外显式调用 `subject.checkPermission("user:status")`，对应 UserList 已有的单条、批量操作权限。权限来自现有 ShiroRealm 角色/部门授权查询，不增加 admin 自动全权或 admin-only 限制；不用新注解推断代理是否生效，也不改 Shiro 配置。缺权沿全局异常处理器返回 HTTP200、`success=false/code510`；无效 JWT 沿已有过滤器返回 HTTP401。通过权限门禁后的参数、目标、等级或更新失败返回 HTTP200、`success=false/code500`；只有 service 成功完成才返回 `success=true/code200`，异常响应不包含 SQL 细节。

service 只接受 trim 后的状态字符串 `1`、`2`，兼容 JSON 整数经现有 `getString` 转换。ids 仍是逗号字符串，trim、精确去重、忽略空段以兼容前端尾逗号，整体为空则拒绝；没有新增数组接口。目标行按 ID 排序并 `FOR UPDATE`，整批存在及权限预检完成后才写入。操作人 ID 只来自当前认证 principal；角色等级仍使用 `getUserRoleLevel` 的 MAX(role_level)，沿用“操作人等级小于任一目标则拒绝”的规则，包括原有同等级、自我及无角色时 -1 的语义。整批预检同时保护数据库中精确用户名 `admin`，两个状态均拒绝，沿用现有 UI 规则；不会按 admin 角色泛化这条保护。

已经处于目标状态的行跳过 SQL 更新，重复请求幂等成功。其余目标一次 IN 更新，并核对返回行数；不足或异常抛出并回滚，避免假成功与部分提交。`@Transactional(rollbackFor=Exception.class)` 与成功后的 `@CacheEvict(SYS_USERS_CACHE, allEntries=true)` 沿用现有事务感知 CacheManager，提交后清除用户缓存。同状态成功也清缓存，能够修正已有过期状态。

单次缓存清除本身不解决 cache-aside 迟到回填。Realm 因此先通过已有、未缓存的 `sysUserService.getUserByName(username)` 查询实时存在性与状态：查询已过滤 del_flag=0，缺失或当前状态不是 1 均拒绝；缓存 LoginUser 的旧 status 不再决定放行。其余 profile/password 与 JWT 刷新流程保持。每次 token 校验增加一次现有 `SELECT *` 数据库查询；没有新增缓存版本或跨库事务机制。状态更新成功后开始的认证不会因迟到的旧 status 缓存放行；本改动不撤回此前已完成认证并进入执行的请求，也不宣称全系统请求线性一致。TokenUtils 目前没有产品调用，真实 HTTP、媒体、WebSocket 使用 Realm；不得将其静态共享缓存路径当作已执行的真实验收。

作者仅执行源码核对、构建及包内容比较，没有启动服务、登录、访问数据库、运行浏览器、提交或推送。独立 reviewer 对四文件实际 diff 的静态复核未见阻断；真实权限拒绝、热缓存冻结/解冻、旧状态回填、回滚与缓存提交行为由测试 Agent 和主 Agent 在专用合成环境执行，其结果以各自报告为准，不能由本记录代替。

构建使用既有 Zulu JDK 8.0.504、Maven 3.9.16、项目独立 m2 与 `api/dev/maven-settings.xml`，从该工作树的 api 目录执行：

```sh
JAVA_HOME=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home \
PATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home/bin:$PATH \
/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/apache-maven-3.9.16/bin/mvn \
  -s dev/maven-settings.xml \
  -Dmaven.repo.local=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/m2 \
  -DskipTests clean package
```

本次一次 clean package 退出 0，`BUILD SUCCESS`，8.926 秒；Surefire 明确跳过，不能称 Java 单元测试通过。`git diff --check` 退出 0。原始构建日志与精确清单保存在私有 `.devspace/artifacts/account-freeze-build/clean-package.log`、`final-inventory.json`，不提交原始日志。

最终 JAR SHA256 为 `bca9e5c8f1aa78ab536901e92e2ae3d96433ad0eb4c7599bdaf12174c2c785af`，构建后冻结，不再覆盖打包。包内 209 个 libraries 中，208 个外部依赖与 PR54 冻结 JAR 字节相同，包括 12 个 Shiro 1.13.0、14 个 Spring Framework 5.1.5.RELEASE（含 spring-oxm）、3 个 Tomcat 9.0.122。内部 common JAR 容器字节不同，但解包 111 个 payload 条目逐字节相同，无增删；没有 common 产品变化。BOOT-INF/classes 下 355 个 class 仅上述四个对应 class 改变，均为 major 52；common 另有 107 个 class，合计应用 class 462 个。应用资源没有变化。

冻结源码 SHA256：

- `ShiroRealm.java`：`5a16d5c1a1bb7c0e0202428f7f466655fcd98a5a5b39b6ff0fe25d2ff08deae0`
- `SysUserController.java`：`06d3ad51f539ec58aecdc6d070857042e2384ff77f11051f9ed08d7cee6f6c8a`
- `ISysUserService.java`：`1aa7871fa09c9b99a6234dfbd710e04c3f6de86b9a32a3bdca2fc44de1b807d2`
- `SysUserServiceImpl.java`：`6716cbdbd73ef705177fcc8bf4201dd75920c6ca623d85276d5dc5235bbbb7af`

未变的 POM 为 `6ba0b79046344e99378bb56fe597dd92535ee16abbe8df35f0a8e87c0d038aad`，ShiroConfig 为 `a8cb16f0ba40581dd8d97f7959eef9f41f356a397e779ea65413c504ecded8e0`。本次没有将构建、静态审查或合成接口检查称为浏览器、生产或人工验收。
