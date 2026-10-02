# 课程学习入口：课程列表与单元目录

本项基于 #19 `54b3449`，代码提交 `492b327`。目标是让学生找到课程和单元时看到明确的内容与操作，并能从加载失败中恢复。当前为 Draft，已完成实现、工程自检和受控组件视觉检查；认证浏览器中的菜单、实际应用外壳和原学习弹窗仍需验证。

## 原问题与最终行为

原「我的课程」使用 400px 固定卡片加两侧间距，同一份合成数据在 390px 浏览器出现 440px 页面宽度。课程目录只有大卡片标题，缺封面时大块空白；两页请求没有完整网络错误/空白恢复，目录只请求前 99 个单元，路由参数变化不重新加载。

- 我的课程改为响应式内容卡片，显示实际课程分类、名称、摘要、介绍及学习入口，缺图或图片失败后保持文本卡片。继续按 `showType` 使用地图或目录原路由。
- 目录改为编号列表，显示课程标题、简介、单元简介及服务端实际返回的资源类型。单元仍交给原 `UnitViewModal.view(unit)`，没有改变媒体、作业或编辑器接口。
- 加载、空白、错误和重试分别呈现；畸形成功响应不伪装成空列表。课程地址缺失不请求后端。
- 监听课程 ID；新请求使旧结果失效，切换课程关闭原单元弹窗。按服务端原分页契约每页 20 项加载，失败保留已有内容并重试同页；忙状态防止重复追加。
- 沿用白色、深墨色、少量珊瑚红及细分隔线，没有新增进度、时长或完成率等虚构业务数据。

## 验证

前端分支 `492b327` 的 `npm test` 70/70（新增 11 项，执行实际 SFC 方法），涵盖失效/空响应、重试、路由竞争、销毁、分页及旧地图路由。三个生产 Vue/JS 文件 ESLint 0 errors / 0 warnings，生产构建成功，仍有 6 条原 CSS 顺序与资源体积警告。没有增加依赖或改动锁文件。当前 Agent 已完成自检，没有独立审核或人工验收结论。

[准确候选与摘要](evidence/learning-entry/candidate.json)记录 13 项受控浏览器观察：两页的 390/768/1440 宽度、失效封面回退、介绍与单元入口、Enter 键、错误重试、空目录和忙状态。两页三个宽度均无横向溢出。原源码清单 5,634 个文件摘要保持不变。

**证据边界：**截图使用真实前后 Vue 组件，但 API 被确定性合成数据替代，外壳使用测试页，学习弹窗使用只接收单元的替身。它证明组件视觉和声明的入口交互，不证明实际登录、权限菜单、播放器或后端持久化。预览不连接后台、不设置任何认证凭据、不修改业务数据；生产构建不包含这个测试入口。

| 页面 | 之前 | 之后 |
| --- | --- | --- |
| 课程目录 1440 | [旧版](evidence/learning-entry/before-units-1440.jpg) | [新版](evidence/learning-entry/after-units-1440.jpg) |
| 我的课程 1440 | [旧版](evidence/learning-entry/before-courses-1440.jpg) | [新版](evidence/learning-entry/after-courses-1440.jpg) |
| 我的课程 390 | [旧版溢出](evidence/learning-entry/before-courses-390.jpg) | [新版](evidence/learning-entry/after-courses-390.jpg) |
| 课程目录 390 | [旧版](evidence/learning-entry/before-units-390.jpg) | [新版](evidence/learning-entry/after-units-390.jpg) |

另有 [768 目录](evidence/learning-entry/after-units-768.jpg)、[768 课程](evidence/learning-entry/after-courses-768.jpg)、[错误](evidence/learning-entry/after-error.jpg)、[空状态](evidence/learning-entry/after-empty.jpg)。

## 复现

在 `web/` 使用现有锁文件依赖：

```sh
npm test
./node_modules/.bin/eslint --no-ignore src/views/account/course/CourseListCard.vue src/views/account/course/CourseUnitListCard.vue src/views/account/course/learningPresentation.js
npm run build
node tests/learning-preview/build.cjs /tmp/teaching-learning-preview
python3 -m http.server 18113 --bind 127.0.0.1 --directory /tmp/teaching-learning-preview
```

组件入口为 `http://127.0.0.1:18113/#/teaching/mineCourse/courseUnitCard?id=preview-a`；顶部链接可切换课程列表。查询字符串 `?scenario=error`、`?scenario=empty`、`?scenario=loading` 放在 `#` 前，分别提供一次失败后恢复、空响应和持续 pending。普通状态含一个故意失效封面。加第三个构建参数 `54b3449` 可生成使用同一夹具的原组件预览。请使用空闲本地端口，勿覆盖已有服务。

## Draft 剩余条件与兼容性

真实验证码登录的操作时确认先前已请求，尚未收到。不能注入会话来跳过这个步骤。此项需在真实认证应用中完成课程列表 → 地图/目录 → 原学习弹窗的浏览器核对，补充真实接口错误、分页、菜单外壳下三宽度表现，然后再转为可审阅。当前全站菜单/顶部布局、地图阅读器、播放器、编辑器、Office 转码以及富文本安全并不因本 PR 完成验收。完整三角色与产品化 Goal 继续未完成。

后端运行应使用 #20 及其前置修复；当前新前端分支尚未加入本地 `integration/product-candidate`。原 18112 仍为已记录的 #19/#20 组合，18113 仅为本项组件预览。没有远端合并、部署或数据库迁移；回退为父分支构建即可撤回本项页面变化。
