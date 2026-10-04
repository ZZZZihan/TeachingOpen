# 学生作品加载输入契约与独立基线

对象：`student-work-loading`，base `f0980ce2d8c8a06e635bf09aca3a8b7d16edbcb7`。仅源码与本机离线 Vue/SFC；本审阅者没有浏览器、HTTP、数据库、服务或认证调用。

两个入口均 GET `/teaching/teachingWork/mine`。controller `api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/teaching/controller/TeachingWorkController.java:127–151` 在当前用户约束下读取分页并返回 `Result.ok(pageList)`；正常结果为 `success=true`、`result.records` 数组、`result.total` 数值。默认 pageNo=1/pageSize=999；前端正常传输 JSON 后分页数值为 number。

`web/src/api/manage.js:getAction` 调用既有 axios；`web/src/utils/request.js` 成功拦截返回 `response.data`，网络/HTTP 500 拒绝 Promise，业务 false 是已 resolve 的结果。这要求 loader 同时处理 reject 与不成功/缺结构 body，不能只写 success 分支；本 PR 不改全局拦截器或认证行为。

表格实际继承 `JeecgListMixin`。created 调用组件 `loadData()`；`getQueryParams()` 合成 queryParam/isorter/filters、field、pageNo/pageSize；搜索/重置经 `loadData(1)` 回第一页，分页/排序及既有 CRUD 刷新调用 `loadData()`。本 PR 应在组件局部覆盖 loader，保持全局 mixin 字节不变。主代理明确要求：失败后改变尚未提交的表单输入再点“重试”，仍请求失败时参数快照/页码；只有显式新查询采用新条件。重试不能调用 loadData(1) 或重新读取编辑中的 queryParam。

卡片仍通过真实 `Index.vue -> page/index.js -> MineWorks.vue` 接线。基线 card 请求 params=null，声明的 pagination.pageSize=12/onChange 没有模板分页接线，后端默认 pageSize=999；这项已有分页缺陷另记待办，不要求本 PR 修。反馈继续使用 #71 的 StudentWorkFeedback，每行已有 nullable Integer score / String teacherComment，不改变反馈契约。

基线独立实际 SFC 离线探针从精确 Git blob 读取，**8/8 预期缺陷复现**（并非新功能通过）：table/card 各复现网络 reject 后 loading=true 且无重试入口、业务失败与成功空列表相同、success/result=null 抛错后 loading=true、较老成功覆盖较新成功。`baseline-offline.json` 保留逐项观察与源码 SHA；发生的未处理拒绝由测试进程捕获记录，没有任何真实请求。

新版独立验证围绕实际 SFC 按钮和真实 mixin 参数接线，检查 loading/error/成功empty区分、失败收敛与 retry、失败参数快照、旧成功/旧失败/旧finally 隔离、销毁保护和现有反馈接入。真实 DOM/AntD spinner、键盘、故障 HTTP 服务和布局由主代理 CUA 另记录；离线 VNode/状态结果不替代它们。
