# 可重复的三角色真实界面夹具

root 实测状态（2026-10-03）：专用初始环境 create/verify 成功，69表116行、5账号、10附件；真实后端 API 预检22/22。分支全部开发工具78通过/1跳过，前端 HTTP/dist 字节4项相同。独立审查无本轮阻断。正常浏览器登录、视频播放和三编辑器整链路仍未验收。以下作者准备记录与文末 root 实测分开阅读。

标准 `seed-fixtures.py` 为接口回归准备五个合成账号，但不注册后台菜单、班级类别为 2、视频与编辑器模板不能用于真实媒体验收。此工具在**全新专用环境**追加真实权限菜单、类别 3 班级、机构编码规则、字典、有效课程素材，使已有学生、教师和管理员界面能够沿现有路由与 API 运行。工具本身不启动应用、不做登录，也不把夹具生成当成真实浏览器验收。

## 接口与依赖

需要 Python 3.9+、项目已验证的本地 MySQL 8.4 客户端，以及由现有 `prepare-local.py` 标准初始化的五账号环境。工具不额外安装库、不下载媒体，不依赖本工作树的 JAR 或 `web/dist`。初始化仍需 `prepare-local.py` 所在工作树已构建的密码辅助类；前后端应由候选组合提供并记录各自提交/JAR/dist 摘要。

本轮 root 已另建的专用环境为 `.devspace/role-flow-1003`，端口 MySQL 13350、Redis 16423、后端 18149、前端 18150。**本夹具 Agent 未访问这个环境或运行任何数据库/服务命令。** 下列命令由 root 在审查后执行，`role-flow-fixture` 仅提供工具与素材：

```sh
cd /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/role-flow-fixture
python3 api/dev/seed-role-flows.py create --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/role-flow-1003
python3 api/dev/seed-role-flows.py verify --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/role-flow-1003
```

`create` 仅接受私有、非符号链接、直属本机 `.devspace` 的 `role-flow-*` 环境；需要原五个确切账号及对应角色/部门/课程/作品全部字段与标准种子相符、69 表列类型/默认值相符、其他表为空、上传目录仅包含原两个文本附件。原私有种子文件通过引号感知解析器读取标量 `INSERT` 作对照，**不执行其中 SQL**；表达式、越界语句、未知表/行/列均拒绝。验证还要求本机实际 MySQL datadir/端口、完全匹配隔离模板的配置、前后端端口关闭且不存在应用启动记录。

写入只由固定合成记录生成，经十六进制传输文本，在事务内更新两个班级类别并插入新记录。执行用户为 `teaching_dev@127.0.0.1`，先检查权限仅限 `teachingopen_dev.*`，禁用 LOCAL INFILE，口令只存于私有客户端文件。工具先写独占开始标记，已有成功/失败/中断目标一律拒绝再次创建；失败时保留不完整环境供核查，不自动清除或覆盖。应另建环境重试。

成功后的 `role-flow-manifest.json` 为私有文件，绑定工具/源码/schema 摘要、runtime/datadir/端口、完整初始数据库与附件摘要。`verify` 是**首次启动前的严格初始验收**。浏览器操作、登录日志、学习记录或 Quartz 运行行都会改变初始快照；此后不要用它判断应用健康或阻止停止。正常 start/stop 继续使用既有运行工具与进程归属检查，五账号默认保护不变。界面验收不得新增第六个账号；用户维护采用编辑现有合成学生并重开核对。

## 新数据与真实路由

保留原五账号、三角色代码、账号班级关系、两门原课程/单元、两份原作品与附件。仅在专用环境将 `fixture_class_a/b.org_category` 从 2 改为 3；学校类别仍为 1。班级创建规则为 `org_num_role` → `org.jeecg.modules.system.rule.OrgCodeRule`，`rule_params={}`，由表单真实 parentId 决定组织编码。

增加 1 门 `fixture_ui_course`（名称“三角色编程实践（自制夹具）”），只分配给班 a；3 单元 `fixture_ui_unit_sb3/sjr/py` 使用真实类型 2/3/4、相同本地 10 秒视频与富文本说明。视频、案例、学习资料向学生显示，教师教案不向学生显示。增加 1 个已发布的班 a 文件任务 `fixture_ui_task`，不预造学生提交或教师反馈。素材共 8 份，来源及原始字节摘要见 `api/dev/role-flow-assets/README.md`；素材无生产原文或外部资源引用。

菜单通过 `sys_permission → sys_role_permission → 原 sys_user_role` 真实授权，前端照常从 `/sys/permission/getUserPermissionByToken` 注册动态路由；没有修改前端路由或权限逻辑。

