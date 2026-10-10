# 产品化完成条件独立审计：1 / 4 / 8 / 9 / 10

> 后续注记（根并行补证）：根完成新空缓存clean-backend构建，报告exit0、158.103s；208外部库、945应用条目、111内部common条目字节一致。详见同级[../clean-backend/REPORT.md](../clean-backend/REPORT.md)及[../clean-backend/root-build-review.json](../clean-backend/root-build-review.json)。原审计读取时尚未有该证据；此处据根消息追加，不能写成审阅者执行或独立复读。
结论：**8 / 9 / 10 在约定的本地候选声明范围已具备证据；4 的代表性权限/数据路径有实测，但必须保留其准确覆盖和下列限制。1 原来缺少空 Maven cache 复现，根已并行补做并报告成功，细节以根的新构建报告为准。整个 Goal 仍不能仅凭这些门或645个前端测试标为完成；普通认证三角色和编辑器打开→保存→重开→提交→反馈属于2 / 3 / 7的实际业务验收。**

本轮只读源码、Git对象、产物和本地报告，没有运行构建、产品测试、HTTP、SQL、浏览器、服务或生产访问，也没有修改产品、创建PR。仅写新私有backend-review目录。根并行新构建的结论来自根消息，本审阅按根要求停止新增读取，没有把它列为自己独立执行/复读的结果。

## 对象与本轮直接核对

- C = `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate`，HEAD `06ab2040780f33296e93c97d29d00e80cbcc2f65`；API tree `150a3a0b738c3e635c5bf1eb7be467c4d0ee2266`，web tree `e63b7764a0e8b4b647cfb75f516f40cac37c1255`。
- P = `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/productization-goal`，读取HEAD `9d47b934b7ad2262142a6d2ec25394efd1b0c3e6`。依据是`P/docs/optimization/productization-goal-2026-10-02.md:69–80`；第29行明确本地候选/PR的完成对象与生产、真人试用/容量分开。
- A = `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts`。后文C/P/A展开为这些精确绝对路径。
- 直接计算当前JAR `A/account-recovery-20261005/api-author/teaching-open-account-recovery.jar` SHA256 **67568eeaecea8e8d7342088767eeef2d7fcee45d61afffa0fb559b7808664016**；1,030个main/POM与构建来源`69e1cca5a59026977f12f4e56b0c8fde2910b8a9` Git blob及当前工作区全部相同。
- #72 measured `872109fde9020ab5ad8e42a9cc445f06224589dd`→当前HEAD的api/web diff空；当前4,895 dist文件共211,925,716 bytes逐份大小/SHA一致，无缺失/新增；清单SHA256 **9f9a89fb12fc2a3c674988059c86665bcc0a80617bd53b8445f996708b5929da**。
- 相比2026-10-05旧依赖inventory，当前209库名集合相同，208外部archive逐字相同；仅内部common archive变化。前端lock SHA256 **100033635ce1d01f5ee7b8cd1385bc958edde7ad5686d441d205b49ea7e78e74**不变。
- [evidence-index.json](evidence-index.json)记录52份资料的绝对路径、SHA、读取commit、全部比较结果及72PR的本地Git关系；这是文件审查，不是本轮业务实测。

## 各门状态

