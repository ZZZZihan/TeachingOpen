班级成员上下文的独立实际 HTTP/DB 对照已完成。最终核心专项为 **22/22**，补充部门角色专项为 **9/9**，合计 **31 条断言全部通过**；旧源相同最终工具分别为 **12/22** 和 **7/9**。这里统计的是断言数，包括各专项的一条启动器检查和一条完整恢复检查，不是业务故事数。

测试由 `/root/python_frame_tests` 编写并执行；产品由 `/root/class_context_impl` 编写。离线方法测试由 `/root/course_resume_impl` 执行，真实 Vue/AntD 浏览器验证由 root 执行，二者结果不混入本报告的 31 条实际 HTTP/DB 断言。

| 对照 | 最终旧源 | 冻结新源 | 证据 |
| --- | --- | --- | --- |
| 成员核心：实际 DeptUserInfo / SelectUserModal / JeecgListMixin 方法 | 12/22 | 22/22 | [旧源](evidence/class-member-context/live-before-final.json)、[新源](evidence/class-member-context/live-after.json) |
| 部门角色：实际 DeptRoleUserModal 方法 | 7/9 | 9/9 | [旧源](evidence/class-member-context/live-role-before-final.json)、[新源](evidence/class-member-context/live-role-after-final.json) |

旧前端源为 `8f58b32362899047da0136e41278368fd26c88f0`。两组对照都使用同一个冻结后端 JAR，SHA-256 为 `4578567dcedc18bf8a5f69758f8209d9b7bc74fc24f24f0d50196ec97e684c42`。它位于 `.devspace/artifacts/encoded-media-root/author-build-20261003T131119Z/teaching-open-2.8.0.jar`；本轮没有重建、修改后端或增加产品诊断接口。

核心旧版真实复现了三个残留入口。A 的清空确认打开后切到 B，旧 OK 发送清空 B 的请求，将 B 教师、学生两条关联变成零条；A 的批量确认及切班后再打开批量菜单，会删除共属用户的 B 关联；A 的用户选择在切到 B 或取消后重新打开时，都会把原 A 学生加入 B。新版相同调用都不再发出旧的写请求，数据库相应关联保持。正常 B 查询、添加已有用户、单条取消关联、批量取消和清空班级继续通过真实接口执行；清空只删除关系，五个账号保留。

失败行为用真实角色等级验证：仅在独占夹具内把管理员、教师、学生等级分别设置为 9、5、1，使用合法学生 CLI 会话取消教师关联。后端 HTTP 200 返回业务拒绝，关系矩阵不变，组件显示失败反馈且不显示成功。三个角色完整原行随后恢复。这不是手工合成一个失败响应。

部门角色补充使用同一合成学生的 A/B 关联、两个 A 角色和一个 B 角色。实际选项接口只返回 A 的两个角色，已分配接口返回 A+B。旧组件保存空 A 选择或 A 新选择时，实际请求的 oldRoleId 包含 B，导致 B 角色被删除。新版保存空 A 选择后直接 DB 计数为 Aold=0、Anew=0、Bold=1；选择 Anew 保存后为 Aold=0、Anew=1、Bold=1。这个专项没有使用 mock 来判定 B 是否保留。

保留了初轮证据，没有把失败追记为通过：[成员首轮旧 12/22](evidence/class-member-context/live-before.json)、[角色首轮旧 7/9](evidence/class-member-context/live-role-before.json)、[角色首轮新 8/9](evidence/class-member-context/live-role-after.json)。成员初轮后，反馈断言从仅允许 warning/error toast 调整为也接受模板显示的 actionError，随后重新运行最终旧源；最终旧、新核心报告的 Python 和 CJS 哈希完全相同。角色首轮工具会无条件重建 B：新版已经保留 B 后又调用 oldRoleId 为空、newRoleId 为 B 的差集接口，会再插入关联，使“恰好一条”读数检查失败。初轮报告没有保存原始行数，归因依据为保留的真实请求序列及后端差集服务实现。修正为仅在 B 缺失时恢复，并增加实际行数记录后，旧、新角色各使用同一最终工具重新执行，得到 7/9 与 9/9。产品未因该夹具问题修改。

