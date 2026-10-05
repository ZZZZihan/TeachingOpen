# 三页正式接入前的合同核对

日期：2026-10-05。关联 [目标](club-learning-goal-2026-10-05.md) 与 [原型 PR #77](https://github.com/ZZZZihan/TeachingOpen/pull/77)。本次由两位子 Agent 并行只读核对，主 Agent 复核关键实现；没有修改正式产品、运行新业务测试或连接生产。用户视觉反馈尚未收到，三页原型运行文件保持原版本。

源码基线固定为上一阶段组合候选 `4f30e51b7121b7f102cfe1c71bba3183cd21b7e2`，与原型分支基线不同。该提交只存在于本地组合工作树，GitHub 查询未找到此 SHA；下列源码脚注给出该版本内的路径与行号，不能当作远端 main 的当前内容。接入时须重查目标分支。

## 创作台：名称、续作与反馈应准确

| 源码事实 | 正式接入约束 |
| --- | --- |
| 本人作品列表默认按 `create_time DESC`，不是编辑时间。列表控制器[^works-controller] | 现有首项不能标成“最近编辑”。先使用“我的作品”；若增加最近续作入口，独立定义排序和时间含义。通用 `updateTime` 也不专指学生修改代码。 |
| MineWorks 对各状态作品均给出按类型选择编辑器的入口；附加作业页只对无作品、草稿或待批改作品提供继续入口。作品页[^mine-works]、附加作业页[^additional-works] | 保留类型与 `workId`，并明确“继续修改、重新提交”的含义，不能默认已批改作品被锁定。 |
| 课程编辑器优先使用显式 `workId`，否则查 `mineWorkId`；有作品时恢复文件与任务归属，无作品才使用模板；发现失败不回退到新作品。恢复状态机[^scratch-persistence] | 课程入口保留 `scene=course`、`unitId`，作品入口保留 `workId`。失败显示重试，不能以新模板掩盖已有作品读取失败。 |
| `mineWorkId` 子查询使用没有排序、没有 `del_flag` 条件的 `limit 1`。单元映射[^unit-mapper] | 目前只称“继续已有作品”，不能声称返回“最新草稿”。重复记录、删除记录如何选择需单独验证后处理。 |
| Scratch / ScratchJr 区分草稿 0 和提交 1；Python 保存固定为 1。保存成功留在编辑器，并将 `workId` 写入当前 URL。Scratch 保存[^scratch-persistence]、Python 保存[^python-persistence] | 按工具显示真实动作；不能把 Python 现有保存统一包装为“仅存草稿”。返回创作台后的列表刷新需作为真实行为验证。 |
| 提交服务更新同一作品 ID，不显式清空既有批改；列表按作品 ID 关联评分评语，没有选择最新一条批改的条件。提交服务[^submission]、作品映射[^work-mapper] | 重新提交后的旧评语不能称为“本次批改”。正式页需要呈现待反馈状态，并明确保留的历史建议；不在 UI 重做中直接删除批改记录。多次批改的行为需运行验证。 |
| 合法评分 0–5（包括 0）显示 `n / 5`；无有效分数为“未评分”，无文字为“暂无评语”。反馈格式[^feedback] | 沿用真实反馈字段，不把已批改、评分或浏览次数转换为个人完成百分比。 |

作品列表须继续区分加载、无作品、失败和无权限。StudentWorkListState[^work-list-state] 与 状态辅助函数[^work-list-util] 已有对应处理。编辑器读取失败时禁用保存并允许重试；保存失败保留当前内容。原班级失去任务权限后，提交服务仍会拒绝保存，新界面不能把这类拒绝显示成保存成功。

## 探索与学习页：展示范围不扩大访问权限

- 公开课程接口以 `showHome=1` 展示；它不代表匿名用户可以读取单元。我的课程列表使用共享或已分班且到开课时间的课程条件；直接访问权限检查共享及班级关系，没有同样的开课时间条件。因此不能把列表隐藏称为后端强制开课保护。公开课程[^home-course]、我的课程查询[^course-mapper]、课程权限[^course-permission]
- `mineUnit` / `getUnitWorkInfo` 校验课程权限，并对学生及身份为空账号过滤视频、案例、教案、资料四类字段。新阅读页直接使用过滤后的结果，不从管理列表或旧缓存补回隐藏资源。单元控制器[^unit-controller]
- 答案字段不受上述四个开关过滤，附件授权目前允许有课程权限者读取答案引用。现有阅读器没有答案入口；新页面应明确列出可展示字段，不因遍历全部接口字段而增加答案入口。若需要改变答案开放策略，另行定义教学规则和独立改动。附件授权[^download-access]、现有阅读器[^unit-view]
- 继续复用安全资源 URL、预览转换、媒体失败重试、课程加载与空态、分页失败保留旧内容和请求序号隔离。不能为视觉统一移除这些状态。阅读器[^unit-view]、课程列表[^course-list]、单元列表[^unit-list]

以上为源码可确认的接入约束。开课时间、旧评语、多作品关联等行为尚未在本轮运行复现，不将它们直接定性为已经复现的产品故障或安全漏洞。

## 真实副本与测试素材

主 Agent 仅读取现有私有副本清单和资源清单元数据：资源数 297，资产字节数 5,941,586,119，`student_files_copied=false`。`snapshot-manifest.json` 的 SHA-256 为 `bb4380486c95f6ddd2aa8b362ffed6213e2614485a090e27f4c82ef825cdc100`，与此前冻结记录一致。这是已有快照的文件核对，不是当前生产数据库或全部资产字节的重新核验。

因此，生产来源副本可继续用于私有、只读的课程与资料兼容核对；它没有学生作品文件，不能用于证明作品恢复链路。保存、再次打开、修改后提交和教师反馈测试应使用隔离环境中的自制作品与合成账号。原课程正文、学生标识、原附件名、账号和凭据均不进入本 PR。

## 收到方向反馈后的最小接入范围

1. 探索首页：用实际允许展示的课程与成果字段替换示意卡片；机构识别保留。没有可靠来源的难度、时长、学习进度不添加。
2. 学生创作台：接本人作品和课程；验证从明确的作品 ID 打开同一份内容，修改并保存后可重新打开。真实无作品与请求失败使用不同状态。
3. 代表性单元：沿用实际编辑器，验证可见资料、学习入口、保存或提交、返回后查找作品、读取老师建议与再次修改。工具能力不同，动作名称分别准确。

三个部分按可独立评阅的结果分别提 PR，依赖关系写清。每个实现 PR 提供实际构建版本、相关回归、390 与桌面截图和剩余限制；权限与直接附件检查使用匹配该实现的运行版本。用户视觉反馈前不扩大到全站或重写编辑器。

既有历史回执中，课程权限 HTTP 检查为 80/80、附件授权为 88/88，各自绑定当时 JAR；本轮未重跑，不计作新三页接入通过证据。当前原型交互检查仍以 [交付记录](club-learning-preview-delivery-2026-10-05.md) 为准。真实学生试用、正式产品验收和生产上线仍未完成。

[^works-controller]: `api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/teaching/controller/TeachingWorkController.java:144`。
[^mine-works]: `web/src/views/account/center/page/MineWorks.vue:103`。
[^additional-works]: `web/src/views/account/course/MyAdditionalWorkList.vue:144`。
[^scratch-persistence]: `web/public/scratch3/persistence.js:49`。
[^unit-mapper]: `api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/teaching/mapper/xml/TeachingCourseUnitMapper.xml:59`。
[^python-persistence]: `web/public/python/persistence.js:105`。
[^submission]: `api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/teaching/service/TeachingWorkSubmissionService.java:119`。
[^work-mapper]: `api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/teaching/mapper/xml/TeachingWorkMapper.xml:23`。
[^feedback]: `web/src/utils/studentWorkFeedback.js:3`。
[^work-list-state]: `web/src/components/teaching/StudentWorkListState.vue:12`。
[^work-list-util]: `web/src/utils/studentWorkList.js:22`。
[^home-course]: `api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/teaching/controller/TeachingCourseController.java:75`。
[^course-mapper]: `api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/teaching/mapper/xml/TeachingCourseMapper.xml:9`。
[^course-permission]: `api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/teaching/service/impl/TeachingCourseDeptServiceImpl.java:42`。
[^unit-controller]: `api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/teaching/controller/TeachingCourseUnitController.java:127`。
[^download-access]: `api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/system/service/LocalDownloadAccessService.java:75`。
[^unit-view]: `web/src/views/account/course/modules/UnitViewModal.vue:88`。
[^course-list]: `web/src/views/account/course/CourseListCard.vue:9`。
[^unit-list]: `web/src/views/account/course/CourseUnitListCard.vue:9`。
