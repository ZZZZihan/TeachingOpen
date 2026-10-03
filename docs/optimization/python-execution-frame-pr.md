# Python 执行与绘图隔离

本项基于 PR #50。原编辑器与播放器在父页面运行学生程序，长计算会阻塞界面，程序还能接触父页对象。新候选把计算移入独立 Worker；父页继续负责编辑、保存和输入，受限绘图页面仅执行固定的 turtle 方法。运行、停止、输入取消和重跑共用同一套生命周期。

最终实现保留旧 Python 2 / Skulpt 和 turtle 课堂能力，增加可停止的独立计算、父页面输入和清晰状态。作者实现、独立测试、独立窄范围复核及 root 实际浏览器验证已分别记录。此分支基于 `fix/python-preview-url`（PR #50），不包含首页 prefetch 优化。

## 设计与边界

- Python 2、既有 Skulpt 和 turtle 引擎沿用；通过小型 webpack 模块加载器取得引擎，不启动 Vue 页面入口。
- 学生程序仅在 Worker 执行；绘图区为 opaque srcdoc，父页与绘图区、绘图区与 Worker 分别使用私有 MessageChannel。令牌、保存对象和源文件 URL 不发送给执行域。
- Stop 请求调用原生 Worker.terminate，断开结果通道；重复运行只保留最后一次排队请求，等待旧运行退出确认和短启动节流后再启动。
- 输出保持文本与现有长度上限；输入等待不消耗计算预算。绘图通过固定白名单和带类型的有限数据结构传输，限制请求数量、排队和派生动画工作量。
- 不是操作系统级沙箱、内存配额、全部网络侧信道证明或所有浏览器版本保证。完整认证角色流程和人工试用分别验收。

## 停止行为的实际证据

第一版 opaque iframe 原型被否证：移除页面后，有限同步计算仍继续到结束；相关原型记录保留，没有集成或发布该实现。

