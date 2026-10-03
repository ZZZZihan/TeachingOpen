# 班级成员管理权限：作者实现与冻结构建记录

本次产品改动基于 `fix/class-membership-access` worktree 的 PR #58 提交 `c923ea03a0c5a75cb8f36dee1e90f6587702c0d6`，限定在四个 Java main 文件：`SysDepartController`、`SysUserController`、`ISysUserDepartService`、`SysUserDepartServiceImpl`。作者负责实现、静态自检和 Java 8 构建；root 负责真实 HTTP 对照、数据库故障与并发验证、回归、最终代码审查及 PR。本文没有用构建成功替代接口或数据行为的运行证据。

四个既有成员变更入口都加上 `@RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)`：清空 `/sys/sysDepart/removeAll`，添加 `/sys/user/editSysDepartWithUser`，单删 `/sys/user/deleteUserInDepart`，批删 `/sys/user/deleteUserInDepartBatch`。事务服务的共享检查也要求当前主体是具有 admin 或 dev 角色的 `LoginUser`，在任何成员写入之前拒绝其他角色。权限异常由既有 Shiro 异常处理器输出 `success=false, code=510`，没有给 teacher 新增成员管理权限。

既有 URI、HTTP 方法、参数名和成功响应保持兼容。清空仍为 GET；添加仍为 POST、`depId` 与 `userIdList`；单删/批删仍为 DELETE、`depId` 与 `userId`/`userIds`。清空/单删/批删的成功业务码仍为 200，添加仍沿用旧方法的 `Result<String>` 成功形状与默认业务码 0。旧前端批删在最后一个 ID 后附加逗号，控制器继续使用原有 `split(",")`，因此 `id1,id2,` 可用；列表内部空项、纯空列表、null 用户 ID 会明确失败。重复 ID 在服务内去重，首尾空白规范化后核对真实 ID。

服务在写入前锁定指定部门行，检查部门存在且 `delFlag` 是正常值 `"0"`。用户按 ID 排序锁定，依赖 `SysUser` 的逻辑删除过滤，只接受实际存在且未删除的全部目标用户。部门查询返回的实际 ID 与规范化后的请求 ID 必须 Java 精确相等，用户返回的实际 ID 集合也必须与请求集合精确相等；这避免 MySQL 大小写不敏感比较或其他 collation 等价仅在 SQL 中匹配别名，从而写入不存在的真实 ID 关联。未知部门、逻辑删除部门、未知/逻辑删除用户、非法空项都在成员写入前拒绝。

添加只插入还没有的成员关系，已有关系保持幂等。单删和批删先要求全部目标用户确实属于这个部门，混入其他部门用户或非成员时整批拒绝。单删、批删和清空共享原有角色等级规则：操作者全局角色等级低于任意待移除用户时，抛出权限异常并整批拒绝；等于目标等级仍可操作，与旧单删/批删比较符号一致。清空也应用这个规则，不能成为绕过高等级保护的路径。

成员删除与部门角色清理处于同一个 `@Transactional(rollbackFor = Exception.class)` 事务。清理条件同时限制到本次成员用户 ID 及目标部门的 `sys_depart_role.id`；只删除这些用户在该部门的 `sys_depart_role_user` 关系。账号、全局角色、其他部门成员和其他部门角色不在写入范围，部门自身及其角色定义也保留。删除成员实际行数必须与锁定快照行数一致，否则抛出异常回滚。每次同部门操作先持有该部门行锁，使本次四个入口对同部门的成员变更串行化；这项说明不扩展到未改动的用户编辑、导入或部门角色分配接口。

root 静态审阅发现：如果移除旧删除控制器的宽泛 catch，某些 SQL 故障会直接进入全局 Exception handler，响应可能带入数据库错误和 SQL 细节。最终三个事务方法仅捕获 Spring `DataAccessException`，包装为固定中文 `JeecgBootException(message, cause)` 后继续向外抛出。既有专用异常处理器将固定消息放入响应并保留原始 cause 日志；该异常越过事务代理，保持回滚。权限异常和业务参数异常没有被这个捕获分支吞掉。没有修改全局异常处理器。

