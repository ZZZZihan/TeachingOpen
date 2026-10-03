冻结源码、实际 JAR 的独立静态窄审及最终本地运行证据未发现当前账号冻结变更范围内的阻断。独立测试 Agent 的实际专项为 38/38，root 的七套相关回归为 249/249；本记录分别核对这些证据，不将其合并为 reviewer 独立运行、人工验收或生产验证。审查基线为 c1ab0f80e1179ee4f81c3e1865741bf6a6fc159b，产品提交为 87cf40225057fb043ec76adc21d140eeae2079f0，候选 JAR SHA256 为 bca9e5c8f1aa78ab536901e92e2ae3d96433ad0eb4c7599bdaf12174c2c785af。实际覆盖与剩余限制在下文明确记录。

本次 reviewer 只读基线及候选源码、实际打包字节和其他 Agent 的证据；未启动服务、登录、操作数据库或缓存、运行第二个测试 context，也未修改产品或测试。仅撰写本审查记录。独立重算候选哈希与构建记录一致。与 PR54 冻结包对比，只变化 ShiroRealm、SysUserController、ISysUserService、SysUserServiceImpl 四个应用类，无增删，均为 Java8 major52。209 个嵌入库中全部 208 个外部库逐字相同；唯一变化的内部 base-common JAR 是重新打包，其 111 个解压文件逐字相同，没有隐藏的公共模块改动。实际编译字节中服务方法的事务及缓存失效注解也已核对。root 的 dev-unittest.log 已只读核对 Ran 42 tests 与 OK；42 项工具测试由 root 执行。author 执行 Java8 clean package，Surefire 跳过，不称 Java 单元测试已执行。root 的净化包对照另见 [packaged-diff.json](evidence/account-freeze-state/packaged-diff.json)。

基线问题不只是清缓存遗漏。原 frozenBatch 在循环中逐个验证并马上更新，后续目标不合法可能已经更新前面的用户；异常 catch 后还调用 Result.success，而该方法确实覆盖错误状态。新的 service 接缝整批验证后才写入，异常在事务内抛出；controller 只有 service 正常返回后才返回成功，预期参数错误与内部错误都立即返回失败，内部异常不向客户端拼接 SQL 消息。

授权修正对应现有产品契约。UserList.vue 的单个及批量冻结、解冻都使用 user:status；后端基线没有生效的权限门禁，只比较最高 role_level。角色等级查询无结果返回 -1，因此仅等级比较并不能阻止无冻结权限且等级相同的用户。候选在 frozenBatch 的 try 外显式调用 Subject.checkPermission("user:status")，避免依赖未经实测证明的 controller 注解代理，也不让 AuthorizationException 被业务 catch 包装成一般失败。ShiroRealm 现有授权流程通过 SysUserServiceImpl.getUserPermissionsSet 与 SysPermissionMapper.queryByUser 的角色、部门角色权限取得 perms；它没有按用户名 admin 自动给予所有权限的特殊分支。现有全局异常处理经 Result.noauth 使用 CommonConstant.SC_JEECG_NO_AUTHZ=510，返回业务 code510/successfalse，未显式设置 HTTP 错误状态，实际响应是 HTTP200；不是业务403或HTTP403。

权限门禁之后仍保留角色层次：仅操作者等级小于任一目标等级时拒绝，等等级及普通账户的自我操作仍可通过该层。操作者 ID 只来自当前认证 principal，未从请求正文取值，也没有新增部门范围或 admin-role-only 规则。服务参数仅限状态1/2，ID trim、去重、保留前端尾逗号兼容；整空请求拒绝。目标行按 ID 排序后 FOR UPDATE，整批存在与权限检查完成前不写入；排除已有相同状态的行后统一 IN 更新，并核对实际更新数，不符即抛异常回滚。逻辑删除目标应被实际 MyBatis-Plus 的 TableLogic 条件排除，缺失目标不能悄悄部分成功。

精确用户名 admin 的保护也有现有 UI 依据：前端批量操作遇该用户名拒绝整批，单个操作同样禁止且标有后端校验 TODO。候选在 service 已从数据库读取的目标行上检查精确 username，并在任何写入之前拒绝，冻结和解冻都一致。它不信任请求中的用户名，不扩成禁止所有 admin 角色账户；这是把 UI 已有的目标保护落实到后端，需要在说明中明确，而不能写成后端基线已经实施。

