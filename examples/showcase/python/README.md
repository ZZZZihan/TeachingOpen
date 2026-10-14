# Python 精选示例

三份作品均为适配 TeachingOpen 的单文件 Python 程序，适配版本使用 **CC BY-SA 4.0**。保留原作者、原作来源及相同方式共享要求；发布时请同时展示 manifest 中的原作者、来源和许可链接，不能把适配作品署名为本站原创。

| 作品 | 程序 | 原作者 | 原作来源 |
| --- | --- | --- | --- |
| 彩虹螺旋 | [rainbow_spiral.py](rainbow_spiral.py) | Raspberry Pi Foundation | [Turtley Amazing 教程](https://projects.raspberrypi.org/en/projects/turtley-amazing/0) |
| 缤纷雪花 | [colourful_snowflakes.py](colourful_snowflakes.py) | Carrie Anne Philbin / Geek Gurl Diaries + Raspberry Pi Foundation | [snowflake.py](https://github.com/raspberrypilearning/turtle-snowflakes/blob/master/code/snowflake.py)；[原视频](https://www.youtube.com/watch?v=DHmeX7YTHBY) |
| 海龟赛跑 | [turtle_race.py](turtle_race.py) | Raspberry Pi Foundation | [完成版代码](https://github.com/raspberrypilearning/turtle-race/blob/master/en/resources/turtle-race-finished-turtle-race.py) |

许可链接：[Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/)。三个上游许可文件都把图片和链接指向 `/licenses/by-sa/4.0/`，正文标签却写成 Attribution 4.0。此处按其明确链接记录为 CC BY-SA 4.0，并在 `licenses/` 原样保留文件；没有静默修改原文。`manifest.json` 保存固定提交、逐文件 SHA-256、原作者、适配说明和许可地址。`provenance/` 保留原始参考文件，`.py.txt` 文件供核查，不属于待上传的可运行示例。

彩虹螺旋依据教程中的循环、转角、增长步长和彩色列表思路改编；参考教程正文以及 `en/code/complete/main.py`，没有把 `code/example.py` 的 Hello World 当成原作品。雪花保留函数与八向重复分枝，将枝条重绘成对称图形，随机 20 朵改成 6 朵构图。赛跑保留 4 只海龟和随机步长，补充有限比赛、终点和胜者。三份程序都添加了深蓝配色、等比布局、短暂停顿、可见署名和终端来源输出。

绘图仅使用本站 `turtle-renderer.js` 白名单中已核查的接口。程序采用 Python 2 兼容语法，依赖内置 `turtle`、`time` 和赛跑的 `random`，不读写文件、不访问网络、不需要第三方包。适配坐标以 480×360 为设计范围，并根据实际画布尺寸等比缩放。先设置坐标再设置背景，避免上游 Turtle 引擎重置背景。

`browser-validation.json` 记录真实 Chromium 中加载实际文件、使用本站已有 player、Worker 和 Turtle renderer 的 9 次完成运行：每份作品在 900×760 视口首次运行、同页再次运行，在 390×760 视口重开后运行。桌面实际绘图区为 898×360，手机为 388×300。`covers/` 中三个 480×360 PNG 是最终桌面运行画面的直接截取，没有重绘。原作者及许可在画面中可见，完整来源同时输出到终端。

`static-checks.json` 是使用计数 Turtle 替身执行的指令预算和几何范围检查，不能替代浏览器运行。每份程序总请求数低于 10,000，按程序短暂停顿计算的一秒内请求数低于 500。赛跑最小步长模型在 66 轮内四只海龟全部到终点，最大步长在 30 轮内完成，均低于 80 轮上限。

本子目录的检查没有覆盖完整 SPA 的作品详情、真实接口上传、生产公开入口或人工课堂验收；这些由整合交付继续核查。本站页面展示的作者与许可信息必须与实际上传文件一致。
