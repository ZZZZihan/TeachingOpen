# 课程作品恢复独立测试记录

日期：2026-10-03。测试实施者：role_entry_audit，独立于三份产品实现的 course_resume_impl。代码路径：`/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/course-draft-resume`。

## 结论

相同业务断言在 PR53 旧源码下为 **6/67 PASS、61 FAIL**，在最终产品提交 `ed7930f80d426f66b748acd55a6204e759b8cbac` 下为 **67/67 PASS**。相邻 7 个前端测试文件 **77/77 PASS**，完整前端测试 **436/436 PASS**，无跳过。未发现需要实现者继续修改产品的新问题。

测试文件及唯一必要的既有 fixture 调整已经冻结，未进行提交或推送，由 root 统一整合。三份产品字节哈希与实现者提供的冻结值一致。

## 实际执行范围与证据级别

新测试直接执行 `UnitViewModal.vue` 的实际 `workUrl` 计算属性，保持当前课程入口不含 workId 的 URL，再运行实际 Scratch/ScratchJr 共用持久化模块与 Python 持久化模块。关闭后重开用新的实际状态机实例表示；附件、登记、作品记录与提交在内存中控制。另有 1 条执行实际 Python `editor-bridge.js` 与 `source-loading.js`，验证真实适配器调用课程发现接口、读取学生附件、恢复标题与归属、提交同一个 workId，所有 HTTP/fetch 都为受控替身。

因此这里属于可复现的离线代码与契约验证，不是已认证浏览器验收、真实附件服务或数据库写入。没有访问服务、数据库、缓存或浏览器，没有登录、注入认证、读取运行凭据，也没有执行产品代码修改、提交或推送。root 另行完成的真实 HTTP 31 条验证不计入本记录的离线数量。

每种编辑器各 22 条业务用例，共 66 条；加实际 Python 适配器 1 条，共 67 条。覆盖：

- 实际课程 URL：中文、空格、&、+、% 编码；首次进入只在无已有作品时读取教师模板。
- 第一次保存、关闭、同课程重开：恢复本人内容、名称、ID、课程与班级归属；再次保存更新相同记录，不产生第二份作品。
- 已有记录的名称、班级和附加任务绑定覆盖入口陈旧提示。
- 课程发现与作品详情失败：禁止模板回退、禁止捕获/上传/提交，解除忙状态，手动重试恢复本人作品。
- 缺详情、错误作品类型、缺本人附件、课程不匹配、返回 ID 冲突：禁止回退和上传。
- 缺课程信息、错误模板类型、缺模板附件、课程返回 ID 冲突、mineWorkId 类型错误：入口含模板文件提示也不能跳过验证。
- 显式 workId 正常继续：不额外查询入口课程，按已有记录恢复真实归属。
- 显式/课程 resetTemplate：课程从验证后的课程详情读取模板，额外作业读取明确模板；保留原 workId、课程/任务/班级绑定，保存重做结果后再次继续可恢复。
- 重做与入口课程/任务冲突时禁止覆盖。
- 发现尚未完成时重复 load/save 禁止上传；本人附件打开失败时不提前提交发现的 ID，重试重新发现并保留原作品身份。
- 实际 Python 桥接从 unitId 发现 mineWorkId，再读取 studentWorkInfo 和本人附件，最后提交原作品 ID 与归属。

## 可复现命令

执行位置为上述工作树的 `web`。测试支持 `COURSE_RESUME_SOURCE_ROOT`（另一个检出目录的仓库根路径）与 `COURSE_RESUME_SOURCE_REF`（在指定仓库用只读 git show 读取源文件）。断言文件不随源版本更换。

旧版基线完整提交：`8f5bf1e272e57a3460c0414b506925c1395a18d2`。

```sh
COURSE_RESUME_SOURCE_REF=8f5bf1e272e57a3460c0414b506925c1395a18d2 node --test --test-reporter=tap tests/course-draft-resume.test.cjs
COURSE_RESUME_SOURCE_REF=ed7930f80d426f66b748acd55a6204e759b8cbac node --test --test-reporter=tap tests/course-draft-resume.test.cjs
node --test --test-reporter=tap tests/learning-reader.test.cjs tests/scratch-persistence.test.cjs tests/python-persistence.test.cjs tests/scratch-bridge.test.cjs tests/scratchjr-bridge.test.cjs tests/python-bridge.test.cjs tests/python-source-loading.test.cjs
NODE_PATH=/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/worktrees/product-candidate/web/node_modules node --test --test-reporter=tap tests/*.test.cjs
```

候选与旧版日志使用同一冻结测试文件；候选以最终精确产品提交读取源文件。完整 suite 执行时工作树 HEAD 同样为最终产品提交，只有本次测试文件、既有 fixture 和 root 另行添加的非 `*.test.cjs` 在线探针尚未提交。

## 冻结文件清单

- 新增：`web/tests/course-draft-resume.test.cjs`，SHA-256 `0fd2f0bfbb5f9218984b9221361b2ba73b6a8e4abbe477603cb778e998344d13`。
- 既有 fixture 唯一调整：`web/tests/python-persistence.test.cjs` harness 新增 unit 适配器，返回该课程的 ID、类型、名称、模板 URL 与已有作品 ID。已有重做断言、结果、文件路径与 ID 要求均保留；调整使课程重做 mock 包含实际桥接已有的课程查询契约。SHA-256 `7c29be5f6a70d4d571a7626f8e2e65f7a2455d5b03a129805e2bc4d54088e596`。

产品冻结字节核对：

- `web/public/scratch3/persistence.js`：`a335e902d727401c5044cd99f2faea28c7f9c3e0210da537d07bcfdf00066b40`。
- `web/public/python/persistence.js`：`7305e2bd9ee18ddf8fa419a1ea436a7f14c23d6d0aa50b1e3d7d7829209499be`。
- `web/public/python/editor-bridge.js`：`7eec9c27025cde073c9f7a7ce717cbed14758c6ae5c5108339b01935aa3032d7`。

`git diff --check` 退出 0；本轮没有再修改产品。

## 保留日志

均位于 `/Users/xuzihan/Documents/Projects/TeachingOpen/.devspace/artifacts/role-flow-audit-1003/`：

- `course-resume-baseline.tap`：同一新测试，PR53 源码，6 PASS / 61 FAIL，退出 1。典型失败为三种编辑器保存后从同一课程 URL 重开读取模板、不能恢复本人 ID 或名称；Python 实际桥接也缺少课程作品发现。
- `course-resume-candidate.tap`：同一新测试，精确产品提交，67 PASS / 0 FAIL，退出 0。
- `course-resume-adjacent.tap`：相邻 7 文件，77 PASS / 0 FAIL，退出 0。
- `course-resume-full-frontend.tap`：完整 `tests/*.test.cjs`，436 PASS / 0 FAIL / 0 SKIP，退出 0。
- `course-resume-full-frontend-no-deps.tap`：首次完整 suite，当前工作树尚无 node_modules，4 个文件无法导入 @babel/core 或 vue，其余 353 条通过。保留真实环境失败；未安装依赖，随后使用已有 product-candidate 依赖路径成功。

先前管理员班级切换保留旧选择的发现已单独保存到 `role-entry.md`，作为下一轮独立 PR 候选；本次没有扩展修复范围。

仓库内 TAP 副本仅去除行尾空白以符合 diff 检查；结果未改动，原始本机日志保留，两者摘要见证据目录 tap-copy-manifest.json。
