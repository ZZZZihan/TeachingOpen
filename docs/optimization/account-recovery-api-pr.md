# 账号恢复后端修复记录

此候选把账号恢复验证码与短信登录/注册隔离，手机号预验证只读取验证码，最终改密在重新核对账号和手机号后单次消费验证码。最终接口只接受 POST JSON；旧 GET 改密没有写入路径。账号恢复同时使旧密码签名的会话在下次认证时失效。

## 原问题与边界

原 `smsmode=2` 与登录、注册都使用裸手机号 Redis key。`phoneVerification` 先读裸手机号 key，再以无 TTL 写回并回显验证码；这会把原 600 秒有效期变成永久。原 GET `passwordChange` 把新密码放在查询参数，检查后没有消费验证码，也没有检查数据库更新结果。原代码已经使用 `username AND phone` 查询绑定，本次保留并加强该绑定，不能把原绑定描述成缺失。

本次修改仅覆盖恢复流程及其必需的会话校验。短信登录/注册 `smsmode=0/1` 保留原有效输入、模板和裸手机号缓存契约。未执行生产操作，未调用短信服务商。

## 前后端契约

| 接口 | 请求 JSON | 本次行为 |
| --- | --- | --- |
| `POST /sys/sms` | `{mobile, smsmode:"2", username}` | 手机号必须为完整大陆手机号，发送前查询用户名与手机号并检查 `status=1`、`delFlag=0`；不可向不匹配号码发送恢复短信 |
| `POST /sys/user/phoneVerification` | `{username, phone, smscode}` | 六位数字验证码；重新核对绑定和账号状态；只验证，无写入、无续期、无验证码回显 |
| `POST /sys/user/passwordChange` | `{username, phone, smscode, password}` | 重新检查绑定、账号状态和密码，再原子消费恢复码，只写密码和盐；返回值检查数据库实际更新结果 |

缺失、`null`、数字、对象或数组字段不转换为凭据字符串。恢复密码要求 8–64 个非空白可打印 ASCII 字符，至少含 ASCII 字母、数字以及原界面特殊符号集合中的一个字符：`~!@#$%^&*()_+`、反引号、`-={}:";'<>?,./`。无需同时包含大写和小写。空格、控制字符和 Unicode 不被接受；现有 `PasswordUtil` 把密码当作 PBE key，不支持非 ASCII，因而先拒绝不兼容输入并检查加密结果非空。

响应沿用 Jeecg `success/code/message/result`。恢复成功、验证成功及失败均不在 `result` 返回验证码、密码、用户资料。常规恢复输入/绑定/验证码失败为 `success=false, code=400`；服务或写入失败为 `code=500`。由于项目异常处理约定，JSON code 不能等同 HTTP status；旧 GET 请求触发既有不支持方法处理，JSON code 为 405，且不执行改密。

以下失败额外返回公开、非敏感的顶层字段 `recoveryState`，供界面作明确判断：

| `recoveryState` | 含义与处理 |
| --- | --- |
| `code_active` | 已有有效验证码或正在发送。保留当前验证码输入，使用已收到的码或稍后重试 |
| `code_consumed` | UPDATE 返回未更新。验证码已消费，重新获取 |
| `reset_unknown` | Redis消费响应或数据库更新抛出异常，结果不确定。重新获取验证码，或尝试新密码登录；不能宣称密码未变或旧码仍可用 |
| `reset_committed` | 数据库已返回更新成功，但后续缓存清理失败。密码已变，响应仍为失败；尝试新密码登录或重新获取验证码 |

这属于契约切换：旧前端缺少发送/验证时的 `username`，旧 GET 改密均无法使用新恢复流程；前后端须配套切换。已经存在的登录/注册裸手机号验证码不能恢复密码，切换时也不迁移旧恢复验证码。新恢复验证码不能用于登录或注册。

## Redis、并发与写入

恢复专用 key 为 `sys:password-reset:code:<userId>:<phone>`。专用 `StringRedisTemplate` 以文本读写 key、value 与 Lua 参数，避免通用 `RedisTemplate` 的 Jackson JSON value 与裸文本 Lua 比较不匹配。未修改通用 Redis 工具或其序列化方式。

发送前用 NX 保存 30 秒 `pending:<随机标识>`，避免同一绑定的并发请求发送不同验证码。服务商成功后 Lua 仅在该预约仍归本请求时把它替换成六位验证码，并设置 600 秒 TTL。预约不属于合法六位码。短信失败撤销本预约；成功发送但保存失败也明确返回失败。验证码到期时间从成功发布计算，预验证不延长它。服务商发送在单元测试中被 mock，真实服务商响应、网络抖动和送达没有验证。

最终改密的 Lua 仅在 value 与提交验证码相等时删除 key。同一码只有一次消费机会；错误码不会删除正确码。消费成功后若写库失败，不恢复验证码，明确要求重新获取。Redis与MySQL并不组成分布式事务，异常时返回上述不确定状态。

