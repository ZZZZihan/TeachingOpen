# 生产来源课程的私有本地测试副本

现有合成环境只包含两门构造课程，不能检查真实课程正文、83 个单元的字段组合和真实资源引用。本次增加独立的生产来源副本工具：先在 Python 中解析并处理只读导出，再向全新本机数据库导入脱敏数据，复制已核验的课程素材；原来的五账户合成环境保护保持原样。工具不连接生产服务器，不改生产，不提供生产恢复或迁移功能。

本轮实际副本保留 **69 张表、5 门课程、83 个单元、3 件作品、7 个匿名账户**。课程素材为 **297 个文件、5,941,586,119 字节**；学生作品文件保留匿名引用，文件内容未复制。数据库导入与文件核验成功，不能据此声称真实三角色验收、生产源码等价、迁移交付或任意文本与媒体已全面匿名。

## 范围与隐私处理

全部 69 张原始基础表的定义由导出解析得到，保留生产列类型、默认值、索引、外键和排序规则；仅移除表/列的 `COMMENT` 文本。冻结的 schema profile 来自当前源码，源表缺失、未知表、新增列、列顺序或存储类型变化会拒绝导入，需要另行审阅，不默认保留新字段。

保留课程、单元、开关、正文和课程班级关联；保留用户、角色、班级、作品、评分和必要的字典及内部菜单权限关系。清空公告、审计、短信、微信、任务、外部连接、系统配置、动态表单代码、Scratch 素材目录等不属于本次课程对照的数据表。Scratch 编辑器完整素材功能、消息、评分评论、外部服务和学生作品文件没有在本交付中验收。

- 用户 ID、用户名和姓名统一映射为 `snapshot_user_NNN`；联系方式、头像、生日、性别、第三方身份、学号、岗位、学校和电话清除。旧密码与盐不导入，使用源码 `PasswordUtil` 和新建环境中的随机测试口令重新生成凭据。
- 班级/学校 ID、父关系和标签匿名映射；地址、电话、传真、备注和自由描述清除。所有保留表的 `create_by/update_by` 按同一账户映射处理，历史未知操作者另以 `snapshot_actor_NNN` 编号。
- 角色代码、权限代码、组件路径、业务 ID 与课程/单元/作品关联键保留。没有按用户名全局做子串替换，避免源账号叫 `admin` 或短数字时损坏角色语义或关联键。实际四个角色代码 `admin/dev/teacher/student` 已核对保留。
- 作品名与反馈文本使用测试标签。与作品关联的 5 个文件记录改为 `snapshot-withheld/` 下的匿名路径，未复制原学生文件。课程中引用的教学模板属于课程素材复制范围。

源数据已有 **7 个不同的悬空部门 ID、5 个不同的悬空用户 ID**。副本为它们分别分配 `snapshot_missing_dept_NNN` 和 `snapshot_missing_user_NNN`，保留引用相等及悬空事实，不补造用户或班级记录。源中现存部门记录只有 1 条；课程授权到旧班级的行为需作为兼容性限制理解。

保留的课程正文/资源字段中有 **11 次已知身份字符串匹配**，因此本副本与素材始终作为权限 700/600 的本机私有资料。检测计数不会证明不存在其他身份信息；真实正文、截图、原素材名、原始 dump、用户口令和私有清单均不纳入 Git 或公开 PR。

## 导入与资产边界

工具接受本轮实际 `mysqldump` 格式中的完整 `CREATE TABLE` 和仅标量的 `INSERT ... VALUES`。解析器正确处理单引号、双写引号、反斜杠、Unicode、多行字符串、NULL、数值和 `0x` 二进制。源会话设置和锁语句仅识别后丢弃；不会执行原导出的 SQL。`USE`、`CREATE DATABASE`、`GRANT`、跨库标识、视图/触发器/存储过程/事件、客户端命令、`LOAD DATA`、`OUTFILE` 和 INSERT 表达式均拒绝。

已处理数据通过生成的 UTF-8 十六进制字符串/二进制字面量运输，避免正文成为 SQL 或客户端命令。导入客户端启用 `--binary-mode --local-infile=0`，服务器关闭 `LOCAL INFILE`。导入用户 `teaching_dev@127.0.0.1` 只有新建 `teachingopen_dev.*` 的明确权限，没有全局权限、FILE 权限或 GRANT OPTION。root 客户端只用于可信的本地环境准备与用户权限设置，不接收生产 SQL。

目标必须是 `.devspace/` 的全新、无符号链接直接子目录，四个端口必须互不相同且空闲。工具沿用已核验的 portable MySQL/Redis/JDK/Maven，调用 `prepare(seed_fixtures=False)` 初始化，不修改既有环境或原始来源目录。中途失败会保留新目录和本任务服务供私有诊断，不自动删除其他资产或启动后端。

