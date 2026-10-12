# Scratch 共享素材管理边界（Pro H-07）

基于 93d4cfe8；独立问题为共享素材库的全局管理权限、写入结构和读取容错。

- `GlobalResourceAccessService` 每次读取实时有效账户与数据库 admin/dev 授权，不依赖缓存角色。列表、详情、导出和全部写入均按此边界处理；普通教师的班级管理范围不赋予共享库写权。
- `TeachingScratchAssetsServiceImpl` 收口单条保存、编辑、删除和通用批量导入。批量先全量校验再写入，并显式声明单参/双参入口事务。无实际消费者的 wrapper 更新与 upsert 不开放。
- 只复制素材类型、名称、JSON、文件键和标签。服务生成新增 ID、作者、时间、删除状态；编辑不接受审计字段或删除状态。
- 校验四类 JSON 的字段、集合、数值、相对文件键以及大小/嵌套上限，接受现有表单和仓库 Scratch 索引结构。导入最多 200 行，实际 Excel 解析后仍走同一校验。
- 编辑器继续读取 `/teaching/teachingScratchAssets/getScratchAssets`。每条历史坏数据独立跳过并记录 ID，合法邻居仍返回；不改变内置静态库。
- 删除索引不自动删除文件字节。素材可能已用于保存的项目；文件管理按现有引用检查独立回收，避免索引操作直接销毁共享内容。

验证证据由任务保存于 `evidence/`：修改前 `h07-before-java.log` 两条回归分别产生权限失败与 JSON 错误；修复后 `h07-after-java-r3.log` 的 ScratchAssetAdministrationTest 共 9 条通过，包括 admin/dev、实时撤权、冻结账户、所有管理 HTTP mapping、实际 Excel 导入/坏行无部分写入，以及 1,663 条仓库索引兼容。`h07-node.log` 课程上传与 Scratch bridge 共 22 条通过。

实际 HTTP/MySQL 探针 `api/dev/verify-shared-resource-boundaries.py` 面向隔离合成 runtime，验证所有拒绝路径数据库/字节不变、管理员和临时 dev 正常 CRUD/Excel、同 token 撤权、学生素材读取及坏记录隔离；保留 JAR SHA 和完整清理断言。不支持旧漏洞请求重放。此提交准备探针，不把未运行的候选 HTTP/MySQL、CI 或独立 Pro 复核写为已通过；根代理统一执行并保留最终证据。