| 角色 | 入口/组件 | 用途 |
| --- | --- | --- |
| 三角色 | `/account/center` → `account/center/Index`；`/account/mineWork` → `account/center/MineWorkList` | 个人作品、重开 |
| 三角色 | `/teaching/mineCourse/cardList` → `account/course/CourseListCard`；隐藏 `/teaching/mineCourse/courseUnitCard` → `account/course/CourseUnitListCard` | 真实课程与单元入口，数据范围仍由后端控制 |
| 学生 | `/center/myAdditionalWork` → `account/course/MyAdditionalWorkList` | 班级文件任务、提交状态、直接显示反馈 |
| 教师/管理员 | `/teaching/workList` → `teaching/TeachingWorkList`；`/work/additionalWork` → `teaching/TeachingAdditionalWorkList` | 学生作业批改、发布任务 |
| 管理员 | `/course/course` → `teaching/TeachingCourseList`；`/course/courseUnit` → `teaching/TeachingCourseUnitList` | 课程/单元维护 |
| 管理员 | `/isystem/departDetailList` → `system/DepartList`；`/isystem/user` → `system/UserList` | 班级/原合成用户维护 |

管理员另有真实 `user:edit`、`user:status` 按钮权限。本轮用户维护仅覆盖编辑既有合成用户，未授予 `user:add`，不覆盖新增用户。字典包含 `work_type`、`work_status`、`course_type`、`course_category`、`additional_work_status`、`activiti_sync`、`sex`、`user_status` 和 `yn`，只提供本流程实际所需取值，不导入 upstream INSERT 配置或账户。`work_status` 采用当前界面与接口的 0 草稿、1 已提交、2 已批改、3 公开展示、4 精选。学生没有管理菜单，教师没有用户/课程维护菜单；菜单隐藏并不替代后端授权验证。

## 人能执行的最小完整顺序

口令由自动化从本 runtime 私有文件读取或由 root 向操作者提供，不写文档/日志。沿普通 `/user/login` 页面输入账号、口令和人可见验证码；浏览器验证码操作仍等待用户确认。未获确认前不做浏览器验证码填写，不通过注入令牌绕过浏览器登录；既有隔离合成 `FixtureApi` 测试继续按其已授权流程执行，包括读取其自身 Redis 验证码，但这种独立 API 测试不计作真实浏览器验收。

1. **管理员 `fixture_admin`：真实维护入口。** 从实际菜单进入班级管理，选学校检查班 a/b 为“班级”，编辑班 a 名称/备注，保存、关闭重开确认。可在学校下新增一个不分配用户的合成班级，验证编码规则及类别 3；记录新班 ID。到用户管理编辑 `fixture_student_a` 的显示名，保留学生角色与班 a，保存并重开确认，最终恢复原显示名。用户数保持五个。切到课程包管理打开新 UI 课程、修改描述并重开，再到课程单元管理修改一个单元的正文/资源开关并重开，最后恢复学生可见的视频/资料。若需要覆盖“创建”而不只是“维护”，使用新测试名称创建课程、单元并上传本工具的自制素材，再到班级“课程”页添加已有课程；不要把固定预置课程称为浏览器创建成功。

2. **学生 `fixture_student_a`：真实学习入口。** 登录后从“探索课程”(`/courseList`) 和“我的课程”分别找到“三角色编程实践（自制夹具）”，打开课程卡片/单元。阅读富文本，打开真实 10 秒视频：等待 metadata、播放，确认 currentTime 增加；拖动到约 7 秒，确认 seek 后能继续播放。读取本地学习资料；学生应看不到教师教案。仅下载成功不等于媒体播放成功。

3. **学生：Scratch 与 ScratchJr 保存/重开/提交。** 对两个单元分别点“开始练习”，使用原编辑器按钮实际改项目。Scratch 可移动圆形角色并增加绿旗事件/移动积木；ScratchJr 可加文字或角色/积木。为本次作品使用独特测试名。点“保存草稿”，记录返回的 workId/文件摘要，关闭页面，从“我的作品”编辑同一作品，确认实际改动存在、类型和单元关系正确；然后点“提交作业”，连续点按钮的检查不应产生第二份作品。刷新列表确认状态。不要对原 `fixture_work_a/b` 的文本附件做编辑器格式验收。

4. **学生：Python 按实际按钮保存与重开。** 从 Python 单元开始，修改为会输出明确标记和 `42` 的代码，执行确认输出。当前 `web/public/python/persistence.js` 的课程保存提交 `workStatus=1`，没有独立草稿动作：记录首次保存/提交 ID，关闭，从“我的作品”打开同一 ID 确认代码，再做一次实际修改和保存/提交，确认更新同一 ID。这个差异不作为夹具 PR 的失败条件，也不能记录成 Python 已验证独立草稿按钮。实际体验是否符合教学使用，由本次真实浏览器结果判断。

5. **教师 `fixture_teacher_a`：从学生实际提交批改。** 通过“学生作业批改”菜单进入待批改，以学生/课程/类型找到刚才三份作品。分别打开真实预览，给一份零分及具体中文评语，其余正常评分；保存后从已批改列表重开，确认评分/评语仍在。再回学生账号刷新“我的作品”：确认分数；课程作品当前评语通过评分处 tooltip 显示，需实际触发读取，不能只看到星形就声称学生读到了评语。

