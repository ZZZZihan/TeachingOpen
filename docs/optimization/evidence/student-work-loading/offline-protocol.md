# 独立离线验证协议（实现出现前记录）

测试对象为实际两个入口 SFC、真实 Index/card 导出映射、真实 JeecgListMixin 与 filterObj；请求 transport 仅为可手动 resolve/reject 的 Promise stub。不会发送真实 HTTP。新状态组件存在时编译其真实 template/script，实际原生重试按钮通过实际 Vue `$emit` 接回父组件。测试不抄写 loader/验证器实现。

外部可观察契约：

- 首次未完成请求显示 loading，不冒充成功空态；已 resolve 的真实空数组才显示空态。正常记录仍经真实 StudentWorkFeedback props 接入，含零分/评语。
- 网络 reject、HTTP500 型 reject、业务 false、缺 result、非数组 records、非法 row 和非法 total：请求完成后 loading=false，显示失败和可操作重试，不显示成功空态，不留下未处理拒绝。
- 对每类失败，通过真实重试按钮发送现有 mine endpoint；返回正常列表后恢复，失败文案和重试消失。新请求开始清旧数据/选择、未完成期间仍是 loading。
- 表格失败使用 workName/tag/type、pageNo/pageSize、排序、field 快照。失败后编辑尚未查询的表单输入，重试仍沿用失败快照；显式查询才用新参数并按既有行为回第一页。分页后失败重试仍该页。
- A→B 并发：B success 后 A success/A reject 不改变 B 的数据或状态；A 先结束时不能使 B 的 pending loading 消失（含旧 finally）；B error 后 A success 也不能吞掉 B 的错误。旧成功/旧失败顺序分别验证。
- 活跃请求 pending 时销毁父组件，随后 success/reject 不写回数据/error/loading；销毁后的重试不另发送请求。通过生命周期执行 guard，而非仅测试辅助函数。
- 原 Index 映射、全局 mixin、请求层、后端、反馈组件/helper 不变；CRUD 方法与 URL 沿用。卡片分页问题仅记录待办。

证据边界：VNode/script 状态和 deferred Promise 顺序，实际 Vue 响应性和真实父接线；不含 DOM patch、AntD spinner/portal、浏览器焦点/布局、实际 HTTP、登录或真实数据库。根 Agent 的 CUA 故障服务结果另记。

实现后补充（根 after2 CUA 发现）：a-table 在分页 change 开始请求时不能立刻卸载，否则 AntD 延迟 body refs 回调抛错。离线新增检查实际 table VNode 在 page-change pending 中仍存在并保持 tag/key；这只能检查接线，真实 nextTick/getBodyTable DOM 回调仍由根 CUA 复验。卡片 Less 网格 shorthand 编译错误同样只归根 CUA/构建证据，不能由离线行为测试证明解决。
