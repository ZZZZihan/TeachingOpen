# 注册数据库初始化与已有库升级

手机号注册需要 `teaching_registration_profile`、`sys_user.realname/school` 的 utf8mb4 字段、原有唯一索引和唯一学生角色，最后还需要显式开启 `sys_config.allowReg`。应用启动不会执行升级 SQL。

## 空库初始化

确认数据库数据目录为空后，按下列顺序执行发布包内已核验的输入：

1. 基础空结构 `01-schema.sql`，只有 69 张基础表。
2. 发布入口选择的数据 `02-data.sql`，正式包使用经过审阅的正式初始数据；合成候选包独立使用 `02-fixtures.sql`。
3. `03-phone-profile-registration.sql`，执行前置校验，创建注册档案表并改变两个字段的字符集。
4. `04-enable-phone-registration.sql`，再次核验依赖和档案表，按已确认的配置主键开启唯一 `allowReg`。

完成后是 70 张表。SQL 的顺序由文件名和发布清单同时约束。`deploy/candidate_release.py` 仍然只生成 Linux/arm64 的私有合成候选包；它的五账号、两班、三课程和合成媒体不能替代正式初始数据，也不能证明其他平台可运行。

`api/Dockerfile.db` 显式收录了两个升级步骤，但其基础输入保留旧镜像使用的上游 seed，只用于旧构建入口兼容。正式发布组合入口应提供自己冻结的空结构和正式初始数据，不能把该上游 seed 当成正式发布数据。MySQL 官方镜像只在空数据目录执行 `/docker-entrypoint-initdb.d`；重启已有容器、替换镜像或重新复制 SQL 不会升级已有库。

## 已有库显式升级

升级窗口先停止应用、管理后台及其他数据库写入，确认目标数据库和连接，验证外层发布清单和迁移清单，准备足够磁盘空间。先在隔离环境完成同版本备份恢复演练；新备份和连接凭据都留在目标主机的私有目录，禁止加入 Git、共享文档或公开日志。

发布包的 `upgrade/` 包含两个有序 SQL、`registration_upgrade.py` 和 `migration-manifest.json`。外层发布清单必须记录该迁移清单的 SHA256；下面的 `EXPECTED_MIGRATION_SHA256` 指经过审阅的外层清单给出的值，不能从未核验的迁移清单临时重新取一个值当作批准的值。

```text
python3 upgrade/registration_upgrade.py verify \
  --directory upgrade --manifest-sha256 EXPECTED_MIGRATION_SHA256

python3 upgrade/registration_upgrade.py preflight \
  --directory upgrade --manifest-sha256 EXPECTED_MIGRATION_SHA256 \
  --mysql /absolute/mysql --defaults-extra-file /private/mysql-client.cnf \
  --database teachingopen

python3 upgrade/registration_upgrade.py apply \
  --directory upgrade --manifest-sha256 EXPECTED_MIGRATION_SHA256 \
  --mysql /absolute/mysql --mysqldump /absolute/mysqldump \
  --defaults-extra-file /private/mysql-client.cnf --database teachingopen \
  --backup /private/backups/new-registration-before.sql \
  --maintenance-confirmed --restore-check-confirmed
```

连接文件必须是普通文件且权限为 0600，密码通过 `--defaults-extra-file` 读取，不放进命令参数。备份的父目录必须是已有的 0700 私有目录；备份和收据输出都必须不存在。工具不覆盖已有备份，也不修改现有目录权限。`--maintenance-confirmed` 表示已停止所有写入；`--restore-check-confirmed` 表示操作人已验证恢复流程，不能把工具生成了备份文件等同于恢复演练通过。

`preflight` 不改变用户、配置或表结构，但会创建并移除本迁移保留名称的短期存储过程。`apply` 先完成该核查，再用 `mysqldump --single-transaction --routines --events --triggers --hex-blob` 生成当前数据库的新私有备份与摘要收据；只有 dump 成功、文件非空且迁移清单再次核验通过才执行 DDL 和启用开关。备份只包含明确选择的应用数据库，不包含 MySQL 服务器账号和权限；这些仍按现有数据库运维方式备份。工具输出只包含结果、数据库名和摘要，不输出数据库行、密码或原始错误详情。

## 前置拒绝条件与数据保持

