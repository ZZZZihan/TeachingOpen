# 学生作品加载恢复独立审阅

当前结论：after3 冻结后的四个产品文件实际 Vue/SFC 离线回归 **35/35 通过**，当前无源码/离线 blocker。首次 34 项报告保留。主代理 after2 CUA 发现的卡片 Less 网格简写和 AntD 分页同步卸载问题已修复；读取的 after3 CUA 报告记录实际布局/分页恢复通过，单独归主代理执行。最终审阅提交 `e3522dbc57e10330cbe697ac310e5106231f7aea`，工作树 clean；候选集成 `872109fde9020ab5ad8e42a9cc445f06224589dd` 的四个产品文件，其提交 blob 与当前工作字节均等于本次已测试源。正式候选测试/构建归主代理，未由本审阅者执行。本审阅者没有修改产品、调用浏览器/HTTP/数据库/认证/服务，仅在本私有 review 目录写测试与记录。

## 对象、契约与基线

工作树 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/student-work-loading`，base `f0980ce2d8c8a06e635bf09aca3a8b7d16edbcb7`。目标为真实 `MineWorkList.vue` 表格和真实 `Index.vue -> page/index.js -> MineWorks.vue` 卡片，不替换 Index 映射。新增 `StudentWorkListState.vue` 与 `studentWorkList.js` 复用显示/输入契约。作者 after3 manifest SHA `c33ce3380564a252d606c1e2c4cfc37d0e68eb47de7e9c4d2e5b26e83246ba59`；独立逐文件核对 424 个当前 src 与该冻结清单一致，没有缺失/变更/额外文件；全部十个实际测试源也与冻结一致。`final-source-manifest.json` 保存冻结清单、十个测试源与提交 blob 一致、候选四产品字节一致的证据。

两入口的既有 GET `/teaching/teachingWork/mine` 正常返回 success=true、分页 records 数组与数值 total；网络/HTTP 失败 reject，业务 false resolve。表格实际 JeecgListMixin 的 created/search/page/sort/CRUD 刷新仍路由到局部 loadData；真实 getQueryParams/filterObj 产生查询、排序、field 与 pageNo/pageSize。正常反馈仍为 #71 的 score/teacherComment 与原共享反馈组件。精确源码见 `input-contract.md`。

base Git blob 的独立离线基线 **8/8 预期缺陷复现**：两个入口各自复现网络拒绝/异常成功体后 loading 卡住、业务失败与成功空列表不可区分、旧 success 覆盖新结果。基线中未处理拒绝由测试进程捕获并写入 `baseline-offline.json`，不描述成新版通过。

## 实际 diff 与审阅触发修复

两个 loader 在请求开始清旧 rows/error/ready，表格同时清旧 selection/total；仅当前 requestId 且未 dispose 的请求提交 success、catch、finally。学生只能把成功空 records 看到为空态；失败显示固定本地错误和原生重试按钮，不回显 raw provider/server 文案。响应契约检查严格 success=true、数组 records、对象 row 和有效 id、number 非负 safeinteger total；空 records/正 total 是合法空页。

表格 lastListParams 保存请求参数的独立副本。重试使用失败请求 snapshot，连同页码/页大小保留；失败后只编辑尚未提交的 form 输入不会偷偷改变 retry 请求。显式查询仍采用新的 form 参数并回第一页。测试还修改 transport 收到的真实参数引用，确认 snapshot 不被外部写入影响。

审阅发现既有 mixin.batchDel 成功调用局部 loadData 后，其无条件 finally 会写 loading=false，可能提前清新 loader 状态。主代理明确批准局部 listLoading 隔离；作者用它绑定状态/aria/table/retry，保留 loading 兼容旧 mixin，没有修改全局 mixin 或 CRUD。独立测试直接写同一个 loading 标志，确认列表仍 pending；没有调用删除操作。

主代理另发现早期隐藏表格条件会在合法空页且 total>0 时失去分页恢复入口。最终保留该情况下的真实 table/pagination，显示“当前页暂无作品”；独立测试由 current=4/total=23 空页，经实际 handleTableChange 切回第一页并收到数据，不改页码策略或 CRUD。

主代理 after2 的真实 CUA 发现新增 `.list-state { grid-column: 1 / -1; }` 被 Less 算成 `-1`，状态区落到隐式网格列。该布局问题不在本审阅者离线 VNode 范围内；根已要求拆为 grid-column-start/end，并在 after3 复核。另有真实 AntD 分页 change 后，其 nextTick/getBodyTable TypeError：局部 loadData 立即使 a-table v-if 卸载；作者按根要求保持实例。离线新增第 35 项仅检查真实 table VNode 在 page-change pending 仍存在且 tag/key 稳定；AntD 的真实 DOM 回调仍归根复验。目前源码已使用 grid-column-start/end 与 table v-show，第 35 项离线回归通过；读取的根 after3 报告记录跨列恢复及 empty-page2→page1 实际分页无原 nextTick 错误。最终冻结后完整 35/35 复跑已经执行，不能用旧 34/34 掩盖先前视觉/DOM 失败；这两项实际 DOM 复验属于根，非本审阅者测试。

## 独立实际测试

`loading-offline.cjs` 在实现出现前先记录 `offline-protocol.md`，加载实际 Vue、template compiler、JeecgListMixin、util.filterObj、两个父组件和真实 Index/card mapping。新版状态 SFC 用真实 script/render/props；点击其实际 native button，由实际 Vue `$emit` 接回父 loader。transport 只为 deferred Promise stub，没有复制 loader/验证器算法、没有 DOM/AntD portal 或真实请求。

35 项实际行为回归（详见 `loading-offline.json`，首次 34 项结果保留在 `loading-offline-frozen-v1.json`）：

- 两入口初始 pending、成功空列表、正常 score=0/评语真实 props 接线；刷新时移除旧 rows，表格清 selection/total。
- 两入口网络 reject、HTTP500 型 reject、timeout、business false/code510 各自收敛并经 native retry 恢复；raw 错误细节不出现在状态文本。
- 两入口各对 21 种 malformed body/row/total 顺序重试；无 unhandled rejection；有效非空恢复后错误/空态消失。
- 两入口旧 success/旧 reject 在新 success 后不覆盖；旧 success/reject 的 finally 在新请求 pending 时不能 settle；新 error 不被旧 success 吞掉。
- 两入口销毁后 success/reject 不写回 data/error/ready/loading，也不能再次发送 load。
- 表格未查询输入编辑后的 failed snapshot/page 重试、transport 参数引用隔离、空页正 total 的分页恢复、既有 loading 标志对局部列表 owner 的隔离。
- 实际分页 change 开始请求后，table VNode 仍存在且 tag/key 相同；它证明局部接线，不证明 AntD DOM refs/动画。

state 组件为独立真实 Vue 子实例；Vue props/事件/响应性与生命周期执行是真实的，DOM mount/patch 和 AntD 状态控件渲染没有执行。请求顺序测试显式 resolve/reject；HTTP500/timeout 对象仅对应静态 axios 拒绝契约，并非实际 HTTP 实测。作者测试、根 CUA/故障服务以及正式组合构建分别记录，不能合并成本审阅者证据。

## 主代理浏览器证据归属

已只读读取 `browser/final-report.json`，其 after3 manifest SHA 与独立冻结核对相同。该报告分别记录 390/768/1440 布局、原生键盘重试/失败查询 snapshot、成功空页分页恢复、HTTP/业务/异常数据/网络/短 timeout 场景、迟到响应、重试后的原反馈弹窗，并记录当前 origin 过滤后的 console 为空。它明确使用实际 Vue/AntD 和冻结 src、只读合成 HTTP；认证外壳、全局 HTTP 拦截器和 tag 失败未覆盖，合成 timeout 1.2 秒，产品 60 秒不变。本审阅者没有 CUA、HTTP 或 DOM 操作，只检查这份报告的证据边界，不把它改写为真实学生端验收。

## 范围限制

已只读核对 backend、global mixin、request/manage、util.filterObj、真实 Index/page 导出及 #71 反馈组件/helper 相对 base 无变化。CRUD 方法/URL 沿用；本轮没有改变批改、权限、认证、加载超时时间或取消网络请求。请求 owner 隔离只保证本组件状态；既有全局 HTTP 通知/认证拦截器仍独立运行。

卡片已声明 pageSize=12/onChange 但未接 UI 分页，原请求 params=null 仍使用后端默认 999，这是已有待办；不要求本 PR 包办。表格 ancillary getWorkTags 和其他既有 CRUD 请求不在 mine loader 协议内；本报告不声称已统一所有异步状态。真实登录、真实学生数据、真实教师批改链路、浏览器 DOM/键盘/响应式视觉与生产验收仍须各自证据。

## 最终审阅结论

最终提交相对 base 仅四产品文件、一份作者说明、十个测试/预览文件，共 15 文件。已阅读实际四产品源码/两个 caller diff、作者 28 项测试、旧反馈测试必要适配、合成预览与作者说明。after3 冻结后独立完整复跑 35/35，十个实际测试源均与最终提交 blob 相同；424 个 src 与冻结 manifest 相同，候选四产品源相同。当前无 blocker，既有卡片分页/标签查询/全局通知及真实账号链路仅按上述范围限制保留。独立离线、作者分支测试、根 CUA 与候选正式构建各自归属，没有互相替代。
