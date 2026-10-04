# 真实课程媒体证据独立窄审（2026-10-05）

结论：本次实际离线报告的分母、状态计数、统计与样本资产均一致，未发现解析失败被隐藏或移出总分母。证据支持 **211/211 个 MP4/PDF/Markdown 文件完成离线结构或元信息解析**；另有 **86 个 JPG/PNG 仅清单核对**。它不支持“297 个媒体兼容通过”或任何真实浏览器播放/渲染已经通过的结论。本轮尚未收到浏览器最终结果。

## 审阅范围与版本

只读审阅工作树 `.devspace/worktrees/production-media-compatibility` 的新增 Python 模块、CLI、测试源与作者说明，基线 HEAD `3483f3a3729ad84b359db43dfe93e03fa4e32c0e`。读取指定运行的安全 `summary.json`、仅含匿名 ID/元数据的私有 `report.json` 和 `real-media-browser-20261005/selection-summary.json`。没有读取 `selection.json`、真实媒体正文/资产、数据库、服务或浏览器；没有运行审计器或重跑测试，没有修改实现、PR 文档、goal 或 root 记录。唯一新增文件是本报告。

- 实际报告目录：`.devspace/prod-fixture-1003/reports/media-audit-97884e1289a045afa647ebed8816299d`。
- 私有 `report.json` SHA-256：`33d1f917977c06028c2f80d80aee13ffde35b7d84d21576a2e145f6df4eb4c34`，与 selection-summary 的 `source_audit_sha256` 精确相符。
- 当前模块 SHA-256：`ad102c2c28f511efe7e55e44a87aded228ab6bc0842cf629c10aeed74c913bd1`。
- 本次实际运行模块 SHA-256：`b4bc63664ee603cc70b784ff856c728b3712b3ab4b20cb1ceb2ccbc4fc6547b3`。独立在内存删去当前模块中唯一精确的 `Markdown headings count ATX-shaped lines; no complete Markdown syntax parsing` 局限字符串行后，重算完全得到该运行摘要；没有写回文件。该差异仅增加 report.limitation 说明，审计计算与 summary 不变。不能因此声称最终 ad102c 版本已经执行真实全量审计；可明确将本次 b4bc 实际证据映射到同一实现逻辑，并披露文案变化。
- 当前 CLI 与本次运行摘要均为 `79a06cc4e86747e1b338b03bdf33a091b5d51569810e2bb7c19eda057350e2b1`。
- 已读取测试源的失败保留、变更后复核、代表选择、报告排他创建、CLI 输出及可选真实解析器夹具断言；此处是静态测试审阅，没有独立执行通过声明。

## 实际分母与失败保留

`report.summary` 与独立 `summary.json` 完全相同。297 条 record 有 297 个唯一匿名 asset_id，状态重算如下：

| 资产类型 | 总数 | passed | inventory_only | failed |
|---|---:|---:|---:|---:|
| MP4 | 83 | 83 | 0 | 0 |
| PDF | 45 | 45 | 0 | 0 |
| Markdown | 83 | 83 | 0 | 0 |
| JPG | 83 | 0 | 83 | 0 |
| PNG | 3 | 0 | 3 | 0 |
| 合计 | 297 | 211 | 86 | 0 |

记录总字节数为 5,941,586,119；与 safety.before/after 的文件数、字节数一致。before 与 after 的 stat inventory 摘要一致；`binding == safety.binding_after`；报告声明 `unchanged=true`。这些是报告/元数据内部一致性核对，不是本审查重新读取原文件验证内容未变。

源码 `audit()`（537–557）对每个白名单文件追加一条 record，MP4/PDF/MD 解析异常写 failed/error_code，未支持类型也写 failed。之后在 finally 复核快照（558–571），将结束复核错误另计入 failures，即使解析曾失败也不跳过复核。counts.failed 是文件失败数；failures 还可能包含一次结束复核错误，二者不要求永远相等。`_statistics()`（469–495）只聚合 passed 元数据，summary 的总量/状态与 failures 仍包含失败文件，这个统计筛选没有隐藏总分母。本次实际 `failed=0`、所有 record 无 error_code、failures={}，并无这种计数歧义。