脚本支持 MySQL 8.0.16+ 与 MySQL 8.4，要求核心用户、角色、关系及配置表使用 InnoDB。任一条件不满足就中止，不自动补权限、修索引或猜测配置：

- `username`、`phone` 和 `sys_role.role_code` 必须有完整的单列唯一索引。前缀唯一索引、复合唯一索引或普通索引均不接受。
- 只能存在一个规范的 `student` 角色，大小写变体或重复定义均不接受。
- 只能存在一个规范的 `sys_config.config_key='allowReg'` 行，禁用的重复行也算歧义；值只能是精确的 `0` 或 `1`。缺少该行或不可识别的值不自动插入。菜单或字典中的同名文本不会被当成注册开关。
- 姓名和学校列的长度、空值、默认值及排序规则必须与已审阅结构一致；注释只接受规范的一对注释，或正式初始数据受限导出器移除两项注释的已审阅变体。混合或自定义注释拒绝，避免 `MODIFY COLUMN` 覆盖未知列定义。升级会为无注释变体补回规范注释。
- 已有注册档案表必须是兼容的三列 InnoDB 结构、主键和已生效的身份 CHECK，且 CHECK 语义和现有身份值可识别。结构不兼容时保留原表并中止。

两个脚本都不修改旧账号、密码、盐、角色定义或角色关联；姓名和学校改变字符集及上述已审阅注释，不改内容。最终开关只按确认的一行主键更新 `config_value` 和 `config_enabled`，不进行多行更新。重复执行保持原账号及注册资料。

## 失败与回退

MySQL 的 `CREATE TABLE`、`ALTER TABLE`、存储过程 DDL 会隐式提交，不能依靠事务回滚。[MySQL 官方说明](https://dev.mysql.com/doc/refman/8.0/en/implicit-commit.html)明确列出这些边界。开关更新本身使用事务；其事务不能撤销之前的结构升级。

如果 DDL 中途失败，保持写入停止，核对备份收据、当前结构和最后成功的步骤；不能把失败报告当成数据库完全未改变。原始备份、失败产生的部分备份以及收据均保留，不自动删除或猜测回滚。核对后可在兼容状态上重复执行；需要完整回退时，先按已演练方式将备份恢复到隔离或替代库，检查账号和关系一致性，再由操作人执行原数据库的切换。备份选项与权限参考 [MySQL mysqldump 文档](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)。

失败调用可能留下 `teachingopen_registration_schema_v1` 或 `teachingopen_registration_enable_v1` 存储过程。它们是本迁移保留名称，下一次执行同一脚本会替换；成功后移除。脚本的 advisory lock 只串行化迁移，不阻止应用或管理员写入，因此停写仍是外部操作条件。

## 当前验证范围

2026-10-09 在新的原生 MySQL 8.4.6 隔离实例上验证了 schema→合成数据→两步升级、Unicode 写入、已有五账号所有字段/密码盐/角色关联保持、档案数据保持和重复执行。实际生成的备份已恢复到另一个新空库并比对账号及关系摘要。拒绝测试覆盖角色/唯一索引缺失、前缀索引、重复角色或开关、非规范开关值、变更列元数据、错误 CHECK、CHECK 字面量大小写和升级步骤之间新增歧义。原旧档案表及正式受限导出器的双空注释变体均通过兼容测试，混合注释被拒绝。文件测试验证 SQL 摘要、迁移顺序、备份条件和外层清单摘要拒绝篡改。

本次注册升级测试共 27 项：6 项文件/入口契约，21 项明确选入的原生 MySQL 行为测试。另有 70 项合成候选包文件契约测试通过。复现入口为：

```text
REGISTRATION_TEST_RUNTIME=/absolute/.devspace/launch-upgrade-check-1009 \
  python3 -m unittest discover -s deploy -p test_registration_upgrade.py

CANDIDATE_TEST_JAVA_HOME=/absolute/jdk8 \
  python3 -m unittest discover -s deploy -p test_candidate_release.py
```

未设 `REGISTRATION_TEST_RUNTIME` 时原生 MySQL 项明确跳过，不把跳过计为实际数据库验证；测试入口核验实例名称、13449 端口及数据目录，只新建、清除该自检实例中的随机合成测试数据库。

这些是子 Agent 自检结果；主 Agent 的真实初始数据组合、独立验收、生产主机执行、实际 Linux 镜像初始化、其他平台和人工注册验收分别记录，本文不把它们视为已经完成。