还单独观察到一个**未修复的后端授权问题**：在本项合成库中，合法学生会话直接调用 `GET /sys/sysDepart/removeAll?id=<owned class A>`，实际 HTTP 200、success=true，A 两条成员关联（包含教师）变成零条，账号仍保留。该结果放在核心 JSON 的 `observations_not_fixed` 中，没有纳入前端通过数。此接口的角色及班级权限边界需要另一个后端修复任务；本轮前端保护不能替代后端授权。这是本机合成环境观察，不是生产探测或生产安全验收。

所有执行仅访问新建的 `.devspace/class-member-context-1003`：MySQL 13372、Redis 16445、后端 18178；前端 18179 未启动。初始化检查见 [记录](evidence/class-member-context/live-runtime-initialization.json)。每轮先对全部 69 张表结构、除 sys_log 外的 68 张表的数据及所有附件生成摘要，私有保存完整 sys_user、sys_depart、角色和关系原行。登录产生的 org_code、更新元字段也按完整行恢复；HEX 空值正确恢复为 SQL 空串。角色专项新增的三个角色、角色分配、额外班级关系按拥有的精确 ID 清理。四份最终对照报告均记录：表集合一致、结构无差异、非审计表数据无差异、附件完全一致。sys_log 的真实测试审计记录保留，不把它算作业务数据恢复失败。

合法认证通过现有 FixtureApi 的 CLI CAPTCHA/登录流程；没有浏览器认证注入。密码仅从该 runtime 的私有凭据文件读取，token 只在内存及子进程 stdin 中传递，不进入命令行、报告或请求观察。共享 JSON 只含合成别名、必要接口/响应、A/B 角色范围、计数和 SHA。实际扫描测试工具和 live JSON 没有发现 JWT 值或拥有环境的密码值。包含密码、盐的完整原行快照仅留在 runtime/config 的 600 私有文件，runtime 目录为 700，不进入仓库。

本测试执行真实 SFC/Mixin 方法，确认框、引用组件和表单使用窄 facade，HTTP 请求及 DB 检查是真实的；它不证明 Vue watcher、AntD checkbox 缓存、浏览器布局或人工验收。UserModal 没有在这组真实 HTTP 专项中执行新建/编辑账号写入。后台使用固定 JAR，本轮没有运行无关的全套后端回归。

复现时使用已经安装的 Node 26.7.0、Python 3.14.7，复用 `product-candidate/web/node_modules`，不安装或升级依赖。必须先以项目的 prepare-local.py/run-backend.py 创建并启动指定独占合成环境；Python 工具拒绝不同 runtime、端口、JAR 或旧源引用，拒绝覆盖证据文件。核心工具为 `api/dev/class-member-context-live.py` 与 `web/tests/class-member-context-live.cjs`，角色工具为 `api/dev/class-member-role-live.py` 与 `web/tests/class-member-role-live.cjs`。在本项工作树使用以下环境和参数，旧源加 `--ref 8f58b32362899047da0136e41278368fd26c88f0`，新源省略 --ref，--output 每次采用新路径：

```sh
NODE_PATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/web/node_modules \
PYTHONPATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/encoded-media-references/api/dev \
python3 api/dev/class-member-context-live.py \
  --runtime /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/class-member-context-1003 \
  --jar /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/encoded-media-root/author-build-20261003T131119Z/teaching-open-2.8.0.jar \
  --source /Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/class-member-context \
  --output /absolute/new-evidence.json
```

角色专项将命令的 Python 文件改为 `api/dev/class-member-role-live.py`。准确工具与产品 SHA、最终证据 SHA 见 [manifest](evidence/class-member-context/live-manifest.json)；服务停止及 PID/端口核验见 [最终清理](evidence/class-member-context/live-runtime-cleanup-final.json)。数据目录保留供追溯，原有长期 runtime 和生产副本未操作。
