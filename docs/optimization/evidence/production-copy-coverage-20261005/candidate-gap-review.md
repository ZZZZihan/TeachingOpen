# 性能、恢复与依赖发布条件：只读证据复核

2026-10-05；独立证据审阅 `/root/course_resume_impl`，用户指定 GPT-6.1-sol / ultra。本轮只读文件、Git 状态/差异及冻结 JAR，不运行测试、服务、数据库、浏览器或外部请求；仅写本报告。候选为 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate`，实查 HEAD `64cce174aac6cf3699985b4bc88a30cc70c2f67f`，API tree `92a0c8032ee4a94cebf95ee48b60dbfc7abb0068`，web tree `d35f4bf0d3cf203429cdd23b14c232116b34d734`。已有未跟踪 `.playwright-cli/`、`output/` 保留。

计划在 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/productization-goal/docs/optimization/productization-goal-2026-10-02.md`；聚合证据目录是该工作树下 `docs/optimization/evidence/product-candidate/`，不是候选工作树中的同名目录。下文 **C** 指候选根，**E** 指此聚合证据目录。

**结论：应认可已有有限性能基线、数据库/附件/云数据恢复和候选回退的声明范围已经完成。当前需要补的是最新候选与代表性数据的测量绑定，以及依赖支持/发布风险处置，不是把这些工作重新归零。最有价值下一步是结合另一 Agent 的生产来源素材覆盖审阅，在授权 Z820 私有副本上建立当前精确包的有限只读 HTTP 性能基线；本轮不执行。**

## 已有证据完成了什么

- **有限读写性能基线已建立。** `C/docs/optimization/tomcat-maintenance-pr.md:38–51` 记录四接口、1/4 并发、每组预热 4 次/计时 48 次，旧新各 384 请求成功，保留硬件 Mac14,14 / 24 CPU / 64 GiB、5 账号/2 课程/2 作品、逐请求样本及新连接方法；包括草稿真实落库及恢复，不能说只有匿名首页测速。`C/docs/optimization/account-freeze-pr.md:23` 又保留账号冻结前后的有限对照，明确预热历史不等，不能归因新增 SQL或称容量通过。
- **页面加载改善有实际浏览器对照。** `C/docs/optimization/frontend-route-prefetch-pr.md:63–80` 在同基线旧新各 5 轮、共享私有副本下测得请求 395→17、传输 23,581,181→15,396,141 字节；卡片可用时间存在波动，不宣称普遍延迟改善。`C/web/vue.config.js:31` 仍删除 prefetch，初始 preload/动态 import 保留。预取归属已核对根 `README.md:29` 与 `E/frontend-prefetch-candidate.json` 为 PR #51；#53 是 Python 单次读取，不能混用。
- **停写冷恢复与回退已有真实演练。** `C/docs/optimization/local-backup-restore-pr.md:15` 起记录 69 表/3,019 行/2 附件逐项一致、39/39 实际检查；`C/docs/optimization/local-candidate-switch-pr.md` 记录正常切换、主动回退、启动失败自动恢复及中断 recover，五阶段业务各 26/26。`E/backup-restore-candidate.json`、`E/candidate-switch-candidate.json` 明确区分工具/产物复核和未重复真实演练。
- **Scratch 云业务值遗漏已修复。** `C/docs/optimization/scratch-cloud-recovery-pr.md:5–26`、`E/cloud-recovery-candidate.json` 记录格式 2 保存 DB1 持久化云 hash，真实恢复 69 表/35 行/2 附件/3 云字段并 14/14，通过旧会话拒绝和四类错误输入拒绝；会话、验证码和权限缓存继续排除。旧格式 1 明确报告无云数据，不能再把“所有 Redis 均按可丢缓存处理”当当前缺陷。

实查以下六脚本与已实测 PR #47 提交 `b7a7d788734315c8cdb183e4f79b2853198b4018` **Git diff 为空**：`api/dev/local_recovery.py`、`backup-local.py`、`scratch_cloud_recovery.py`、`verify-cloud-recovered.py`、`local_candidate.py`、`benchmark-local-http.py`。最新组合未重新演练不证明工具失效；代码未变也不构成重复跑全套的理由。

## 与当前候选的对应及剩余条件

1. **测量范围与最新包不同。** 上述 HTTP 基线为小型合成数据和早期包；页面对照为 `85f8a7d` 基线及旧组合。当前 `E/class-membership-layout-candidate.json` 绑定最终 HEAD、581/581 前端、构建退出 0、12 条告警、48/48 代理资源字节及精确后端包；这些不能替代当前生产来源数据的性能测量。计划第 8 项（第 60 行）的“建立基线”已有有限证据；持续负载、公网/容量不是本地候选完成对象，不应偷偷升级为本轮必过门槛。