6. **教师发布任务 → 学生文件提交 → 教师反馈 → 学生回读。** 教师在“布置班级作业”真实新增一个文件类型任务并发布给班 a（亦可先用预置 `fixture_ui_task` 核对入口，但预置不算创建）。学生在“我的班级作业”下载自制提交示例或自行写纯合成文本，使用原上传/提交表单保存。教师在工作台按“班级作业”找到同一提交，给零分+评语；学生回“我的班级作业”直接读到反馈，刷新/重开后仍有正确内容。记录 additionalId、workId、状态变化，不记录会话令牌。

7. **真实边界与失败恢复。** 在已授权登录前提下，学生 b 与教师 b 应读不到班 a 私有课程资源/作品/任务；学生 a 不应进入管理路由。匿名无权下载私有单元素材。用浏览器断网或阻断自己这次请求验证上传/提交/批改失败后内容保留、恢复后能重试，记录按钮忙碌态与重复点击结果。选择视口 390/768/1440，至少核对课程→编辑器→提交→批改链的关键操作没有遮挡且键盘能完成；这些项目必须来自真实页面结果，纯夹具 tests 不覆盖它们。

每段验收要保留“实际页面操作 + 对应真实 API 返回/同一业务 ID + 重开后的内容或文件摘要”证据。无需发布敏感截图、口令、令牌或私有配置。固定夹具与每次操作新增数据分开记录；下一次从**新建环境**开始，不把已使用的环境覆盖恢复成初始样子。

## 本 PR 验证范围

纯检查命令（不连接 MySQL/Redis/应用，也不读取任何私有生产内容）：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s api/dev -p test_role_flow_fixture.py -v
python3 api/dev/seed-role-flows.py --help
```

纯测试涵盖：标准种子解析/表达式拒绝、未知或修改行/列拒绝、保留五账号及既有关系、真实角色菜单与按钮授权、空参数编码规则、媒体/模板结构与摘要、本地资源登记、SQL 文本不会变成语句、非私有/符号链接/旧端口/已启动/重复环境拒绝、实际 datadir 检查调用与外部配置拒绝。所有 DB/端口检查都使用 mock，不等于真实 MySQL 导入成功。

作者冻结时真实环境尚未执行；root 后续 create/verify、启动与 API 检查结果见下文。正常验证码登录及三角色浏览器验收仍待执行。独立审查结果单独记录，不把本 Agent 自检称为独立验收。


## root 实际导入与接口预检

root 在已准备、未启动过的 `.devspace/role-flow-1003` 串行执行 create 和 verify，均退出0。初始私有清单绑定69表116行、原五账号、三角色菜单、3新单元、1新课程/任务及10附件（原2+自制8）；清单 SHA256 `bfa1d14a77458d4276a5b9519e1f0691d83bd7bc8c7fa894232a6e13261303a5`。首次应用启动前严格回读相等，未放宽保护以完成导入。[初始结果](evidence/role-flow-fixture/root-initial-verification.json)。

随后 root 用 #43 已测 JAR 启动18149/PID33557，并以组合候选 `e08cb55` 的现有dist启动18150/PID33973。Java业务源码和web没有变化，未新构建Java/前端，沿用前序305项前端与构建证据；本次4项实际HTTP字节匹配只是服务产物核对。测试入口为 `http://127.0.0.1:18150/index`，真实生产课程副本18142和合成主预览18112保留。[产物读取](evidence/role-flow-fixture/frontend-byte-checks.json)。

既有独立 `FixtureApi` 在专用五合成账号环境进行真实API登录、GET与退出，不填写浏览器验证码、不注入浏览器令牌。实际22/22：五账号各自的完整菜单与按钮权限、A/B课程分配范围、三编辑器类型及隐藏教案、跨班单元拒绝、5种课程素材字节、视频Range和跨班视频拒绝、读取前后教学/配置表及附件不变。源数据全为合成，账号认证引起的日志及缓存正常保留，不重置使用后的环境。[实际API结果](evidence/role-flow-fixture/api-preflight.json)。精确执行探针保留在 [executed-api-preflight.py](evidence/role-flow-fixture/executed-api-preflight.py)，它绑定本轮本机路径及新输出文件，属于执行证据，不是可覆盖重跑的通用CLI。

分支全部开发工具实际发现79项，78通过、1生产副本可选MySQL测试跳过，退出0；作者15项纯测试包含在其中，不叠加声称独立覆盖。[完整工具日志](evidence/role-flow-fixture/all-dev-tests.log)。独立测试Agent只读核对产品组件/权限/班级与媒体契约，没有运行runtime或复跑作者15项。初审发现作品状态字典缺失，作者冻结前补齐`work_status`和`yn`，最终无本轮阻断。[摘要及源码绑定](evidence/role-flow-fixture/root-validation.json)。

本PR交付可选测试准备工具和实际可用的接口/素材环境，没有修改生产、默认seed、Java或前端权限。用户新增、三角色真实页面维护、播放/拖动、编辑保存重开/提交与反馈仍未据此通过；验证码浏览器操作等待前序工具所需确认，其他开发继续。没有GitHub合并或生产部署，Goal active。