事务和清缓存契约沿用现有配置。RedisConfig 已启用 transactionAware；Spring5.1.5 的实际字节码和固定官方源码确认，TransactionAwareCacheDecorator 对同步中的 clear 注册成功 afterCommit，没有事务时立即执行；CacheAspectSupport 默认 eviction 在目标正常返回后执行。因此 cache advice 位于事务内部时延后至成功提交，位于外部时在成功提交返回后执行。候选的 @Transactional(rollbackFor=Exception.class) 和 @CacheEvict(SYS_USERS_CACHE, allEntries=true) 不要求另改全局 advice 顺序；同状态请求正常返回也会走清缓存。实际专项已确认正常冻结、解冻 HTTP 返回后缓存为空，并确认真实 SQL 中途故障时数据库完整行回滚；这验证了实际调用效果，没有使用模拟代理/context，也没有跟踪 afterCommit 内部时点。清缓存失败发生在提交之后时，不能反向回滚已提交的数据库，不能宣称二者构成跨系统原子事务。依据为[固定 Spring5.1.5 缓存事务实现](https://raw.githubusercontent.com/spring-projects/spring-framework/v5.1.5.RELEASE/spring-context-support/src/main/java/org/springframework/cache/transaction/TransactionAwareCacheDecorator.java)、[固定 cache advice 实现](https://raw.githubusercontent.com/spring-projects/spring-framework/v5.1.5.RELEASE/spring-context/src/main/java/org/springframework/cache/interceptor/CacheAspectSupport.java)及[固定提交实现](https://github.com/spring-projects/spring-framework/blob/v5.1.5.RELEASE/spring-tx/src/main/java/org/springframework/transaction/support/AbstractPlatformTransactionManager.java)。

仅清缓存不能提供返回后新请求的可靠状态门禁：另一个缓存未命中的请求可能先读得旧 status1，冻结提交并清缓存后，它才将旧 LoginUser 写回。这是源码可支持的交错，reviewer 没有把它写成自然并发已实测。候选用最小现有接缝消除缓存状态对该门禁的影响：ShiroRealm 每次认证先通过已有、无 Cacheable 的 sysUserService.getUserByName 查询数据库，并以当前存在性及 status 作检查；该查询包含 del_flag=0。常量 Integer1.equals(currentStatus) 对 null 安全拒绝，缺失和逻辑删除都拒绝。随后才读取 cached LoginUser，cached status 不再参与认证状态判定，因此数据库已解冻时不会被陈旧的缓存 status2 再次阻断。原有 cached password/profile、JWT 刷新和凭据验证保持；不能推广为所有用户属性及权限都已实时一致。

该接缝的明确代价是每次 JWT 认证多一条既有用户名 select * 查询；冻结/不存在的账户在该读取后即拒绝，正常账户仍沿用 profile 缓存。验收边界是正常冻结返回后的新请求被拒绝，不要求追溯中止已经在途且已完成认证的请求。已建立通知 Socket 的证据是下一次心跳重查关闭，不推广为所有长连接都在冻结瞬间关闭。

已逐项核对 [最终专项 38/38](evidence/account-freeze-state/candidate-final.json) 与 [测试记录](account-freeze-tests.md)：正常冻结至 DB2 后旧 JWT 返回 HTTP401，正常解冻至 DB1 后同一仍有效 JWT 恢复；DB2/cache1 拒绝、DB1/cache2 通过，两向受控旧缓存不会改变当前数据库状态门禁。无 user:status 的同等级操作者返回 HTTP200/code510/successfalse，五个合成账户完整行不变。空/非法参数、含缺失或越级目标的批次、精确 admin 两个目标状态均拒绝且完整行不变；合法 trim、去重及尾逗号兼容通过。同状态成功并保持完整行不变。

事务专项经过实际 HTTP、产品 Spring service 和真实 MySQL。专属 BEFORE UPDATE 触发器在第二个目标抛错，非事务记录表的槽位为 [1,2]，确认第一目标更新进入后第二目标才失败；候选返回业务失败 code500、不暴露合成 SQL 细节，五个目标完整行摘要均与调用前相等，包含自动更新的审计字段。finally 的全库原有行及表结构检查通过，仅排除正常新增 sys_log，专属触发器和记录表已删除。这与正常冻结、解冻返回后缓存为空的实际观察共同支持本次修复，没有把源码注解存在直接等同真实事务已生效。

尚未实测的范围保留：数据库身份 status=null、逻辑删除及身份不存在只完成源码检查，不能与请求体/参数 null 或批次缺失目标测试混同；同状态请求未单独观察 cache nil，回滚后缓存保留也未单独观察。两向缓存注入并未复现自然并发 miss 的迟到 put、未提交事务中的命中或并发提交调度。本轮验收的是已提交状态与受控陈旧缓存下的实际新请求行为，没有扩展至原 password/profile 缓存的一致性，也不修改无关用户维护接口或另建缓存框架。

原始失败均保留：[旧包初轮 9/36](evidence/account-freeze-state/baseline-initial.json) 的夹具未恢复 MyBatis 自动审计字段，不能声称该轮全量数据已恢复；改为完整行快照、增加缓存失效观察后，[旧包最终对照为 10/38](evidence/account-freeze-state/baseline-final.json)，旧产品的失败仍按失败记录。[候选初轮 37/38](evidence/account-freeze-state/candidate-initial.json) 唯一红项是无 user:status 的同等级操作者已经被拒绝，但测试预期业务403，实际是既有业务510。此前 reviewer 只追到 Result.noauth，未继续核对常量值而误写403，这是本审查的静态遗漏，现已按 handler、Result 和 constant 三段源码及实际响应更正；不将错误推给产品。最终测试仅纠正权限码判据，并明确检查 successfalse 与完整行不变；四个 Java 与候选 JAR 均未变。旧对照的实际业务码200按正确510判据仍失败，旧10/38不变，但旧对照和最终候选脚本并非完全相同字节版本。

最终 probe SHA256 为 5f887bfc5c576a14a6b7e16fdab2312482391ecb2ff0dafc1c5f432bf21e579f；四份净化 JSON 均重新计算哈希并与 [specialist-manifest.json](evidence/account-freeze-state/specialist-manifest.json) 一致。root 后续只更正测试报告中的构建责任句，当前测试报告 SHA256 为 10173ab0e472aae5cefa58a8d6cfc8de5d41e8628a4f4f54ac7d56ab59a5d981，未改变 probe、四份专项结果或产品。

root 的 [七套相关回归汇总](evidence/account-freeze-state/regression-final-summary.json) 已只读核对，全部指向同一 bca9e5c8… JAR：认证7、角色缓存11、菜单权限34、本地下载88、通知 WebSocket44、Scratch52、令牌日志13，共249/249。最初 Scratch 因临时前端代理未启动连接失败，日志专项因未开启要求的 DEBUG 在守卫处停止；这两项缺少测试前提，没有形成业务通过或失败结论。root 补齐前提后只重跑受影响项，未改产品，原始失败记录保留。净化汇总与私有原件逐字相同。

root 的 [有限旧新成本对照](evidence/account-freeze-state/benchmark-comparison.json) 已只读核对且净化副本与原件逐字相同。旧包首轮20/21涉及首次登录填入 org_code 的夹具初始化断言，原失败保留；[初始化观察](evidence/account-freeze-state/benchmark-initialization.json) 记录仅 sys_log、sys_user 变化。有效旧新脚本均21/21，各384/384计时请求成功。认证路由中位数旧3.546–5.428ms、新5.266–8.302ms；多项 P95 增加，例如四并发 work_detail 的旧6.095ms、新43.106ms。这是共享硬件下单轮 localhost、每次新建 HTTP/1.1 连接的有限观察。旧有效测量是第二次完整脚本、新测量是第一次，JVM/JIT 预热历史不等，root 也记录匿名首页同样变慢；不能将差值全归因新增 SQL，不能作因果性能结论、性能提升或生产容量验收，不为挑好数字再次测量。

本次收束不再执行测试或改动产品。[root 清理记录](evidence/account-freeze-state/cleanup.json) 记录四个临时端口全部停止、DEBUG 配置逐字还原，数据及失败证据保留；这是 root 的记录，reviewer 未控制这些进程。以上支持当前 PR55 的本地工程行为结论，真实师生浏览器、人工验收、生产交付及容量仍分别保留状态。