Worker 也不能承诺瞬间 CPU 归零。固定 [Chromium 154.0.8037.93 实现](https://chromium.googlesource.com/chromium/src/+/154.0.8037.93/third_party/blink/renderer/core/workers/worker_thread.cc) 设置了两秒的强制终止宽限。此前 500ms 同步循环在 Stop 后自然结束是非即时性证据，不能把它当作 Worker 无法最终终止。

独立通用实验顺序运行每个浏览器的 3500ms control 和 Stop，确认实际进入循环 20ms 后再过 100ms Stop，观察到进入后 4500ms。Chrome154、Playwright WebKit26.5、缓存 Firefox148 的 control 均有最终 END，Stop 均无最终 END；Chrome 的进度延续到约2000ms，另两者未出现250ms进度。父页面心跳持续响应。它是精确旧引擎的独立实验，不是完整产品跨浏览器验收。

root 在实际播放器 freeze1 中另行完成相同的成对验证：[汇总](evidence/python-execution-frame/chromium-cpu-freeze1.json)、[复现探针](evidence/python-execution-frame/worker-cpu-paired.cjs)、[当时产品文件摘要](evidence/python-execution-frame/worker-frozen-manifest.json)。control 在3500ms正常完成；Stop后最后进度为elapsed2000ms，之后没有2250ms或最终完成，观察结束时页面为stopped、无旧frame/输出，父50ms心跳最大间隔不超过53ms。后续 callback 和绘图约束变更不能直接视为这次冻结快照已全部验收。

## 最终验证

- 独立测试 Agent：专项 **72/72**、完整前端 **347/347**；产品前后 SHA 完全一致。含主完成与回调输入交错、输入暂停计时、回调队列、异步停止确认、最后一次重跑、圆弧派生 720/721 分界及移动文字工作量。日志与摘要在 [测试证据](python-execution-frame-evidence/final-full-suite.json)；这些是受控 DOM/时钟与真实 Skulpt 的 VM 检查，不是浏览器 CPU 证明。
- root：`npm run build` 成功，保留 **12 条既有 CSS 顺序/资源体积 warning** 和过期 Browserslist 提示。[构建摘要](evidence/python-execution-frame/branch-build-summary.log)。产品脚本语法检查、精确 bundle 逆向重建、diff-check 通过；沿用原项目依赖。
- root 实际 Chromium：编辑器、播放器各 **6/6** 基本流程，覆盖 Python2 输出及 HTML 作为文本、输入发送/取消、睡眠程序替换、Stop/重跑及 turtle 方形/文字/undo。[两入口结果](evidence/python-execution-frame/chromium-two-entry-basic.json)。其中 500ms 忙循环只证明父页响应与生命周期，终止证据采用上面的 3500ms 成对实验。
- root 两入口各 **390/768/1440**：六种布局均无页面横向溢出，执行控制完整可见；仅注册事件尚未绘图时 0 canvas 的区域仍可点击，鼠标与键盘回调后有像素和正确输出，无 pageerror。[布局与事件](evidence/python-execution-frame/chromium-responsive-events.json)。旧编辑器 390 菜单沿用折叠入口，本项没有重新设计整套编辑器。
- root 实际编辑器点击提交：自写代码经上传、文件登记、更新同一 seed-work，再重新加载，代码和名称一致、再次执行输出42；只有一份作品、一次上传/登记/提交，pageerror为空。[保存重开](evidence/python-execution-frame/chromium-save-reopen.json)。使用自建 HTTP 模拟接口，无登录或真实 Java 保存写入。
- root 两入口实际 Worker：document 不存在、父 DOM 与 localStorage 写入失败、嵌套 Worker 构造器不可用，自制父 canary 不变；不携带凭据的唯一 loopback fetch 拒绝，浏览器给出匹配的 `connect-src` 违规事件。[范围有限的隔离检查](evidence/python-execution-frame/chromium-realm-network.json)。不推广为所有网络通道或操作系统资源限制的安全证明。
- 独立浏览器 Agent：Playwright WebKit26.5 和缓存 Firefox148 实际播放器各 **6/6**，另验证可见方形/文字及蓝色像素、完成作品 Stop→重跑→clear、编辑入口输出42。12个检查文件前后未变、11个已服务产品资源摘要匹配。[独立跨浏览器报告](evidence/python-execution-frame/cross-browser/REPORT.md)。Firefox使用已记录的缓存协议兼容设置并有旧代码warning；WebKit是自动化引擎，不是Safari人工验收；未做完整全程pageerror监听，未宣称零运行期错误。
- 独立只读 reviewer 先发现并证实了 circle、write(move) 的同步派生工作放大及 done-during-callback-input 空闲误超时；作者修复后，reviewer按同序列窄范围复核通过，冻结摘要与 [最终产品清单](evidence/python-execution-frame/final-source-manifest.json) 匹配。没有把作者自检称为独立审查。

浏览器布局探针最初遇到编辑器正常的未保存离开确认，CLI提前返回，没有计入通过。最终每个场景使用独立自建页面，结果明确返回且页面逐个关闭。失败日志和原 iframe 原型保留在本机私有证据目录。

## 截图

[旧播放器1440](evidence/python-execution-frame/baseline-player-1440.png) 展示原来的运行/清空与输出区；旧图运行的是有界计算，新图运行交互绘图，比较范围仅是执行控制。新播放器：[390](evidence/python-execution-frame/final-player-events-390.png)、[768](evidence/python-execution-frame/final-player-events-768.png)、[1440](evidence/python-execution-frame/final-player-events-1440.png)。新编辑器：[390](evidence/python-execution-frame/final-editor-events-390.png)、[768](evidence/python-execution-frame/final-editor-events-768.png)、[1440](evidence/python-execution-frame/final-editor-events-1440.png)、[保存重开](evidence/python-execution-frame/final-editor-save-reopen.png)。这些截图只包含自写程序和模拟作品，不含生产用户资料。

## 剩余边界

保留的旧引擎提供 Python2，不新增 Python3 支持；旧 turtle 的速度字符串等继承语义不在本项改写。停止确认表示原生 terminate 已调用、通道关闭及启动节流已完成，不代表 CPU 瞬时归零。5分钟运行保留期限、30秒计算预算和新绘图限额均可能让过重程序提前结束，界面及错误信息会提示。

完整认证角色流程、真实后端保存与师生人工试用仍单独验收。没有绕过验证码，没有修改生产、合并 GitHub PR 或部署。组合候选验证由产品化计划另行记录。