| 条件 | 权威证据与绑定 | 判断与限制 |
| --- | --- | --- |
| **1 构建/可复现** | `C/web/BUILDING.md`、`C/docs/optimization/evidence/install-round1.txt`：Node26.7.0/npm11.19.0，原锁npm ci实际装2,080包，lock至今不变。`A/account-recovery-20261005/api-author/{author-build-receipt.json,build-final.log}`：来源69e1cca5、当前JAR67568eea，固定Java8/Maven3.9.16 clean package和两组30 JUnit。`A/student-work-loading-20261005/{candidate-tests.log,candidate-build.log}`及`P/.../student-work-loading-candidate.json`：645/645、DONE/12warnings，根回执exit0。 | 已具备固定构建/合成启动。最新#69 JUnit是mock SMS/Redis/用户服务，不是业务矩阵。旧构建沿用Maven缓存；根本轮新增`A/completion-audit-20261005/clean-backend/build.log`空缓存构建已报告exit0/158.103s，根另完成条目对比，详见其`completion-audit-2026-10-05.md`。本审阅未新增复读该报告，不把它算自己独立实跑。 |
| **4 权限/数据** | `C/docs/optimization/class-membership-access-pr.md`及`evidence/class-membership-access/comparison.json`：#62产品ee25b493/交付328a0212/JARf03ac420，82/82+286/286。`C/docs/optimization/upload-resource-boundary-pr.md`及`evidence/upload-resource-boundary/synthetic-summary.json`：#65产品9945646b/交付956a4c16/JAR9eb18d42，451/451+下载88/88。`P/.../account-recovery-candidate.json`：#69交付03954459/当前67568eea，根22恢复+7登录+11角色。`P/.../student-feedback-readable-candidate.json`：#71 exact pair45/45，后端同当前67568eea。 | 代表匿名/学生/本人/他人/同班教师/管理员/跨班学生和教师，含允许、拒绝、真实故障回滚/字段不变和文件字节。旧矩阵不是本轮当前全套；准确现存限制详见下一段。没有从只读审查证明新的具体权限缺陷，不扩大安全扫描。 |
| **8 运行/恢复** | `C/docs/optimization/tomcat-maintenance-pr.md:36–51`：#33旧新各384，4接口读写、1/4并发；`frontend-route-prefetch-pr.md`与`P/.../frontend-prefetch-candidate.json`：#51同基线85f8a7d、各5轮实际页面请求395→17/传输下降。`production-read-benchmark-pr.md`与`evidence/production-read-benchmark/aggregate.json`：#64 measured77a4fbfb/JARf03ac420，真实私有5课程/83单元/297素材，1008计时+126预热+2预检。`local-backup-restore-pr.md`/#30：69表3019行2附件39实查；`scratch-cloud-recovery-pr.md`/#47：69表35行2附件3云字段14实查；`local-candidate-switch-pr.md`/#31：切换/主动回退/启动失败恢复/中断recover，五阶段各26业务。 | 原声明的有限基线、实际瓶颈对照和本地停写恢复/回退已完成，不能归零。6个恢复/回退/基线脚本与#47 b7a7d788无diff；当前vue.config与#51 630a639c无diff。它们不是当前包完整恢复/当前页面性能/生产容量证据；计划没有每PR重复所有演练要求，因此不追加#72相同后端45项或压力重跑。 |
| **9 依赖/发布** | `P/docs/optimization/evidence/dependency-release-20261005/{review.md,inventory.json,inventory-summary.json,official-sources.json}`：读取旧64cce174/JARf03ac420，2026-10-05重点官方来源。当前208外部库/前端lock相同，版本与维护结论可沿用。`A/session-cookie-20261005/source-review.md`：49bea7da/JAR9eb18d42静态条件审阅；当前ShiroConfig/MediaCookie无diff。 | 重点版本/维护/公告核查、有关已证风险处理、生产定制/试用/目标环境状态明确，在本地声明范围满足。旧Shiro资源切片已被#65修复；不重新开。Boot/Spring/Shiro/Vue维护债务不是已复现可达漏洞，也不是整体安全放行。TLS可信转发、case-sensitive Linux/Z820、生产定制对应和真人试用明确未完成；原文要求状态明确，不能擅自升级成这些都须先执行或全栈迁移。 |
| **10 PR/追溯** | `A/completion-audit-20261005/root-current.json`是根2026-10-04T21:22:15.647348+00:00快照；72 OPEN/12 Draft，无已报告CI。直接Git核对72 exact head均存在，71个实现/交付head为候选祖先，唯一非祖先是规划PR#1；#62—72全在祖先链。#72产品e3522dbc、PR交付fcaaf6d8、构建872109fd、最终06ab2040和产物链一致。 | 本地候选/各实现PR确切追溯及自检/独立审阅/人工待验/未部署状态成立。OPEN不等于尚未本地集成，也不等于远端合并。Draft19/21/22/23/25/26/27/28/29/37/41/44的待验业务不能只通过改标签算完成。没有GitHub CI通过、远端合并或生产交付声明。 |

表中`P/.../<name>.json`的完整路径均为`P/docs/optimization/evidence/product-candidate/<name>.json`；每份实查SHA及提交见evidence-index。根并行完成的clean-backend结果另引用，不混入该index的先前读取清单。

## 条件4的准确现存限制

1. **覆盖是代表主路径，非全系统授权扫描。** #62覆盖成员四入口（admin/dev、批量/幂等、并发、真实SQL回滚）；不覆盖全部账号创建/部门角色分配入口。#65覆盖规范下载与公开资源旁路、大小写别名、GET/HEAD/Range；规范正常路径和数据恢复实测充分。WebMvcConfiguration至当前与修复commit相同，旧旁路不是当前待办。
2. **最新认证实现有真实常规检查，也有明确未完成矩阵。** #69的22/7/11和#71同一67568eea后端45项是当前认证/角色代表证据；#62/#65的82/286/451/88不能重记成最新包全部重新实测。#69独立新版完整并发/DB失败专项被平台中断，仍未完成；30个mock JUnit不等于补做实际Redis/MySQL故障矩阵。本轮不重派该请求，也不把未完成当新产品缺陷。
3. **普通浏览器/角色写入链仍缺。** #48 role-flow真实菜单/角色夹具及22 API预检不等于普通浏览器登录。#71/#72 CUA替代认证外壳和合成传输，不能证明学生登录后保存/提交、教师批改和管理员维护真实链。这一缺口属于2/3/7明确门槛，不能以seed token、读取验证码或再做孤立组件修复替代；验证码当下操作边界仍待处理。
4. **数据不变的分母清楚。** 合成故障/资源矩阵比较69 schema、68非审计表及本次用户/文件；认证审计可变化。真实私有副本只读12项的7表不变，不等于全69表/全部素材重哈希或生产当前状态。旧生产来源快照含历史悬空关系，不能自动认定当前代码缺陷并清理真实数据。

## 必要推进与停止边界

根已补空缓存构建这一有新增对象的复现证据，可用其独立来源/条目对比收口1。下一优先是既定普通认证三角色和三个编辑器全链，绑定当前候选、真实数据结果与可恢复自制夹具；只有这些结果才能推进大目标的2/3/7。

8/9/10无需再用重复容器45项、匿名首页测速、旧Shiro切片、全框架迁移或小页面PR替代完成条件。生产定制对应、真人试用、TLS/目标部署的执行确需相应资料/环境/授权，但当前原文只要求清楚记录状态，未完成状态本身不是新增本地候选阻断。

本轮没有发现应新增产品修复的阻断问题。若要给“当前整包已完整恢复/当前时延/正式目标部署”作新承诺，应对新增对象另证，不扩大既有Goal。最终Goal能否完成须结合负责其余门的独立审计及根真实验收，不能由本五门报告单独关闭。