课程、单元、附加作业资源字段以及正文中的 URL 属性生成私有相对路径清单。297 条路径全部存在于已校验的源资产清单；复制前后核对每个文件的 SHA-256，拒绝绝对路径、`..`、编码穿越、任何符号链接组件或非普通文件。副本使用独立文件，不共享可写硬链接。

已确认属于源清单的应用 static URL 可转为本地引用：普通文件字段保持相对路径，以适配现有 `getFileAccessHttpUrl`；HTML 属性使用 `/api/sys/common/static/`，并保留其他正文。JSON 中已转义 URL 也有受控用例。本轮真实数据没有需要此转换的应用 static 绝对 URL，转换数量为 0；2 条其他外链保留为未验证内容。预览应使用现有 `serve-frontend.py` 的 CSP，阻止自动外网资源读取。资产复制和数据库事务快照不是跨资源原子快照，清单明确记录这一点。

## 实际操作与复现

以下变量指向本轮本机私有目录；重新创建时必须使用一个不存在的新运行目录，不覆盖已展示的副本。

```sh
TEACHING_REPO=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/production-data-fixture
TEACHING_SOURCE=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/production-source-20261003
TEACHING_RUNTIME=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/prod-fixture-1003
TEACHING_TOOLS=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/backend-runtime/tools

cd "$TEACHING_REPO"
python3 api/dev/production-fixture.py create --source "$TEACHING_SOURCE" \
  --runtime "$TEACHING_RUNTIME" --tools "$TEACHING_TOOLS" \
  --mysql-port 13346 --redis-port 16419 --backend-port 18141 --frontend-port 18142

# 仅在首次启动应用之前检查完整初始基线：
python3 api/dev/production-fixture.py verify --runtime "$TEACHING_RUNTIME"
```

本轮源 dump 为 2,167,779 字节，SHA-256 为 `54b7bc48c80dfafd405bf0907502fb46c3de90ee50bc25540e7fe0f547a6435c`；仅此来源摘要可在公开记录引用。独立 `snapshot-manifest.json` 绑定源 dump/获取清单摘要、schema policy、目标 datadir/端口、配置/凭据文件摘要、脱敏数据库逐行摘要和结果。初次清单 SHA-256 为 `bb4380486c95f6ddd2aa8b362ffed6213e2614485a090e27f4c82ef825cdc100`。这些 SHA-256 用于检测变化，不是来源签名或加密。

运行目录中的 `snapshot-accounts.json`、`resource-references.json`、`assets-result.json`、`schema-comparison.json`、`sanitized.sql`、`config/credentials.json` 都是私有诊断/复现材料。口令不出现在命令参数、输出或报告中。

专用启动入口要求明确 JAR 路径及 SHA-256，并在进程创建前执行上述完整验证；原 `run-backend.py` 和 `FixtureApi` 的固定五账户保护仍会拒绝这个副本。

```sh
TEACHING_JAVA="$TEACHING_TOOLS/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home"
TEACHING_JAR=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/course-update-outcome/api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar
TEACHING_JAR_SHA=c2898fa71e75294fe03bc1401388a7c50126c2964030c3739dd949c840a9a364

python3 api/dev/run-production-fixture.py start --runtime "$TEACHING_RUNTIME" \
  --java-home "$TEACHING_JAVA" --jar "$TEACHING_JAR" --jar-sha256 "$TEACHING_JAR_SHA"
python3 api/dev/run-production-fixture.py stop --runtime "$TEACHING_RUNTIME"
```

启动成功返回 PID 只表示派生进程，健康 `UP` 和业务读取需单独检查。私有进程记录保存完整 JAR/配置/profile、`ps` 启动时间及命令和初始清单摘要；停止只匹配本任务进程身份，发送 SIGTERM 并等待退出，不因正常 Quartz/审计/业务变化比较全库摘要。

完整 `verify` 表示“仍等于初始脱敏基线”。应用启动后的 Quartz、审计和查看计数可能改变库，因此运行期检查应使用专用的轻量归属/配置/匿名账户守卫；不要把完整初始摘要不相等误报为服务失效，也不要为了重启删除真实运行记录。本版再次启动仍要求完整初始基线，运行过的副本可能需明确核查或另建副本后再启动，不自动重置或重新封装它。

## 验证结果和结构差异

工具作者实际执行 `create` 和完整 `verify`，导入 69 张表及上述课程/单元/作品/账户，数据库计数与已处理数据一致；素材复制摘要相等。root 随后独立运行 `verify` 通过，审阅范围/私有文本边界后，由 root 启动指定 JAR 与候选前端，并确认后端健康 `UP`。本记录不将 root 的启动核查称为用户人工验收；匿名只读 API 与浏览器内容核验由独立脚本及其记录交付。

```sh
python3 -m unittest discover -s api/dev -p 'test_production_fixture.py' -v
TEACHING_SNAPSHOT_TEST_RUNTIME="$TEACHING_RUNTIME" \
  python3 -m unittest discover -s api/dev -p 'test_production_fixture.py' -v
python3 -m unittest discover -s api/dev -p 'test_*.py'
```

