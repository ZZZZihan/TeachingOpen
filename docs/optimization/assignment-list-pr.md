# 班级作业列表：范围、状态与附件地址

学生的 `mineAdditionalWork` 列表原来可能显示不属于当前班级或已撤回任务的草稿，班级筛选参数也没有生效。本地作品附件被拼接成七牛地址，字典装饰器又加一次本地前缀，导致返回地址无法继续学习或下载。本项修正列表读取契约，供后续任务/反馈页面使用；不包含页面视觉修改。

产品及专项检查提交：`3eada950e4681cb86d787ee07d7233c1e3589058`，基于 PR #20 的 `bad0e272969d0b0543381ba61276d68f03393950`。完整 JAR 和源码摘要见 [准确候选](evidence/assignment-list/candidate.json)。

## 修改后的行为

- SQL 给“未提交”条件加明确括号，完整班级 ID 匹配替代 `LIKE` 子串匹配；逗号列表中的空格、制表符和换行被处理。未发布、已结束、异班任务不会因草稿状态绕过范围。
- 班级参数真正筛选当前用户已有班级，陌生班级返回空数组。仍使用当前登录身份，调用者传入的用户 ID 不会切换身份。
- 已删除作品不再当作有效提交，任务恢复为未提交；零分和教师文字反馈原样保留。
- 返回的 `mineWorkDepartId` 保留已存作品班级。多班共享任务的现有作品只在其仍有资格的保存班级中显示；未开始的任务按稳定班级顺序选择，避免依赖数据库遍历顺序。没有迁移或重绑定历史作品。
- `mineWorkUrl` / `mineWorkCover` 按 `sys_file.file_location` 选择本地或七牛域，正确编码文件路径。兼容保留 `_url` 别名且值一致，避免二次装饰。缺失记录或未知存储位置返回空地址，不伪造可下载链接。真实下载权限仍由 #18 控制。
- 私人列表设置 `Cache-Control: no-store`；本方法内读取失败返回通用 HTTP 503，恢复数据后同一会话可重试，不向学生返回 SQL 诊断。

## 真实对照与回归

旧 JAR 上 **12/12** 符合旧问题预期；新 JAR 上专项 **48/48** 通过。使用合成本机账号、MySQL、Redis 和自制附件，覆盖发布/状态/班级组合、陌生班级与伪造用户参数、删除作品、零分评语、共享任务保存班级、本地附件本人实际字节读取/异用户拒绝、未知及七牛存储地址、真实数据库查询故障与恢复。

同一新 JAR `85f7746a3ae4b143f1a4ca4e5c043e11c81bf7d69f32c72b7dbaa190f6a0e85c` 上串行重跑：

| 范围 | 结果 |
| --- | --- |
| 学生作业提交 | 95/95 |
| 教师作业管理 | 134/134 |
| 本地附件下载 | 88/88 |

三模块 `clean package` 成功；父 POM 仍跳过 Java 测试，不能把构建当作行为验收。行为证据来自实际 HTTP/数据库脚本。Python 语法及 `git diff --check` 通过。前端未改动，本分支没有重跑前端构建，也没有把历史前端检查计入此次结果。

## 复现和清理

按 `api/BUILDING.md` 使用已校验工具与现有隔离依赖缓存构建，在本机合成环境启动新 JAR，然后执行：

```sh
python3 api/dev/verify-assignment-list.py --runtime /absolute/path/to/course-role-runtime --output /tmp/assignment-list.json
python3 api/dev/verify-work-submission.py --runtime /absolute/path/to/course-role-runtime --output /tmp/submission.json
python3 api/dev/verify-work-management.py --runtime /absolute/path/to/course-role-runtime --java-home /absolute/path/to/java8 --output /tmp/work-management.json
python3 api/dev/verify-local-download.py --runtime /absolute/path/to/course-role-runtime --output /tmp/download.json
```

旧 JAR 对照给专项命令增加 `--expect-legacy --jar /absolute/path/to/running/old.jar`。脚本验证运行进程、JAR 摘要、数据库/Redis 归属，只适用于独占的合成环境；不在生产或有人同时编辑的数据库执行。

通用夹具的两个“班”目前 `org_category=2`（部门），该接口按系统契约只查 `3`（班级）。专项检查临时改成 `3`，最后恢复原值；没有以原空列表声称业务通过。完整角色浏览器验收需要明确准备真实班级类型。故障检查临时重命名合成任务表，`finally` 中恢复；六表全列摘要、附件字节及班级类型恢复，临时表清除，用户/文件/作品计数恢复到 5/2/2，会话已退出。

本次没有浏览器 UI 截图或认证后页面验收；真实七牛、Office 预览、多个历史重复作品的整理及服务端分页不在该修复范围。原源码 5,634 项摘要未变，18091/18101/18111 均健康，只有隔离 18111 切换为新 JAR。旧 JAR 保留可本地回退；回退会恢复上述旧行为。没有数据库结构迁移、GitHub PR 合并或生产部署。