数据库使用新建的仅含 `password/salt` 实体，条件同时限制 `id/username/phone/status=1/delFlag=0`，避免把早先读取的整行用户资料覆盖回去，或在手机号/状态已经变更后继续重置。检查 `users.update(...)` 返回值，未更新不报成功。

成功写库后按现有命名清理用户名 token 指针、Shiro 权限缓存和用户信息缓存。此处不同 cache value serializer 不影响删除，因为 key 均为 String。清理异常不报成功，也不把已提交的密码描述成未变。

## 旧会话撤销及限制

原 `ShiroRealm.jwtTokenRefresh` 会把仍在 Redis 中的旧 token 重签；仅改变密码/盐或删除用户信息缓存无法证明旧会话失效。本次在原续签入口前，以每次查询的当前数据库密码核对原 token 的 HS256 签名，并核对用户名 claim。使用数据库凭据，避免陈旧的 `LoginUser` 缓存继续提供旧密码。

签名检查故意不检查过期时间：签名正确但已到期的原 token，在 Redis 会话仍存在时继续使用既有续签机制；Redis 会话不存在时仍拒绝。密码变化后，旧密码签名的 token 即使其 Redis token key 尚存，也不能被重新签为新密码 token。多个旧会话均受该签名屏障约束，无需扫描全库 token。

这只约束后续认证请求，不能追溯取消在重置提交前已经完成认证的在途请求，也不声称物理删除了每一个旧 token key。其它已存在的修改密码入口及使用过期缓存的认证行为同样经过这个必要的签名校验；未更换 token 格式、生命周期或登录接口。

恢复发送取消手机号日志与该路服务商响应日志，恢复异常只返回固定消息，不打印可能包含手机号、模板参数或凭据的异常详情。

## 作者验证

2026-10-05 使用项目固定 JDK 8/Maven 与本机专用 m2 缓存执行 `clean package`，显式运行 `AccountRecoveryServiceTest,AccountRecoverySessionTest`：**30 tests，0 failures，0 errors，0 skipped**。测试包含输入类型、密码兼容边界、完整手机号、无匹配/冻结/删除账号、只读预验证、消费失败不写、只写密码盐及五字段条件、数据库返回 false/异常、缓存失败、短信 mock 预约/发送/发布失败、旧签名拒绝、陈旧用户缓存、缺失 Redis 会话拒绝以及过期合法签名保留续签。

父 POM 原先硬编码 `<skipTests>true</skipTests>`，实际使 `-DskipTests=false` 仍显示 `Tests are skipped`。本次将默认 true 放入同名 property，并由 Surefire 引用，使原默认保持跳过，同时允许显式执行指定测试。不能仅凭默认 `BUILD SUCCESS` 声称测试通过。

复现命令在 `api/` 目录执行：

```sh
TEACHING_TOOLS=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools
TEACHING_JAVA="$TEACHING_TOOLS/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home"
TEACHING_MAVEN="$TEACHING_TOOLS/apache-maven-3.9.16/bin/mvn"
JAVA_HOME="$TEACHING_JAVA" "$TEACHING_MAVEN" -B -s dev/maven-settings.xml \
  -Dmaven.repo.local=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/m2 \
  -DskipTests=false -Dtest=AccountRecoveryServiceTest,AccountRecoverySessionTest \
  -Dsurefire.failIfNoSpecifiedTests=false clean package
```

作者私有证据在项目 `.devspace/artifacts/account-recovery-20261005/api-author/`：`build-final.log`、Surefire XML、`author-build-receipt.json` 和冻结 `teaching-open-account-recovery.jar`。冻结包 SHA-256 为 `67568eeaecea8e8d7342088767eeef2d7fcee45d61afffa0fb559b7808664016`，大小 112462842 bytes；日志和产物不提交 Git。

这是作者单元验证与编译证据，使用 mock 的 SMS/Redis/用户服务，以及真实密码引擎和签名库。作者没有操作本地或生产 runtime。独立 API Agent完成了旧包基线复现，但新版专项矩阵在平台风险检查处中断；不能将其记为新版真实 API 验证。根 Agent 已使用该精确冻结 JAR，在全新合成环境完成常规 HTTP 功能核验 22/22、登录响应 7/7、角色缓存 11/11，报告分别位于私有 `root-functional/functional-02.json`、`auth-status.json`、`role-cache.json`。final02 将错误验证码案例从非法字符改为格式合法、与正确码不同的六位数字，实际覆盖验证码内容比对拒绝；加强后常规 HTTP 核验仍为 22/22。最终脚本 SHA-256 为 `2539eb9a9ee974936fb816fc40a9d6ad708cf502641a4e44048494f1f906d5c8`。功能脚本直接种下合成恢复码，不调用短信服务商；五个原合成账号的完整行已恢复。该证据属于根 Agent 常规功能实测，不能拼接成中断的独立新版矩阵；独立代码审阅及前端验证各自记录。短信实际送达、生产兼容性和用户人工验收仍未证明。
