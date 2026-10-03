# 中文本地媒体路径读取交付

PR #56 基于 #55（`6235e7e2586a4ce914257faa11c7552bf628c04c`）。旧后端接受中文 `biz`/`bizPath` 上传并登记文件，随后同一合法路径的下载被 Shiro 默认 non-ASCII 检查提前拒绝。最小基线对同一公开课程的 ASCII 封面返回200/正确正文，中文封面返回401/JSON。这里没有声称生产副本现存297个ASCII路径损坏。

产品只改 `ShiroConfig` 注册和新增 `LocalMediaInvalidRequestFilter`。仅直接 REQUEST、GET/HEAD、原始及解码路径都落在精确本地媒体前缀时允许Unicode；保留原结构检查并显式拒绝控制字符。媒体JWT、当前关系授权、符号链接和文件边界继续执行；其它路径和dispatcher沿用父类。无 schema、UI、依赖变化，不全局放开Unicode。

产品提交 `2f724a264ab08ffd86b3652d4c1396d19efe773f`；精确候选JAR SHA256 `95d9ad3ad4ada70897974071fec283a0c29bb703e2cdcb41397e80f77ebbd7c7`。Java8干净构建退出0，父POM跳过Surefire，不能称Java单元测试已运行。打包差异只有Config class和新增filter的3个class，208外部JAR及common的111个解包文件字节不变。

## 实际验证与失败分类

- 同一冻结186断言脚本：旧包118/186，新包182/186。4个候选失败保留原JSON，**没有宣称186项全通过**。其中3个误预设重复斜杠一律拒绝；实际规范化为同一合法文件。独立18/18补查证明作者/本班教师/管理员只读同一目标，匿名401、跨班403，未返回邻居正文。另1个是已有本地代理缺少HEAD转发，新旧代理均404，后端直连HEAD正常；另项独立修复，不混入本Java PR。
- 同JAR相关回归393/393：认证7、下载88、上传46（含3项精确打包Java流故障）、文件归属76、课程单元80、通知44、Scratch云变量52。首次root上传回归漏传必需`--java-home`，中途退出1；保留记录，补参数后完整重跑46/46，未改产品。
- 本分支Python工具42/42；真实Spring/Tomcat注册与有限分派上下文49/49；独立Agent精确filter合成servlet矩阵70/70。三类范围分别记录，不能统称浏览器/生产验收。
- 真实匿名浏览器课程列表加载中文目录封面：HTTP200、图片complete、naturalWidth/Height=320/180。使用自制合成课程/图片和真实后端，无登录或令牌注入；[卡片截图](evidence/unicode-media/root/unicode-course-card.png)、[请求记录](evidence/unicode-media/root/browser-requests.txt)。既有外域errlog.js被原CSP拒绝的console error仍保留，非零错误页面未写成无错误。
- 专项前后完整业务行、表结构与全部附件恢复；浏览器夹具清理另核对68非审计表和附件相等。正常sys_log增量不当作业务写入失败。

完整脚本与逐项结果见[专项报告](unicode-media-tests.md)、[作者记录](unicode-media-author.md)、[独立审查](unicode-media-review.md)及[root聚合](evidence/unicode-media/root/root-summary.json)。补充观测的整理版CLI只做py_compile，原实际命令的观察证据与新脚本未重跑分别记录。

## 限制、依赖与后续

合法`%2B`加号URL引用在原权限查询的候选匹配中仍可能缺失：旧、新候选均401，字面`+`对照200。它是另一个真实兼容问题，保留待办，不把该失败归为非法输入，也不以这次guard修复声称已解决。重复斜杠和INCLUDE属性错位的上游边界详见独立报告；不作全面路径安全保证。

现有生产副本的297个路径为ASCII；这次中文用例来自受控合成环境。真实课程/媒体回归、组合候选切换另由总计划记录，不发布真实课程正文或学生附件。PR未远端合并，未生产部署。完整认证三角色、用户视觉评阅、真实云服务/容量与受支持框架迁移仍待处理。

回退可在本地将后端切回已保留的#55精确JAR（`bca9e5c8f1aa78ab536901e92e2ae3d96433ad0eb4c7599bdaf12174c2c785af`），不需要数据库回滚。新建中文资源在旧包上仍会恢复为原读取限制；不要删除其数据来伪装兼容。