2. **恢复能力与最新包恢复验收不同。** 冷恢复/切换实演使用 #24 JAR，云恢复使用 #43 JAR。当前冻结 #62 JAR 是 `f03ac420301977cea26e14d9de0bab03f0d8a5c0e7ec92854363ad07347060c0`，已独立只读重新计算并一致；`C/docs/optimization/evidence/class-membership-access/candidate-source.json:3–6` 记录 1,031 个后端输入与冻结构建相同。本轮还核对产品提交 `ee25b493` 到当前 HEAD 的 api 差异，仅有 dev 工具与 BUILDING，没有应用/POM 路径变化。历史演练足以认可可信本机、停写、同 schema 的恢复机制，不等于最新包或生产来源副本已完整恢复实演，也没有生产 RPO/RTO、异机/跨版本、周期/加密/保留策略结论。最新候选若要专门声明整包恢复，应另做一次有新增对象的受控恢复，不重复旧机制全套。

3. **依赖盘点部分有效，部分陈旧；发布条件未全部闭合。** 当前 `C/web/package-lock.json` SHA256 `100033635ce1d01f5ee7b8cd1385bc958edde7ad5686d441d205b49ea7e78e74` 与 `E/dependency-inventory-2026-10-03.json` 相同；另直接读取当前 node_modules 中九项 package.json，Vue2.7.16、Axios0.18.1、TinyMCE5.10.9、Router3.6.5、i18n8.28.2、Prism1.29.0、Lodash4.17.21、Webpack4.47.0、CLI3.12.1 全匹配，故前端解析版本仍可复用。155 条 npm audit 是当日包级告警，不是 155 个可达漏洞，也不是今天重跑结果。当前 POM 第 57/59 行是 Shiro1.13.0 / Tomcat9.0.122；直接只读检查精确冻结 JAR 中 209 个库条目（含一个内部 common）确认 12 个 Apache Shiro1.13.0、三 Tomcat9.0.122、encoder1.2.3，Boot2.1.3、Spring5.1.5。旧 inventory 的 `backend_packaged_libraries_before` 及 Shiro1.7.0 followup 不能作为当前清单。维护报告已有官方来源与兼容实测，不能说依赖未处理；其 `shiro-maintenance-pr.md:43` 明确 1.13 为 EOL 过渡版本，Spring/Vue 的长期维护和发布风险仍需明确处置。

计划第 9 项（第 61 行）要求依赖维护/公告和有关发布阻断风险有明确结论，尚不能用“构建成功”关闭此项；适合下一次整理最新冻结包/锁文件清单，把已解决、暂缓迁移及真正发布阻断分开并绑定出处。本轮没有联网刷新官方公告，不能根据旧 audit 直接判定当前可利用漏洞或擅自触发框架升级。旧 Shiro 报告中的账号冻结失败已由后续账号冻结项修复，旧切换聚合中的读取审计字段待办也已由作品浏览项修复；这些历史失败不作为当前缺陷重新开单。真实三角色/人工视觉、目标环境及生产定制对应保持计划中的独立状态。

## 下一项建议：代表性只读性能基线

根本轮已核验 Z820 生产来源私有副本 receipt（69 表、5 课程、83 单元）和现有只读 12/12；另一个 Agent 正在核验 83 单元/297 素材覆盖。应以它的实际可用性结果选择代表样本，使用当前精确 JAR/候选，测有限课程分页与允许资源的 GET/HEAD/Range；不访问 Z820 生产运行服务、不登录浏览器、不请求学生私有作品、不记录原始业务正文或凭据。产出绑定 receipt/schema/素材集合摘要、JAR/dist 摘要、硬件、数据量、预热、固定并发/样本数、成功语义、中位/P95、字节和失败结果，并核对业务表/附件保持；只做有限基线，不宣称容量。

沿用 `C/api/dev/verify-production-content.py:1–6,56–120` 的私有副本/精确包/配置/进程守卫及只读聚合原则，新增测量应与已有 12 项正确性检查分开，避免把重复成功探针当新覆盖。**不能直接运行现有 `benchmark-local-http.py` 指向该副本**：第 46–48 行登录旧 fixture 并 SQL 插入五作品，第 58–59 行读取会增加作品计数且调用草稿写入；它适合旧合成夹具，不是生产来源副本只读测试。这项新证据有代表性和当前包绑定的实际增量，不依赖浏览器验证码。

本报告没有执行新 benchmark、恢复演练、依赖安装/audit、测试或远端核查；没有修改产品、既有报告、私有数据、服务或版本历史。