专用 MySQL 测试仅可在应用启动前的独占新副本执行，会创建自己的临时探针表、验证文本/二进制 HEX 往返、删除该表并再核对完整基线，不与业务/API 检查并行。实际先完成包含该往返用例的 16 项测试，全部通过；后加的 6 项启动/停止守卫测试通过。冻结后默认工具测试 22 项中 21 项通过、真实 MySQL 项按约定跳过；`api/dev` 全集 64 项中 63 项通过、1 项同样跳过。没有在应用运行后再次建表测试。

可提交的 [安全测试证据](evidence/production-data-fixture/README.md) 保存后续默认纯测试重跑的完整输出、命令、时间、退出码与摘要。原 16 项真实 MySQL 执行只在会话工具结果中，没有落盘原始日志；证据目录如实记为历史执行记录，不把它重建成原始输出，也没有为补日志重跑运行中的数据库。

真实源定义和当前 `api/db/teachingopen2.8.sql` 的表名、列名/顺序和归一化存储类型签名均相同；这不表示完整定义或生产行为相同。私有结构对照记录发现：

- 544 列的显式字符集/排序规则标注不同，主要包括 `utf8` 与 `utf8mb3` 命名、显式列标注和继承表默认值的导出差异；不把 544 处都宣称为语义差异。
- `sys_check_rule`、`sys_data_source`、`sys_fill_rule` 三表的默认排序规则在源中为 `utf8mb4_0900_ai_ci`，源码为 `utf8mb4_general_ci`。两者相等/排序行为未在本交付中全面验证，导入保持源定义。
- `teaching_depart_day_log.depart_id` 的默认值声明存在差异；源为 NOT NULL 且无默认值，源码声明空字符串默认值。本工具保持源定义，没有补迁移。
- 五张 Quartz 表的导出省略了源码中显式的 `ON DELETE RESTRICT ON UPDATE RESTRICT` 外键条款；列/关联目标保留。原始定义语法不同不等于已经证明功能差异。

尚待的范围包括任意自由文本/媒体的全面匿名审查、登录与三角色业务检查、原班级悬空授权行为、编辑器/视频/文档的用户操作验收、生产定制源码等价和部署。原始副本、素材和数据库都不随代码 PR 发布。


## root 最终审查与实际使用

工具产品提交 `2f385d4`，基于 #43 `3fb70f1`。工具实现与默认测试由 `production_fixture` 子 Agent完成；`admin_ui` 子 Agent另外做只读代码审查，未发现阻断当前首次启动的问题。root复核脱敏范围、角色/ID保留、配置及PID所有权后，独立执行初始verify并启动后端18141/PID1792；`/api/actuator/health` 返回HTTP200/UP。前端18142/PID1867提供新组合 `91cdbe4` 构建。三位子Agent按用户指定 GPT-6.1-sol / Ultra；没有可设置的Fast参数。

`admin_tests` 子Agent随后用匿名HTTP和只读SQL完成 **12/12** 实际副本检查：公开3门课程的ID及标记逐项与SQL一致；页码/每页数量、越界空页、名称/性质/分类筛选一致；匿名课程/单元管理接口仍401；3份首页封面通过实际同源HTTP读取，其字节摘要与独立本地文件及来源清单一致。7张选定教学业务表在检查前后行数/逐行摘要不变。记录中的10次JSON接口请求与3次封面GET分别计量，不将数据对照称作登录后业务验收。

首轮错误地假定del_flag必须为0，但源中3门公开课程均为NULL；保留失败后依据真实getHomeCourse的show_home=1契约修正断言，并逐项核对返回标记。第二轮部分执行因参考分类/性质的字符串数字类型处理不足停止；修正检查器后完整通过。源中没有公开且del_flag非零的样本，不能据本次数据宣称接口会过滤全部删除态课程。

root另使用Playwright CLI打开真实副本首页和课程目录，1440/768/390视口均无横向溢出，5张页面图片无破图，一个真实课程介绍弹窗正常打开、手机按钮可见。历史外部统计脚本被本机CSP阻止，是已知console错误，不记为无错误页面。真实内容截图、DOM仅留在私有runtime，Git只保留聚合观察 `anonymous-browser.json`。

真实内容发现两个相关UI问题：摘要显示HTML实体文本；旧Autoprefixer移除box-orient导致三行摘要展开全文。修复在独立 `fix/course-summary-text` 分支进行，不混入本PR。没有修改源生产数据或把长期目标标记完成。

启动工具继承调用shell环境；本次独立审查确认相关Spring/JVM覆盖变量未设置。其他shell重用时仍应核对环境，当前工具不是恶意宿主隔离沙箱。`stop`仅停止本副本后端，MySQL/Redis另由隔离环境管理。本PR不证明启动后任意变更均可重新通过初始baseline，也不声称三角色/视频/编辑器/完整迁移已验收。