测试源 `test_parse_failures_and_unsupported_assets_remain_in_denominator` 明确构造 5 个资产、3 个失败并断言全部留在 records；`test_failed_parser_still_checks_changed_private_configuration` 区分 1 个解析失败和 1 个结束绑定失败；同大小文件变更检查也保留 record。这些是相关的反例断言，而非只验证当前成功输出。

## 元数据与样本复核

独立根据 record 元数据重算全部 summary.statistics，结果全等：MP4 编码/profile/音频组合、布局、字节/时长极值；PDF 页数、加密、版本、字节极值；MD 字节/行数/ATX 形状行/换行计数。实际 MP4 是 83 个 H.264 High、AAC 单声道，moov 在 mdat 后 60 个、前 23 个。时长 51.633333–558.634167 秒、大小 18,052,955–96,459,689 字节；PDF 4–30 页、无加密；这些只是观察值，moov 后置本身不是解析失败或已证明的播放缺陷。

作者说明准确限定 `headings` 为 ATX 标题形状行，未解析代码围栏和 Setext，不能当完整 Markdown 标题语义；本次旧报告缺这一局限字符串，当前模块和作者文档已补说明。JPG/PNG 没有图片解码；MP4 没有全量解码；PDF 没有页面渲染。来源文件内容摘要仍是绑定的 acquisition claim，审计 safety 明确 `full_asset_content_hash_performed=false`。

离线模块自动选择 7 个匿名资产（4 MP4+2 PDF+1 MD）。浏览器阶段 selection-summary 选择 8 个唯一资产（5 MP4+2 PDF+1 MD），含离线全部 7 项，另加 1 个 MP4，reason=`additional_course_coverage`。这两个分母属于不同阶段，不能把 summary.selection_counts 的 4 MP4 写成浏览器选择的 5 MP4，或把多出的 1 项称为离线算法已自动选择。

8 个选择项都在实际 report 的 passed records 中，kind 对应一致。可以独立复核的理由均成立：codec/audio/layout、最长视频、最大视频、最多页 PDF、最大 PDF、最多行 MD。selection-summary 的 `video_course_coverage=3`、`available_courses=3` 和 `selected_full_content_hashes_match_manifest=true` 是 root 选择阶段汇总声明；允许读取的文件没有匿名课程映射，也没有所选实际资产本次重算 hash。因此本审查不把课程 3/3 与所选完整内容散列一致升级为独立复验。

## 窄范围可执行建议

未发现阻止工具合并的代码问题。最终交付需要保留以下证据界限：

1. 将离线结果写为“297 个资产清单；211 个文档/视频元信息解析通过；86 个图片未解码”，并披露 b4bc 运行版本与 ad102c 文案差异。不要写“全部媒体兼容通过”或“最终模块真实重跑通过”。
2. 浏览器结果按 `sampleXX + asset_id + kind + 具体行为结果` 绑定到样本。现有 selection-summary 的 selected 项与 html_checks 没有 asset_id↔sampleXX 映射；8 个 HTML sample ID 唯一，但正文 hash 只有 7 个唯一值。重复正文不证明资产重复（资产确有 8 个唯一 ID），也不能把 HTML 检查当作 8 个媒体验收。后续保留 safe 映射即可，不需公开标题、路径或正文。
3. 若最终要宣称 3/3 门真实课程覆盖，可在安全汇总中保留匿名课程标识/分母计算来源，以便核对新增第 5 个视频的课程覆盖理由。当前仅说“root 选择汇总报告覆盖 3/3”，并保留其证据等级。
4. `active_content_found=false` 是 HTML 检查器的阶段结果，不能推广成任意 HTML 安全证明，也不替代视频播放、seek、音轨、PDF 渲染和 MD 展示的真实浏览器证据。本轮浏览器最终结果尚未核查，仍待 root 单独收束。

上述建议仅收束报告和后续证据绑定，不要求扩大工具实现或增加网络、生产访问或全量内容读取。
