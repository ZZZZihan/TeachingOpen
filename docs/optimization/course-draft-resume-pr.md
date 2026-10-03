# 课程入口恢复学生已保存作品

学生在课程单元点击「开始练习」，保存后关闭，再从同一单元重开，原三个编辑器会载入教师模板。Scratch 忽略单元接口已经返回的 `mineWorkId`；ScratchJr 因 URL 带模板而跳过查询；Python 没有单元查询适配器。旧后端会把无 ID 的再次保存匹配到同用户、同单元的原作品，因此模板可能替换当前学生版本。旧版本仍有数据日志，本问题不是附件已经彻底删除。

产品提交 `ed7930f80d426f66b748acd55a6204e759b8cbac`，基于 PR #53 `fix/python-source-loading`。只修改 Scratch/ScratchJr 共用 persistence、Python persistence 和 Python editor bridge 三份产品文件，无后端、依赖、数据库或页面布局改动。实现与独立离线测试分别由用户指定的 GPT-6.1-sol / ultra 子 Agent 完成；工具没有单独 Fast 参数，没有声称已设置该参数。主 Agent 独立审查，并完成真实 HTTP/数据库验证、组合构建与本地交付。

课程入口现在先读取有权限约束的 `getUnitWorkInfo(unitId)`，已有 `mineWorkId` 时再读 `studentWorkInfo`，恢复学生文件、名字、原 ID 与任务归属；没有历史作品时才读教师模板。单元、详情、类型、文件或归属异常时进入错误状态、禁止保存并允许重试。只有文件成功打开后才提交本次加载的身份状态。显式作品 ID 入口保持优先；明确重做仍更新原作品，并验证原任务与对应模板。

## 验证与限制

- 独立离线专项用同一套最终 67 条断言，对 PR53 精确基线为 6/67，对产品提交为 67/67。包含实际 `UnitViewModal.workUrl` 到三个持久化模块的「首次创建—保存—关闭—重开—继续保存」及真实桥接适配器；受控失败、类型/身份冲突、重试与重做均覆盖。相邻 7 文件 77/77，完整前端 436/436（0 跳过）。首次完整运行有 4 个文件缺少当前工作树的 Vue/Babel 依赖，保留失败日志；显式借用已有依赖目录后完整重跑通过，未安装依赖。详见 [独立测试记录](course-draft-resume-tests.md) 和原始日志。
- 主 Agent 的同一最终实际 HTTP 判据：旧前端 **16/31**，新前端 **31/31**，15 项改善、0 项回退。实际执行本地上传、文件登记、作品保存、单元发现、学生详情、附件 GET 和 MySQL 回读；三种格式都复现旧版模板替换当前作品，新版学生内容与名称保持、继续保存沿用原 ID，最终每单元每学生仅一行作品。
- 两轮均使用同一个已冻结 PR58 后端 JAR `4578567dcedc18bf8a5f69758f8209d9b7bc74fc24f24f0d50196ec97e684c42`。新建合成 runtime `course-resume-1003`，专用端口 13370/16443/18173/18174。测试后 69 个表结构、68 个非审计表完整行、全部附件条目和提交缓存均恢复。五个合成账号行也完整恢复，CLI 会话退出；最后关闭临时后端、MySQL 与 Redis，确认四端口均无监听，数据和证据保留。
- 实际 HTTP 检查调用的是产品持久化模块，文件捕获/应用边界由合成适配器承担，不等同实际 Scratch/ScratchJr/Python 引擎浏览器验收。终端测试登录沿用隔离夹具工具；没有向浏览器注入 token，也没有完成或绕过浏览器验证码。完整三角色登录与人工视觉验收仍待处理。
- 首次运行因前端分支没有 `local_http` 工具而在导入时退出，未访问运行环境；最终指定 PR58 工具目录的 `PYTHONPATH`。首轮旧 17/31、新 31/31 保留：旧 Python 空名称使第二次保存被正常校验拦住。最终在再次保存前模拟填写合法名称，保持载入内容不变，用同一脚本重跑旧新版本，才得到三类型完整覆盖证据，没有修改预期以抹掉失败。

## 本地组合交付

本地组合产品提交 `faf1b1f23a268e6f9919088ab2a65abcda76b708`，API tree `cff429b0a7f9d0fcb76e2072b59f7d121a10e3e9` 不变。主 Agent 在组合源码运行 `npm run build` 成功，Node 26.7.0 / npm 11.19.0，12 条既有 CSS 顺序与资源体积 warning 保留。4893 个构建文件、211470810 字节；与旧产物逐文件比较，仅上述三份 public 脚本变化，无删除。清单 SHA-256 `81ff2a16225aee2f652e17990992472e33cea2b2f000c6524c4fa7a92d29f6d8`。

18112、18142、18150 三个常用代理的各 10 个初始/变更资源实际 GET，共 30/30 与构建产物逐字一致。18150 登录页刷新后正常显示，当前错误/告警日志为空；这仅证明登录界面加载，尚未证明认证后的练习恢复。旧 4893 文件完整副本已保存到本机 `.devspace/artifacts/course-resume-root/previous-dist`，清单摘要仍为 `453a9f32aeb0f3d534146e790ae62ab49bae4c23405127c640cc6ce86e0d6065`，可回退。

生产内容副本仍位于私有 `.devspace/prod-fixture-1003`，用于真实课程/媒体内容检查；这次写入复现只在新合成 runtime。没有修改 Z820 生产数据、GitHub 合并或生产部署。管理员跨班级选择残留已记录为下一独立问题，本 PR 不混入该改动。

## 复现入口

离线：在 `web` 运行 `node --test tests/course-draft-resume.test.cjs`；指定 `COURSE_RESUME_SOURCE_REF=8f5bf1e272e57a3460c0414b506925c1395a18d2` 可用相同判据验证旧版失败。完整前端检查为 `npm test`，需项目依赖或显式 `NODE_PATH` 指向已有依赖目录。

实际 HTTP：使用 PR58 `api/dev` 的隔离工具与冻结 JAR，先创建上述专用 runtime，运行 `api/dev/verify-course-draft-resume.py --runtime ... --jar ... --source ... --assets ... --output ...`。`PYTHONPATH` 指向 PR58 的 `api/dev`；`--assets` 指向组合源码 `api/dev/role-flow-assets`；旧、新 `--source` 分别为 PR53 与本候选工作树。脚本拒绝其他 runtime 名称、端口和已有输出，凭据仅经 stdin 传递给 Node，不写证据。

原始结果、源码摘要与本地字节检查见 [证据目录](evidence/course-draft-resume/)，实现说明见 [作者记录](course-draft-resume-author.md)。
