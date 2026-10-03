# Freeze2 实际 player / editor 的 WebKit、Firefox 基本流程

结论：在 root 管理的18160实际产品静态服务中，两个独立自建浏览器会话各通过现有 basic() 的6项短流程；另补画布像素、截图、完成作品 Stop→重跑→clear，以及 index 编辑入口打印。未发现本检查范围的产品失败，未修改产品、seed-work、服务或认证状态。本轮未重复3500ms CPU实验。

时间为2026-10-03 UTC09:21–09:28附近，候选工作树base85f8a7d0a995047feb8ce486224d7bf991878e62，feature/python-execution-frame。执行前后12项核心JS/HTML与probe文件 SHA-256 完全相同；11项可由public读取的静态文件，18160响应SHA-256均与本地一致。见product-hashes-before.json、product-hashes-after.json、served-hashes.json、hash-check.json。文件列表明确在manifest中；不把dirty工作树HEAD当最终产品提交标识。

浏览器均不安装、不下载，使用已缓存 Playwright1.62.1 CLI：

- WebKit cache2336，与此Playwright版本匹配；实际UA Safari26.5，headless。是Playwright引擎验证，不是用户真实Safari人工验收。
- Firefox cache1511；实际UA Firefox148.0，headless。缓存协议不完全匹配，使用前轮已证实的explicit executablePath与contextOptions.viewport=null；保留该自动化兼容限制，不推广到所有Firefox版本。

使用实际player URL：`http://127.0.0.1:18160/python/player.html?queryEncoding=uri&lang=turtle&url=%2Ffixtures%2Fseed.py`。通过本地浏览器addScriptTag加载项目现有browser-probe.js，调用实际挂载PythonEditor的setCode/runit/clear，未替代执行实现。

| 检查 | WebKit26.5 | Firefox148 |
|---|---|---|
| Python2 print42、HTML样式字符串纯文本输出 | 完成，output无img节点，sandbox allow-scripts | 同样通过 |
| raw_input 等待与表单提交 | waiting-input期间300ms remainingMs不减少；输出hello 测试输入，form隐藏，完成 | 同样通过 |
| 输入取消后重跑 | 旧frame断开，新run完成，无OLD_INPUT_AFTER | 同样通过 |
| 重复运行替换sleep中的旧run | 新run完成，等待800ms无OLD_SLEEP_AFTER | 同样通过 |
| helper有限500ms busy与Stop | parent30ms心跳持续，Stop后stopped，无BUSY_AFTER；有实际20ms entered console标记 | 同样通过 |
| turtle方形、write、undo | 输出turtle finished、state completed、保留opaque frame | 同样通过 |

basic()包含既有500ms有限helper，本轮没有延长或重复3500ms负载。helper的外部console entered含实际迭代数（WebKit319290、Firefox159814），没有completion标记；missing END不能单独证明CPU终止。因此player-basic.json仍保留cpuTermination='unverified'。线程终止宽限由前轮v6控制实验与root实际Chromium paired probe另行判断，不由本短流程取代。

为了确认绘图实际呈现，另运行speed0、blue方形60x60、write('Audit square')程序。两个浏览器截图都可见蓝色方形、龟标和文字，output AUDIT_DRAW_OK。通过Playwright对自建opaque frame做只读像素读取（该权限属于浏览器测试，不提供给学生代码）：

- WebKit两个canvas为1278x360；绘图层677个非白可见像素，其中439个蓝色；龟层70/46。
- Firefox两个canvas为1364x360；绘图层686个非白可见像素，其中440个蓝色；龟层68/41。

证据为各浏览器turtle-pixels.json、turtle-player.png及原CLI记录。截图已实际查看，像素非空并不代替全套图形API兼容验收。

随后在完成作品上点击实际Stop：old frame disconnected、state stopped；重跑打印AFTER_DRAW_STOP且completed；clear后state idle、frame0、output空。两个浏览器均通过，见draw-stop-rerun-clear.json。这证明本任务生命周期，不把frame removal当CPU死亡。

编辑入口 `http://127.0.0.1:18160/python/index.html?workId=seed-work` 也分别加载实际组件并运行 `print 6 * 7` 与 `print 'EDITOR_AUDIT_OK'`：输出42与标记，state completed，sandbox allow-scripts，保存按钮可见。本轮没有点保存。root同期在synthetic后端保存过seed-work，其fixture初始文本可能变化；本检查直接设置临时编辑内容并运行，没有用旧fixture文字等待，也没有改后端保存数据。

实际console保留相邻.playwright-cli目录，分开浏览器工作目录避免前轮同毫秒碰撞。Firefox旧打包代码每次Worker启动有unreachable code warnings；CLI未报告console errors。WebKit日志含既有app对象打印和entered标记。本轮没有独立贯穿全流程的pageerror监听，因此不单凭CLI摘要宣称所有运行期错误都被完整捕获。首次对1.62.1 run-code使用plain await形式被CLI拒绝SyntaxError，改为其接受的async(page)=>函数形式后加载probe成功；这是工具调用适配，不是产品失败。

本轮只覆盖打印、输入、取消/替换、简单绘图、作品Stop/重跑/clear和编辑入口基本打印；未验证认证、保存后端、完整键鼠/定时回调、所有turtle API或资源限制。root的实际Chromium保存/重开、宽度/键鼠测试和全suite结果属于另一执行者，不混入本独立记录。

Cleanup：本轮创建的python-product-freeze2-webkit与python-product-freeze2-firefox均由命名CLI close成功关闭。18160未创建、修改或停止；前轮18161已停止，本轮没有新建服务。所有独立sources/config/results/screenshots保留在私有审计目录。
