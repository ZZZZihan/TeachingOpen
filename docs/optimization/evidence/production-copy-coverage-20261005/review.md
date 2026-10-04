# 真实课程覆盖只读审计（2026-10-05）

本次结论：私有副本的 297 份课程资源清单全部存在且字节长度匹配；数据主要覆盖视频、HTML 正文、PDF 课程资料、Markdown 教案，没有覆盖练习模板、案例或自定义作业。课程班级历史关联存在悬空数据，需作为下一轮真实数据兼容性测试的输入，尚未作产品修复。

范围与依据：候选代码 HEAD 为 `64cce174aac6cf3699985b4bc88a30cc70c2f67f`，运行 JAR 为 `f03ac420301977cea26e14d9de0bab03f0d8a5c0e7ec92854363ad07347060c0`。使用已有 `verify-production-content.py` 的 guard、server READ ONLY SQL 和业务哈希方法确认隔离副本身份。审计开始、完成 UTC 时间以及全部统计、前后哈希均在同目录 `aggregate.json`。未重复既有匿名列表/封面检查。

真实数据覆盖如下：

| 产品分支或字段 | 私有副本数量 | 当前证据 |
| --- | ---: | --- |
| 数据表、课程、单元 | 69、5、83 | schema / 只读 SQL |
| 有单元的课程 | 3 | 单元分布为 14、24、45；另 2 课无单元 |
| 上传型视频 | 83 | 来源 code=1，全为 MP4 引用；链接/嵌入型为 0 |
| 单元 HTML 正文 | 83 | 全含 HTML 标签；未检出 img/video/audio/iframe 标签；2 个外部引用未访问 |
| 课程资料 | 45 | 全为 PDF 引用，其他 38 单元为空 |
| 课程教案 | 83 | 全为 `.md` 后缀；文件存在/大小匹配，内容格式和实际预览未验收 |
| 单元封面、课程封面 | 83、3 | JPG、PNG 清单引用 |
| 案例、预设作业、作业答案 | 0、0、0 | 字段为空，无法提供编辑器/模板兼容性证据 |
| 自定义作业 | 0 | 无真实记录 |
| 单元练习类型 | 83 条均 NULL | Scratch3 code=1/2、ScratchJr code=3、Python Turtle code=4 均无记录 |

上述类型以实际消费者为依据：`TeachingCourseUnitModal.vue` 对 `mediaContent` 使用 `JEditor`；`JEditor.vue` 使用 TinyMCE。`UnitViewModal.vue` 的 `caseUrl/workUrl` 按 work type 1/2/3/4 分派到 Scratch3、ScratchJr、Python Turtle；资料和教案按逗号拆分交给文件预览函数。`mineUnit` 对学生使用 showCourseVideo/showCourseCase/showCoursePpt/showCoursePlan 开关。本副本的非空视频、资料、教案分别有 83、45、83 条开关开启，没有非空但隐藏的样本；多附件、链接/嵌入视频、隐藏资源也没有覆盖。全部练习类型为 NULL 本身不能认定为产品故障，因为相关练习、案例字段也为空。

资源检查覆盖清单 297/297：83 JPG、83 MP4、45 PDF、83 Markdown、3 PNG，总 `5,941,586,119` 字节。`resource-references.json` 和 `assets-result.json` 的路径集合相同；本次查找缺失/不安全文件 0，大小不匹配 0；所有识别出的本地资源引用均落在清单内。本次仅 `stat` 文件，没有读取资源正文或重算约 6 GB 资源哈希；已有采集时哈希核验由 manifest guard 绑定。数据库与附件原始采集并非原子快照。

关联审计发现：

- 83 单元缺少所属课程的数量为 0。5 课中 2 课没有单元；空课程可能符合现有业务，需在下一次真实数据页面测试确认空态。
- `teaching_course_dept` 共 4 条边，4 条均同时缺少课程和班级；涉及 3 个缺失班级标识；重复课程班级对为 0。`TeachingCourseDeptMapper.xml:list` inner join 课程和班级后只剩 0 条，所以这些历史边不会出现在现有管理列表。尚未验证权限或登录行为，也不将其直接认定为当前有效课程的访问故障。
- `sys_user_depart` 共 3 条边，3 条同时缺少用户和班级。当前班级表仅 1 条。源副本 sanitization 记录保留了 7 个悬空班级标识和 5 个悬空用户标识，审计没有补造关系、清理历史数据或访问学生文件。

建议下一项测试先覆盖一节同时带 MP4、HTML 正文、PDF 资料和 Markdown 教案的真实单元，检查视频播放、正文渲染、Markdown/PDF 打开或预览，以及刷新/失败恢复。Scratch3/ScratchJr/Python 的案例与模板须使用单独有授权的合成或已知样本，不能声称这 83 条真实单元已经覆盖。班级关系问题先复查历史数据在真实教学列表中的呈现与错误恢复，再决定是否需要独立产品修复 PR。

记录与请求计数：

- 执行命令：`python3 .devspace/prod-fixture-1003/audit-course-coverage-20261005.py`；随后只读核对 Markdown 后缀并整理这两份汇总报告。原始内容始终未输出，私有脚本和内部报告均为权限 600。
- 正式审计执行 58 条 SELECT：guard 2、前后 9 张表哈希 36、覆盖探针 20。前置 schema/guard 核对另 11 条，整个本子任务为 69 条；计数根据固定调用点核对。此前暂存的 28 条 tracked query 只含 20 条探针和额外 2 表的前后哈希 8 条，不含 guard 与原有 7 表的前后哈希 28 条，已改成完整分项。
- 每条 SELECT 通过 `START TRANSACTION READ ONLY` 和 `ROLLBACK` 执行。9 张表为 teaching_course、teaching_course_unit、teaching_course_dept、teaching_additional_work、teaching_student、teaching_work、teaching_work_correct、sys_depart、sys_user_depart；前后行数和哈希均相同。这不是全部 69 张表的哈希断言。
- HTTP、浏览器、外网、认证接口、Redis、服务启停、数据库写入、学生文件读取、产品修改、提交/推送均为 0。未作视频播放、编辑器保存、预览、真实角色或人工验收，未形成生产交付结论。