清空的边界明确：若某条成员关系对应的用户已逻辑删除或实际不存在，整批拒绝并保持原状。空班级清空幂等成功。只对应孤儿角色关系、未对应本次真实成员的角色关系保持原状；清理遗留孤儿数据需要另项明确处理，避免用这个接口隐式修复未知数据。将清空改为适合写操作的 HTTP 方法也作为另项兼容性改进，本 PR 不改前端调用和现有 GET 契约。

最终构建使用 Zulu `1.8.0_504 / 8.96.0.205-CA-macos-aarch64` 与 Maven `3.9.16`。工具版本保存在 `tool-versions.log`；两份本机工具归档的 SHA-256 再核对与 `api/dev/toolchain.json` 一致，记录见 `tool-archive-hashes.json`。命令在本 worktree 的 `api/` 执行：

```sh
JAVA_HOME=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home \
  /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools/apache-maven-3.9.16/bin/mvn \
  -B -s dev/maven-settings.xml \
  -Dmaven.repo.local=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/m2 \
  clean package -DskipTests
```

开始时间 `2026-10-03T15:58:12.085858+00:00`，完成时间 `2026-10-03T15:58:21.447973+00:00`，退出码 `0`，日志为 `BUILD SUCCESS`。**命令和父 POM 跳过 Java 测试运行，日志两处明确写出 `Tests are skipped.`。作者没有编写或运行测试，没有启动/修改 runtime、操作数据库、浏览器或生产，也没有提交、推送或合并。** 构建前后 1031 项后端 main/test 文件、POM 和 Maven settings 的 SHA-256 清单完全相同，证明冻结包构建期间这些输入未变化。

最终证据目录为 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/class-membership-access/author-build-20261003T155810Z`，包含 `clean-package.log`、工具版本/归档记录、构建前后源清单、`product.diff`、`build-record.json`、`frozen-hashes.json`、四个产品 Java 文件的只读快照 `frozen-product-source/` 与只读冻结 JAR。前两次候选构建目录 `author-build-20261003T154617Z`、`author-build-20261003T155458Z` 保留历史证据；最终矩阵应使用 `author-build-20261003T155810Z` 的包。

| 冻结项 | SHA-256 |
| --- | --- |
| `SysDepartController.java` | `852f9f488c3c7dc4bd1185da40fa3fc003407972612258f284d0f67d5c45117d` |
| `SysUserController.java` | `03765d8321bf4cf9f9194ea1eede4f8aff1b87fdbd8af380d683ba423a1cb955` |
| `ISysUserDepartService.java` | `c7edd821906b243d64bf72f30fdce38add1241c0ff49738e7c11c5ba6a1c91d1` |
| `SysUserDepartServiceImpl.java` | `b7d0d67c129d1a6b4b704a6476b153fdcd032fae50075c66df2e57253166b518` |
| 构建前/后源清单文件 | `4e4e3bc7cb6a6e5a6f264e640904369677302c09994bbfe0f4763aaf624fee2c` |
| product.diff | `8c6d054d30c6113e666997ecc9a5d4c9b771717dadc2b61c5bcc6f0541454d75` |
| clean-package.log | `14b78f4c84dd4c44c0fe0ee32c67e8fd092a9c3adccedb1fdda977be981ba961` |
| teaching-open-class-membership-access.jar | `f03ac420301977cea26e14d9de0bab03f0d8a5c0e7ec92854363ad07347060c0` |

只读冻结 JAR `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/class-membership-access/author-build-20261003T155810Z/teaching-open-class-membership-access.jar` 与 worktree 的构建输出 JAR 摘要一致。接口与数据库行为是否符合预期，由 root 对这个准确冻结包的独立于作者的验证记录说明；本文仅交付作者已完成的实现和构建事实。
