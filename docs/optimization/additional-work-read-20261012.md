# 追加作业详情读取范围

基于 `93d4cfe8e911bccbaf1d20094357fa0b88076a86`，处理 Pro 首轮报告中两个追加作业详情入口缺少对象授权的 Medium。修复前 `AdditionalWorkReadAuthorizationTest#studentCannotReadAnotherClassThroughEitherDetailRoute` 在真实控制器/服务调用上失败，普通学生可取得其他班级任务；[原始失败日志](evidence/additional-work-read-20261012/before.log)。这不是生产数据验证。

`/teaching/teachingAdditionalWork/queryById` 和 `/getWorkInfo` 现在都通过 `getReadableById` 与 `TeachingAccessService.requireReadAdditionalWork`。必须有当前有效账户：管理员/dev 可读；教师能预览当前负责班级被分配的任务（包括草稿）；当前班级成员只能读取已发布、分配到本人班级的任务。班级 ID 逐项精确匹配，任务 ID 也拒绝数据库大小写排序规则产生的别名。角色和教师管理范围从当前账户记录读取，旧 principal 不会保留已撤销的管理权限。

两个入口返回同一次查询中已授权的对象；不再在授权后第二次裸查询详情。多班共享任务保留各已分配班级的读取权；作者身份本身不授予跨班读取。追加作业没有公开课共享标志，未扩展其匿名读取；既有课程 `is_shared` / 首页公开读取逻辑未改动。

[修复后日志](evidence/additional-work-read-20261012/after.log) 中 33 项 Java 回归通过：新增 `AdditionalWorkReadAuthorizationTest` 9 项，以及原 `AdditionalWorkAuthorizationTest` 15 项、`WorkAttachmentAuthorizationTest` 9 项，无失败、错误或跳过。覆盖学生本人、跨班、草稿、精确班级、多班、教师实时范围、旧角色、管理员/dev、匿名/禁用/删除账号及未知/别名 ID。`python3 -m py_compile api/dev/verify-additional-work-read-authorization.py`、`git diff --check` 通过。

新增真实 HTTP 探针：`python3 api/dev/verify-additional-work-read-authorization.py --runtime <owned-runtime> --jar <candidate.jar> --output <new-report.json>`，可用 `--expect-legacy` 记录旧候选两个裸详情入口。检查两入口允许/拒绝矩阵、公共课程兼容性，逐项确认响应中没有私有哨兵正文，并恢复全部临时任务/课程行，核对原始业务行和上传字节。该 HTTP 探针在本提交时尚未运行，等待根任务下一组合候选。

普通课程、学生作品历史与通用审计日志沿用各自业务授权；后两项由并行的独立修复处理。本自检不等于 Pro 验收。
