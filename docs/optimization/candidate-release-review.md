2026-10-05 独立限定审阅结论：在明确可信源码、全新私有合成包和本机 Linux/arm64 容器的范围内，未发现尚未处理的 P1/P2 缺陷。此前发现的 P2“探针改变既有报告父目录权限”已修复，独立文件系统回归 8/8 通过；最终 fresh05 实际运行报告与修复后的同一份探针摘要绑定，45/45 通过。这里的独立性指另一个 Agent 对源码、拒绝路径及证据文件的核对；实际 Docker、HTTP、数据库与 WebSocket 执行由根 Agent 完成。

审阅对象为 `candidate-release-bundle` 工作树中的 `deploy/candidate_release.py`、`deploy/probe_candidate_runtime.py`、独立测试及公开说明。审阅者没有启动 Docker、访问 HTTP/数据库/浏览器、读取 bundle 内凭据、生产配置或真实生产资料，没有改动实现。唯一主动执行是下面的临时文件测试；唯一交付写入是本审阅记录。

冻结摘要逐字复算如下，独立测试运行前后均未变化：

| 文件 | SHA256 |
| --- | --- |
| `deploy/candidate_release.py` | `ee6eae518411b09290c68a81ab76c40a43f55c83c7e3e80ce5bff2417beb1f67` |
| `deploy/probe_candidate_runtime.py` | `68a7c76899de0490b1b0a2530dae8267841867d88ecf92dc5a2432f1de3f16dd` |
| `deploy/test_probe_candidate_runtime.py` | `622ebaf06dcaa1fdc051486cd726d258d5f3b5e88bbc4fe09df3d95fd3934785` |

原 P2 的具体触发是把 `--output` 放在已有目录中，旧探针无条件 `chmod(parent, 0700)`，可能改掉项目或共享目录的权限。最终 `prepare_output`（探针第 83 行）只接受已经私有、普通且允许所有者写入/遍历的父目录，或者创建新的 0700 父目录；拒绝已有公开目录、符号链接父目录、已有报告及悬空报告链接。它不修改既有目录权限，`main` 在构造 Probe 与任何运行操作前调用该检查（第 675 行）。报告最终以 `O_EXCL | O_NOFOLLOW`、0600 创建（第 659 行）。

独立运行命令为 `python3 -B -m unittest discover -s deploy -p test_probe_candidate_runtime.py -v`，exit 0，8 项全部通过，0 failure/error/skip，unittest 计时 0.005 秒。覆盖公开父目录拒绝并保留 0755、私有父目录接受并精确保留权限、创建新 0700 父目录、链接拒绝、已有报告字节/权限保持，以及 CLI 在 Probe 构造前拒绝。测试显式禁用探针 `run` 与 socket 操作，活动仅发生在测试拥有的临时目录。

工具边界和实际探针相符：

- `candidate_release.py` 第 47、117、284、376 行的输入路径、tracked clean source、create/verify 检查保留了显式输入闭包。工具只执行使用者明确选择的可信源码 helper；这不是运行不可信源码的沙箱。冻结 JAR、4893 个 dist 文件、Nginx、54 键模板与 helper 摘要受检查，但 manifest 不提供源码到 JAR/dist 的构建证明，也不抵抗操作者同时替换全部文件和 manifest。
- `compose_config`（第 222 行）只发布 web 的 loopback 端口，DB/Redis/API 仅加入 internal candidate 网络，web 额外加入自身项目的 ingress bridge；入口 bridge 具有正常出站能力。应用 JAR/dist/config 的输入挂载只读，持久数据属于新包。私有根目录隔离宿主其他用户；给官方容器读取的少量 0444 文件通过精确文件挂载提供，未把整个私有配置目录公开挂载。
- 探针 `preflight`（第 343 行起）在业务请求前执行同摘要工具的 verify，并检查自有 Compose 身份、精确双网络及成员、HostConfig 请求映射与 NetworkSettings 实际映射、镜像平台/ID和精确挂载。边界失败时不进入业务请求。这覆盖了先前“internal-only 网络配置写了端口但实际未发布”的真实失败。
- 配置、密码及原始响应不写入公开报告。Java 夹具密码和 Redis AUTH 经 stdin 传给受控子进程；探针 SQL 入口限定 SELECT（第 167 行）并用 hex literal 编码值，操作对象是已核对身份的自有容器。验证码读取只针对这次合成账号登录，公开说明准确限定为 API fixture 登录。
- 探针报告保留独立 case 的 pass/fail/not_run，异常只记 phase 与 exception class；group 异常不会把未执行用例算作通过，finally 退出已创建会话。合成 Python 草稿和附件在本包私有 data 中保留，课程/单元通过正常 API 删除验证；没有把保留的草稿伪称为完整数据恢复。

