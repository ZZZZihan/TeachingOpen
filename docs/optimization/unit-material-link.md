# 学习资料链接重复文件前缀修复

2026-10-05；基线 `fix/student-work-loading` / `fcaaf6d82dfaa8b3a0120c4104a6b07d8e8ad1f3`，修复分支 `fix/unit-material-link`。

## 问题与根因

根任务的实际学生页面观察发现，“课程资料 1”链接为：

```text
http://127.0.0.1:18150/api/sys/common/static//api/sys/common/static/role-flow/learning-notes.txt
```

根任务的只读数据库观察确认原资料字段仍是相对 key `role-flow/learning-notes.txt`。本实现 Agent 没有请求该运行时或数据库；下面的根因由当前源码和实际方法的合成配置执行确认。

学习卡片通过 `/teaching/teachingCourseUnit/mineUnit` 取得单元。`TeachingCourseUnitController.mineUnit` 在返回前已对 `coursePpt` 和 `coursePlan` 调用 `Ow365Util.getFileUrlStr`，其内部 `QiniuUtil.getFileUrl` 给本地 key 添加 `staticDomain`。因此阅读器拿到的是 `/api/sys/common/static/role-flow/learning-notes.txt`。

原 `UnitViewModal.resources` 再调用 `getFilePrevew`。这个 helper 对非 HTTP/HTTPS、非 `aes:`/`aess:` 的输入调用 `getFileAccessHttpUrl`；后者把网站根路径当成文件 key，又加一次 `staticDomain`。已有阅读器测试将两个 helper 替换为原样返回，所以没有覆盖真实链路。

不能用 `coursePlan_url` 替代原字段绕过问题：`coursePlan` 的 `@FileUrl` 会让 DictAspect 对已解析字段再派生地址，它本身也可能重复前缀。此次继续读取原字段，在阅读器链接边界修复。

## 修复行为与范围

产品只改 `web/src/views/account/course/modules/UnitViewModal.vue`：

- 网站根路径和完整 URL 先经原 `safeUrl` 转为绝对 HTTP/HTTPS URL，再交给原预览 helper。
- 原始相对 key 先经原 `getFileAccessHttpUrl` 解析一次，再绝对化并预览。
- `aes:` / `aess:` 保留原 ow365 密文预览契约；officeapps、外链、七牛地址仍通过原 helper 处理。
- Scratch 资料仍使用 create 场景和 `queryEncoding=uri`，嵌套文件参数采用可访问的完整 URL。
- 非 Web scheme 在包装为文件 URL 前被拒绝；单份预览配置异常仍只使该资料不可用，不阻止其他单元内容和资料显示。

共享 `manage.js`、后端序列化、数据库字段、认证与权限均未修改。原阅读器的预览异常测试调整了触发方式，使其仍能模拟已绝对化的 broken-config 文件；没有删除异常隔离断言。

## 验证

新增 `web/tests/unit-material-link.test.cjs` 联合执行实际 SFC script 与实际 `manage.js` 的文件/预览函数，配置和接口均为本地受控替身，不使用 identity helper 替身：

| 检查 | 结果 |
| --- | --- |
| 同一新专项在旧基线执行 | 2/10 PASS、8 FAIL，退出码 1 |
| 候选专项与 reader、entry、draft-resume、python-preview 相邻测试 | 132/132 PASS，退出码 0 |
| 完整前端 `tests/*.test.cjs` | 635/635 PASS，退出码 0 |
| 单元阅读器 template 编译及 script 解析 | errors/tips 均空 |
| `npm run build` | 退出码 0，构建完成 |
| `git diff --check` | 退出码 0 |

专项覆盖已解析 API 地址、相对 key、HTTP/HTTPS 外链、protocol-relative URL、中文/百分号/query/hash、officeapps 嵌套地址、ow365 两种加密标记、七牛、Scratch 参数、非法 scheme 与异常隔离。旧版通过的两条包含外链和加密预览，候选保留这些正常入口。

构建使用已有依赖的本地链接，没有安装或升级依赖。构建报告 12 条 CSS 顺序及资源体积 warnings，构建配置没有修改。原始日志保存于本机 `.devspace/artifacts/unit-material-link/`：`baseline.tap`、`candidate-targeted.tap`、`candidate-full.tap`、`build.log`。

可在 `web/` 目录重跑：

```sh
SOURCE_REF=fcaaf6d82dfaa8b3a0120c4104a6b07d8e8ad1f3 node --test tests/unit-material-link.test.cjs
node --test tests/unit-material-link.test.cjs tests/learning-reader.test.cjs tests/learning-entry.test.cjs tests/course-draft-resume.test.cjs tests/python-preview-url.test.cjs
npm test
npm run build
```

产品 SFC SHA-256：`16e95e3f1e59b89bf16e594efd40e570a3b73cbfe41b2931d7b0379d3494acf3`。
未修改的 `manage.js` SHA-256：`7c6f487b32ba0cf0a2275cc7d0852fff7a41609eb42b84b7c125177f0e632599`。
专项测试 SHA-256：`eed300bcfb2a2f0a0af9642a92b1e72fcc59202ae9aa2be20facc250ca78f72f`。

另一个只读 Agent 独立审查了 controller → Ow365/Qiniu → SFC → manage 的链路，并用实际 SFC/helper 联合执行确认根路径、相对 key、外链、Scratch、officeapps、加密地址行为，未发现阻塞问题。独立审查没有写文件或操作服务。上述方法、构建与审查证据不代替浏览器实际打开资料、服务 HTTP 200、人工验收或生产部署。

当前发现共享 `getFilePrevew` 的 kkfileview 分支引用未定义 `url`，本次只验证该异常仍被资料级隔离，没有扩大为共享预览重写。此次没有启动、停止或修改运行时，没有数据库或浏览器动作，没有远端合并或生产动作。
