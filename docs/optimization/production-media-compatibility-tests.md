# 媒体审计独立受控测试记录

2026-10-05，独立测试 Agent 在该功能 worktree 中执行 `python3 api/dev/test_production_media_audit.py -v`，33 个测试方法全部通过，0 失败、0 错误、0 跳过。测试使用本 Agent 创建并负责清理的临时目录、临时文件和临时子进程。没有读取已有课程媒体，没有连接应用、MySQL、Redis、浏览器或外部服务，也没有安装工具或提交媒体二进制文件。

这份记录覆盖工具的受控行为与守卫审查。真实私有快照的审计由主 Agent 单独执行和记录；本记录不代替真实数据解析、浏览器验证、人工验收或生产行为验证。

## 本次冻结

| 文件 | SHA-256 |
| --- | --- |
| `api/dev/production_media_audit.py` | `ad102c2c28f511efe7e55e44a87aded228ab6bc0842cf629c10aeed74c913bd1` |
| `api/dev/audit-production-media.py` | `79a06cc4e86747e1b338b03bdf33a091b5d51569810e2bb7c19eda057350e2b1` |
| `api/dev/test_production_media_audit.py` | `c4a6a8d9a76ce9de0617728a4be3fd0848a0132d9fe0492921a6283fe78f86a2` |

最终测试进程退出码为 0，unittest 报告为 `Ran 33 tests` / `OK`。统计单位是测试方法，参数化子用例不额外计入 33 的分母。

## 已覆盖的行为

- 私有快照守卫：完整的受控 manifest 可以通过；源导出/生产 live 标记、错误 runtime/datadir、缺失或错误源摘要、schema policy 改变、学生附件标记、恢复 session 标记、bool 冒充整数均被拒绝。初始守卫失败不会启动探测器或创建报告目录。
- 普通文件与白名单边界：路径穿越、runtime/metadata/asset 符号链接、额外文件、FIFO、公开权限、已绑定私有文件变更，以及资产数量/字节/记录字段不匹配均被拒绝。重复 JSON key 与过大的元数据在解析边界被拒绝。
- 工具路径：仅接受绝对真实路径、普通文件、可执行权限和正确的 `ffprobe` / `pdfinfo` 文件名；符号链接入口和错误文件名被拒绝。
- MP4 结构：区分 moov 在 mdat 前后，观察实际 top-level moof；接受有界 extended-size 与末尾 size=0 mdat；拒绝截断、过小/越界 size、子 atom 越过父边界、缺少必要 atom 和外部 dref。外部 dref 在启动媒体探测器前拒绝。对自造含 mdat 的容器，头部读取计数小于文件总字节数。
- 探测器结果：字段只保留元数据；标题、tags、文件路径和诊断标记不进入结果。无效 JSON、无视频流、非正常尺寸与无效 PDF 页数不被当成成功。
- Markdown：严格 UTF-8、UTF-8 BOM、NUL、读取大小上限、字节保持与换行/ATX 行计数。这里没有验证 Markdown 渲染、代码围栏语义或 Setext 标题。
- 子进程：真实受控 Python 子进程覆盖正常退出、异常退出、启动失败、超时、stdout/stderr 各自上限和 stderr 丢弃。特别覆盖了 leader 已退出但后代仍持有 pipe 的情形；失败后实际调用 SIGKILL 终止该进程组，测试创建的后代在清理范围内。
- 代表样本：输入乱序和并列极值保持结果稳定；覆盖视频 codec、音频通道/无音频、moov 布局，补最长/最大；失败记录不入选。视频/PDF/Markdown 分别限制在 5/2/1 项，PDF 最多页和最大文件优先，Markdown 并列时使用稳定身份。
- 失败分母：一个受控 5 文件混合集合得到 assets=5、media_checked=3、passed=1、failed=3、inventory_only=1。损坏 MP4、PDF 超时和不支持类型都保留在记录与固定错误码计数中；失败不能减少审计分母。
- 前后复核：同大小的 Markdown 改写并改变 stat 后，结果 passed=false / unchanged=false。解析已经失败时仍复核配置，解析失败码和配置绑定失败码同时保留。终止复核错误独立于媒体失败数，不能把 `counts.failed=0` 解释为整体通过。
- 私有报告与 CLI：新报告目录为 700，JSON 文件为 600；固定目录 ID 冲突会失败且旧字节不被覆盖。summary 不含逐资产记录/身份，私有完整报告也没有原路径/原文。CLI 成功与守卫失败输出都没有测试路径、内容、凭据标记或 traceback。

## 真实解析器在自造文件上的证据

本机已有的真实 `ffprobe` 与 `pdfinfo` 通过解析后的实际普通可执行路径调用，没有下载或安装。测试不是只 mock 探测器返回值：637 字节的自造 ISO BMFF 文件被 ffprobe 识别为 H.264、64×64、时长 1 秒；429 字节的自造 PDF 被 pdfinfo 识别为 1 页、未加密。工具 API 返回了相应元数据，两个文件前后 SHA-256 相同。

MP4 fixture 只有视频轨道元数据，媒体样本数量为零。这证明探测器调用与元数据提取能工作，不能证明视频解码、播放、seek 或音轨行为。PDF fixture 是空白的单页文档，只证明 pdfinfo 页数/版本/加密字段提取，不能证明真实课程 PDF 页面渲染。运行环境没有探测器时这项测试会显式 skip；本次实际运行没有 skip。

多数 audit 流程测试使用 Markdown 或 mock 解析失败，并使用自造普通可执行占位文件验证工具路径与哈希绑定。这些受控流程与上一段真实解析器测试分别表述，不能把占位工具的路径检查当成真实解析成功。

## 守卫审查与证据限制

独立审查核对了审计入口顺序、snapshot 私有文件白名单、资产普通路径检查、固定探测参数与错误处理。入口没有调用访问服务的 fixture verify/SQL；ffprobe 使用 mov demuxer、file 协议白名单、关闭 drefs 与 absolute-path 引用。子进程不使用 shell，清理继承环境后执行；stdout/stderr 有独立字节上限与超时。未发现阻止对已授权私有快照开展离线元数据审计的当前守卫问题。

审查中关注的“leader 已退出后仍有后代 pipe”清理路径已经通过回归。首次探测输出测试发现存在负数视频尺寸时会被转成 None 并继续通过，作者已改为拒绝存在的非法尺寸，冻结版本的回归通过。缺失但可选的元数据仍可记录为 None，并不自动提升为格式兼容。

manifest 的 source_sha256 与逐资产 source_sha256 是已绑定的获取声明；本工具没有重新验证所有媒体的内容散列。前后防变更证据来自全 uploads stat inventory 与 manifest/config/schema 绑定复核，不能表述成全量内容字节未变。资产获取 manifest 与 snapshot source manifest 的摘要语义分别保留，不要求两者恰好相等。

所有受控 fixtures 都在临时目录内清理。该记录只有可公开引用的测试设计、计数和代码摘要，未收录真实课程原文、原路径、课程身份或凭据。独立 Agent 测试与主 Agent 自检、真实数据解析、其他设备复现和人工验收分别判断。