对实际证据的独立文件核对结果：

- `reports/runtime-04.json` SHA256 为 `073b4746b68d399df9b1b5efdb7dc0b43eac9d7528780b907ef7a38c08a821cf`，45/45，无异常；它绑定的是旧探针 `b1b0e370…`，只保留为历史结果，不作为最终修复版本的运行证据。
- `reports/runtime-05.json` SHA256 为 `7d796d7099fb7af58520245ce61f19cfbc18bc3af35f84c504e290a48f2056a3`。共 45 个不同 case，全部 `passed: true / status: pass`，failed 0、not_run 0、exceptions 空，all_passed true。审阅者重新计数并核对字段，没有只接受汇总成功字符串。
- `probe-05-execution.json` SHA256 为 `555a55908ed8b1b125be8cba91283ccda469c6417c85604163cb6f88e4271867`。exit 0，记录的运行前后摘要一致，正好对应上表最终 probe 和 generator；其 report_sha256 与上述报告原始字节复算值一致。
- fresh05 的 manifest 指纹为 `248981ca502091d46a45d739cbdda6d0dbe67484fb2717933267aa5931379b1f`，source 为 `8ad3f13db83fe7b48063c99c0f5d33ad42358c67`，JAR 为 `9eb18d42d365dd4fba7044d57ed33aaa0fdb543f8468dd67c10c9dc83de05869`，dist manifest 为 `0b38b4690bac046186f3f4127eb8dc666aada7e2a413216a1a1a917f4bf2d120`。
- 公开 `evidence/candidate-release/runtime.json` 和 `runtime-execution.json` 与 fresh05 原报告/收据逐字节一致。报告只含范围说明、状态、摘要与指纹；每个 case 字段限定为 case、passed、status、phase、http_status、body_sha256。公开尝试历史、版本日志、测试记录和 runtime-state 也未发现原始凭据、令牌、配置、响应体或生产资料。对测试/版本命令字段另行核对，未含秘密参数。
- create/verify 的 66/66 独立测试结果来自另一测试 Agent 的 `tests/final.json`，本审阅者复算该文件 SHA256 为 `f8cbc6916de7f0b5911b192d307d846d9be0909d224665d6318374b1fe3c7b20`，并核对其生成器前后摘要。审阅者没有重新执行这组 66 项，不把读收据等同于自己重跑。

45 项覆盖真实网络/挂载边界、Nginx → Java 健康与静态字节、五账号、三角色的登录和菜单、同班允许/跨班拒绝、管理员课程及单元 POST/PUT/DELETE 的 API 与数据库重读、学生写入拒绝、媒体 GET/HEAD/Range 原字节、中文路径 multipart Python 附件及个人草稿持久化/重读、附件归属与越权拒绝、媒体 Cookie 限制和退出撤销、实际 WebSocket 升级及认证响应。它证明这份本机合成候选的这些行为；Python 草稿接口写入不是浏览器编辑器保存/执行/最终交作业验收，媒体字节一致不是浏览器完整播放验收。

公开说明已校正 MySQL 文件系统边界：根 Agent 的 post-run SQL 记录为 MySQL 8.4.6、`lower_case_table_names=2`、69 表、五个合成用户；运行状态记录也一致。审阅者只读核对该记录，未独立执行 SQL。Linux/arm64 镜像运行在 Mac 宿主 bind 目录，不证明大小写敏感 Linux 文件系统下参数 0 的兼容性，也不证明实际 Z820、生产部署、TLS、容量、普通浏览器登录、用户人工验收或源代码到产物的构建重现。

自有容器停止与网络删除由根 Agent另行记录；本审阅不以运行时 running 快照证明清理完成，也没有扩大为重启恢复或生产交付门槛。最终产品 Goal、PR 提交/推送/合并及部署状态由根 Agent单独报告。
