# 学生作品反馈可读性独立审阅

结论：冻结的四个产品文件解决两个实际学生作品入口的反馈可读性问题，独立离线测试 **20/20 通过**。当前无产品修复 blocker。浏览器 DOM、AntD 动画/焦点和窄屏布局归主代理 CUA，本报告不把离线结果写成人类验收。

## 对象与输入契约

作者工作树 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/student-feedback-readable`，基于 `c2c3eacbe54a1a44314c83f17e4d27027686553a`。四个产品文件为 `web/src/components/teaching/StudentWorkFeedback.vue`、`web/src/utils/studentWorkFeedback.js`、`web/src/views/account/center/MineWorkList.vue`、`web/src/views/account/center/page/MineWorks.vue`。最终审阅提交为 `f8071b1ba1a955a1fff517a57212e52e85babc22`，已核对工作树 clean、实际测试源与提交 blob 字节一致。缩进修正后的最终源码重新执行 20/20；首次冻结报告保留为 `feedback-offline-frozen-v1.json`，没有覆盖历史证据。`feedback-offline.json` 和 `final-source-manifest.json` 保存最终测试源及提交 SHA-256。候选集成 `69002a1450306e73f13c7d0763d026dad7b8c335` 的四个产品文件逐字节相同；这是只读源一致性核对，正式候选 test/build 由主代理执行。

已核对 `/teaching/teachingWork/mine` 的 controller、service、mapper、StudentWorkModel：列表每行反馈是 nullable Integer `score` 与 nullable String `teacherComment`，没有 teacherFeedback 数组。0 是有效评分；教师批改端允许 0–5 整数或仅评语。最终容错支持 trim 后单个 0–5 数字字符串；空白、布尔值、数组、对象、超范围、非整数和 hex/exponent 等格式非法输入不转换成零分。

correct 表 LEFT JOIN 与完整行 DISTINCT 没有按作品 id 聚合，也没有最新反馈排序；多条不同反馈仍可能形成同 work.id 多行。教师编辑器另外读取 correct 数组、编辑第一条并保留其余，该 SQL 同样没有 ORDER BY。本次 UI 呈现该行已有反馈，不声称最新或全部评语，不新增请求、合并反馈或改后端。详见 `input-contract.md` 的精确源位置。

## 真实调用方与改动核对

- `MineWorkList.vue` 的实际表格 scoreInfo slot 用当前 row 挂载真实 StudentWorkFeedback，保留 mine 接口及既有 CRUD；原 Tooltip + disabled Rate 被可见数字/未评分、评语摘要和原生 button 替代。表格必要的窄屏滚动/焦点入口及原生操作按钮没有更改原处理函数或接口。
- 默认账号中心 `Index.vue -> page/index.js -> MineWorks.vue` 仍是原卡片映射，卡片以当前 item 接入同一反馈组件。独立探针编译真实 Index、读取 page 导出并实例化其实际注册的 MineWorksCard；没有用表格替换父映射。
- shared 组件没有编辑评分、改密或反馈写入路径。全文按 Vue 文本节点渲染，没有 v-html；modal 标题关联 workName，详情保存反馈快照。无评语不给空的打开按钮；仅评语保留“未评分”和可读内容。
- props 替换、同作品反馈更新、销毁都会清旧 detail。正常关闭仅在 modal afterClose 清理并恢复仍连接的 trigger focus；当前 visible=true 时的旧 afterClose 不清新内容，也不抢焦点。不会声称已通过真实浏览器动画测试。

## 独立执行的证据

`feedback-offline.cjs` 使用当前本机真实 Vue、vue-template-compiler 与实际 SFC 的 script/render 函数。JeecgListMixin 也加载真实源码；API transport、无关导入及焦点目标为 stub，没有使用 DOM、AntD portal、HTTP、数据库或服务。测试通过真实按钮/cancel/afterClose VNode handler，并对实际两个父级的反馈 props 做检查；没有重新实现反馈算法后测试自己的镜像。

基线 `--baseline` 从精确 base Git blob 读取：**2/2** 确认表格将评语仅放在 Tooltip title、Rate disabled 且无可操作读评语 button，以及真实 Index 卡片没有任何反馈显示。记录在 `baseline-offline.json`。

最终 **20/20** 覆盖：0 与 '0'、1–5、null/undefined/空白/布尔/非法分、仅评语/无评语、长 Unicode 与换行、类似 HTML 的原样文本、实际原生按钮/作品标题/全文、关闭与连接焦点恢复、旧关闭回调后的重开、不同作品/同作品反馈更新、移除组件、两个实际父接线及列表替换、表格方向键不抢嵌套控件事件、无额外反馈/变更请求。`feedback-offline.json` 保存逐项结果和测试源 SHA。

草稿真实缺陷已保留在 `draft-race-probe.json`：shared 源 SHA `9d07f781e79f6f11fc3d414f234a3daebc7e0bb053bf285bc210ce809fec056c` 的 open→close→reopen→旧 afterClose，使 visible=true 而 detail=null；另记录 '0x0'/'0e0' 被旧 Number 分支解释为 0。作者已分别增加 visible 防护和严格字符串边界。后一项是明确容错边界，正常 Integer mine 返回并不会生成这类字符串，不能把它描述成当前后端数据已存在的问题。

探针开发中的两个 harness 问题已校正：真实父级会响应式观察 row，所以原地字段更新测试使用 Vue.observable；AntD table 的 `.native` 事件位于 VNode nativeOn，而非 on。此前这些 harness 红例不作为产品缺陷证据。

## 范围与剩余限制

本审阅者没有修改产品或工作树、调用浏览器/HTTP/DB/服务。只在 `.devspace/artifacts/student-feedback-20261005/review` 写输入契约、独立测试与报告；没有重复账号恢复中断专项。

本报告证明源码与离线输入/状态/接线行为。读取的主代理 `browser/final-report.json` 另记录真实 Vue/AntD 的 CUA 与只读合成 HTTP：390/768/1440 布局、键盘全文按钮、Esc 返回焦点、纯文本 HTML、长评语和表格局部滚动。预览外壳替代认证 BasicLayout，不能描述成真实登录平台验收。报告记录第一版预览缺全局 ellipsis filter，after-final2 注册真实 utils/filter 后 fresh origin console warning/error 为 0；父 SFC 此后仅缩进调整并通过本次 20/20，后续 final3 的视觉衔接由主代理记录。作者测试/构建与主代理浏览器结果分别归属各执行者；本审阅者没有运行 CUA 或复现这些 DOM 指标。没有真实学生账号、真实教师批改、多反馈 DB 数据的完整链路验收。

本次不解决既有列表请求竞态、重复作品 id/多 correct 行聚合或教师反馈选择顺序，也不推广为 CRUD、权限或安全扫描。保留这个边界不会削弱当前“可见得分与可操作完整评语”修复的结果，但应避免作更强产品承诺。

## 最终 diff 与阻断结论

已阅读实际四产品源码、两个 caller 的完整 diff 和作者测试/预览/交付说明；最终提交只含四产品文件、一份作者说明、九个测试/预览文件，共 14 文件。`api/`、真实 Index 与 page 导出映射对 base 无变化，没有引入依赖或额外反馈请求。最终独立离线回归 20/20，所有七个测试源（含未改的 mixin/Index/page 导出）与提交 blob 相同，候选四产品源相同。当前无 blocker 或需补产品修复的已证实问题。既有多 correct 行语义和完整真实账号批改链路仍是上述范围限制，不作本次新缺陷。
