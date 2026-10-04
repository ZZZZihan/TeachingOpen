# 私有课程资产离线兼容性审计实现

该工具在现有私有快照内进行文件审计。它不启动应用、不访问数据库或 Redis、不登录、不创建浏览器服务，也不修改已有课程文件、配置或清单。审计仅新增 `runtime/reports/media-audit-<随机 ID>/`，目录权限为 700，两个 JSON 报告为 600，采用排他创建，不覆盖既有结果。

入口为 `api/dev/audit-production-media.py`。参数固定为 `--runtime`、`--ffprobe`、`--pdfinfo`。runtime 必须是绝对路径、现有私有目录、`.devspace` 的直接子目录，并且所有路径组成不得是符号链接。两个探测器要求已经存在的真实可执行普通文件路径，文件名分别为 `ffprobe` 和 `pdfinfo`；Homebrew 的符号链接入口应由操作者先解析为现有真实路径。脚本不安装依赖或下载工具。

运行前验证生产快照的 format/kind/complete、runtime/datadir/ports、源文件摘要格式、当前 schema policy 摘要、固定八项 private_files 摘要及权限。assets-result 的记录必须是 `relative -> {bytes, sha256}`，总数与总字节数准确，学生文件复制标志为 false，非原子复制标志为 false。uploads 的实际普通文件集合必须与该课程资产白名单一致，路径穿越、编码路径、符号链接、特殊文件、意外文件均拒绝。这里不调用会访问服务的 `production_fixture.verify()`，也不重新读取外层源数据库备份或对全部媒体做内容散列。

本版还要求 uploads 根目录及其所有中间目录的 group/other 权限位为零，文件同样必须私有。历史 `copy_assets()` 使用 `mkdir(parents=True, mode=0o700)` 时，Python 对缺失中间父目录可能使用默认权限，因而旧快照存在中间目录 755 时会被本版拒绝。这是当前工具的明确前置限制；工具不替操作者 chmod，也不自动放宽。当前审计是否通过应以对应 runtime 的实际报告为准，不能推广到其他历史快照。

MP4 先使用 seek 读取有界 atom 头与 dref flags，判定 moov 是否在首个 mdat 之前。扫描最多 4096 个 atom、128 KiB 头部字节、8 层递归，校验截断与 size 字段。外部 dref 检查实际覆盖标准 `moov/trak/mdia/minf/dinf/dref` 层次；它不是通用容器安全证明。ffprobe 固定 mov demuxer、file 协议白名单、enable_drefs=0、use_absolute_path=0，仅索取编解码器、profile、尺寸、pixfmt、时长、帧率和音频通道等字段，不索取标题、tags 或正文。

探测器均以无 shell 参数调用，串行处理，单进程超时 20 秒，stdout 上限 512 KiB，stderr 上限 64 KiB。超时、输出超限或异常退出终止并回收子进程组；原始 stdout/stderr 不进入报告或终端。PDF 使用 pdfinfo，只保留页数、是否加密、PDF 版本。Markdown 至多读取 4 MiB，严格 UTF-8/UTF-8 BOM 解码，拒绝 NUL，只保留字节、行、ATX 标题形状行及换行计数；没有解析代码围栏或 Setext 标题，计数不是完整 Markdown 渲染语义。JPG/PNG 保留文件清单与 stat 证据，图片解码仍待验证。其他类型记为失败。罕见 codec、profile 或 moov 布局作为观察值，不单独判失败。

报告契约冻结为 format=1。私有 report.json 的 kind 为 `teachingopen-private-media-audit`，包含 summary、records、representatives、limitations；records 仅使用 `sha256(relative UTF-8)` 的 asset_id，不保存原路径、课程 ID 或内容。source_sha256 来自已绑定的 assets-result，是获取时的内容摘要声明。脚本本次没有证明所有媒体的内容摘要仍一致。

summary.json 与终端输出的 kind 为 `teachingopen-private-media-audit-summary`，只含 counts、extensions、固定错误码 failures、statistics、binding、tool_binding、safety、selection_counts 和报告目录名。safety 的 before/after 比较全部 uploads 文件的数量、字节和 stat inventory 摘要，且复核清单、配置、schema policy 的摘要；这些 stat 摘要与完整内容散列证据分开。处理失败后仍执行复核，再写出 completed=true / passed=false 的私有结果。初始 guard 失败时不执行探测器且退出 1；解析或复核失败同样退出 1。全程不输出异常原文。

样本选择按稳定 asset_id 排序，MP4 先覆盖 codec/audio/layout 差异，再补最长和最大，共最多 5 项；PDF 优先最多页和最大文件，剩余槽位补最少页/最小文件，共最多 2 项；Markdown 选择最多行的 1 项。原因写入私有报告，课程分布和浏览器路线由后续审计者在内存中映射，不在此脚本中查询。

这些结果只能说明离线结构和元信息解析。真实浏览器播放、跳转、音轨行为、PDF 渲染、Markdown 页面展示，以及所选样本的完整内容散列仍是后续独立门槛。探测器 flags 的当前安装版本兼容性也需要操作者在实际工具路径上验证。
