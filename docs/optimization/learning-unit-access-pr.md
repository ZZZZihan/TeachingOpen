# 学习单元统一课程权限及资料显示规则

创作工具通过 `getUnitWorkInfo` 获取单元和本人作品入口；原接口只查询单元 ID，没有验证课程权限，也没有应用四个“对学生显示”开关。隔离真实后端已重现：跨班学生和教师能够读取未分配的私有单元，本班学生能取得已隐藏的视频、案例、资料、教案路径。同时，学习列表直接拆箱可空的 Boolean 字段，遇到空开关会整体失败；管理员没有班级分配时也被列表拒绝。

本 PR 基于 #9，复用 #8 的课程资源检查，让列表和详情都按“已分配课程、共享课程或管理员/dev”授权，并复用一处学生资料过滤方法。身份为学生或尚未设置时，只有明确为 true 的开关才返回对应资源；先过滤，再进行列表中的资料地址转换。教师沿用原显示规则。管理接口仍保留 #8 的角色限制。

预设作业 `courseWork`、作业类型、课程正文和按当前用户查询的 `mineWorkId` 保留；没有改变创作工具的返回字段格式。此修复针对现有四个显示开关，不新增 `courseWorkAnswer` 的发布策略；该历史字段的使用与答案开放规则仍需核查。文件直链权限、媒体播放、编辑器保存及重新打开均需另外验收。

## 实际验证

使用独立的 `course-role-runtime`：MySQL 13326、Redis 16399、后端 18111，五个合成账号。脚本验证运行 JAR、数据库归属与 Redis 目录后才生成临时课程和单元；不连接生产或写入真实师生数据。

- 修复前 **9/9** 项预期现象及清理核对：包含越权读取、隐藏资源返回、空开关导致业务失败、管理员无法读取。这里表示旧缺陷被重现，不表示旧版本安全通过。
- 修复后 **80/80** 项真实 HTTP/数据检查：两个入口的匿名拒绝、跨班学生/教师拒绝、共享课程读取、管理员/dev 读取；四类资源分别开启、全部关闭、全部开启及空值；学生身份为空时仍受显示规则限制；预设作业及生成 URL 保留、本人已有作品入口保留、不存在单元的原失败格式保留。
- 同一新 JAR 上复跑前置课程管理 **188/188**、权限缓存 **11/11**。这些是组合回归，不算作新增加的独立用例。
- 所有原课程、单元、分班、作品及文件行摘要恢复，附件字节不变；临时角色删除，管理员角色和学生身份恢复，测试会话退出。
- Maven 三模块干净构建成功，Java 测试被父 POM 跳过；上述脚本是单独执行的真实集成检查。Python 语法和 Git 差异检查通过。

证据：[修复前](evidence/learning-unit-access/before.json)、[修复后](evidence/learning-unit-access/after.json)、[课程管理组合](evidence/learning-unit-access/course-management-combined.json)、[缓存组合](evidence/learning-unit-access/role-cache-combined.json)、[候选摘要](evidence/learning-unit-access/candidate.json)、[构建摘要](evidence/learning-unit-access/build-summary.txt)。

匿名请求返回 HTTP 401；已登录但无课程权限沿用项目的 HTTP 200 / 业务码 510。空开关在修复前触发的是 HTTP 200 / 业务码 500，修复后列表成功且不返回该资源。没有宣称 HTTP 403 或完整浏览器教学流程通过。

## 复现及兼容性

按 [独立运行说明](../../api/BUILDING.md) 启动合成环境，在本分支根目录执行：

```sh
python3 api/dev/verify-learning-units.py --runtime "$TEACHING_RUNTIME" \
  --output "$TEACHING_RUNTIME/learning-unit-check.json"
python3 api/dev/verify-course-management.py --runtime "$TEACHING_RUNTIME" \
  --output "$TEACHING_RUNTIME/course-management-check.json"
python3 api/dev/verify-role-cache.py --runtime "$TEACHING_RUNTIME" \
  --output "$TEACHING_RUNTIME/role-cache-check.json"
```

基线复现传 `--jar` 指向实际运行的 #9 JAR，并加 `--expect-legacy`。测试中的资源路径是标记值，未提供真实视频、PPT 或 Scratch 文件，不能据此声称媒体或创作工具通过。

无数据库迁移、依赖升级或前端修改。课程列表的无权限错误从原业务码 500 统一为 510；跨班详情原有的错误成功路径将被拒绝。回退会重新引入越权和隐藏资源返回，不能把服务可启动当作安全回退验收。未合并、未部署、未改生产。
