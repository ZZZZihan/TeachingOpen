# Scratch 精选作品适配

本目录交付两份可直接上传 TeachingOpen 的 Scratch 3 项目。原作者均为 **Raspberry Pi Foundation**，本地化适配者为 TeachingOpen；适配文件按 **CC BY-SA 4.0** 提供。作品内有中文开始画面、玩法、持续署名和包含完整来源的舞台注释。

| 作品 | 上传文件 | 封面 | 玩法 |
| --- | --- | --- | --- |
| 小船竞速 | `boat-race.sb3` | `covers/boat-race.png` | 鼠标带领小船绕过棕色河岸，抵达浅黄色终点；白色水流加速。 |
| 缤纷接点 | `catch-the-dots.sb3` | `covers/catch-the-dots.png` | 左右方向键旋转转盘，同色接点得分，错色扣机会，3 次机会用完结束。 |

两份封面均为 **960 × 720** 的实际 TeachingOpen Scratch 播放器舞台截图，展示项目内的开始画面，包含原作者及许可署名。`covers/*-playing.png` 另外保留实际运行画面供审阅。

## 固定来源与许可

- Boat race：来源仓库 [raspberrypilearning/boat-race](https://github.com/raspberrypilearning/boat-race)，固定提交 `08b40cde7e8bd804bd1b0f7bed335123115f8f24`；[Scratch 原作](https://scratch.mit.edu/projects/276662533/)；[官方教程](https://projects.raspberrypi.org/en/projects/boat-race)。
- Catch the Dots：来源仓库 [raspberrypilearning/catch-the-dots](https://github.com/raspberrypilearning/catch-the-dots)，固定提交 `beeafc3a77a993c762c4017ad66cd3385d6deac3`；[Scratch 原作](https://scratch.mit.edu/projects/252923761/)；[官方教程](https://projects.raspberrypi.org/en/projects/catch-the-dots)。
- 来源文件通过 agent-reach 指定的 GitHub CLI 内容 API 下载。完整固定源文件 URL、原文件与最终文件 SHA-256、封面 SHA-256、来源提交、适配内容见 `manifest.json`。
- 原始 `.sb3`、许可全文与来源简介保存在 `sources/<slug>/`。原始媒体和全部源积木 ID 均保留。
- 上游 `LICENSE.md` 的许可名称正文写作 “Creative Commons Attribution 4.0 International License”，但其正文超链接及许可图均指向 `by-sa/4.0`。本适配采用该具体链接指向的 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)，原文完整保留，未将其改写成另一许可。

## 适配范围

保留原角色、地图、声音、移动速度、碰撞颜色、生成速度调整和计分规则。开始画面点绿旗后立即隐藏，不延迟游戏；边缘署名使用的颜色避开两个项目全部游戏碰撞判定颜色。

小船竞速只增加中文玩法/署名、中文计时监视器和碰撞/胜利气泡，并让文件初始船位与原绿旗起点一致。原地图和障碍物不重绘，因为棕色河岸、白色水流和浅黄色终点直接参与真实颜色传感器判定。

缤纷接点增加中文分数、机会和“文件内最佳”监视器；清除原文件保存的上轮试玩值；每次绿旗将转盘恢复到原文件初始方向 165°；机会用完后先显示中文结束提示，再执行原脚本停止全部积木。“文件内最佳”在当前项目及保存的 `.sb3` 内保留，未新增网络排行榜。

两个项目都无扩展、云变量或外部资源请求要求，打开项目后可在本机运行。

## 本地验证与边界

候选文件 SHA-256：

- `boat-race.sb3`：`79cea250da8ff1c3241b2d67801a08da04662e8a2c912a528ce700e07ea52d7b`
- `catch-the-dots.sb3`：`1f9deec63d7074aae73f7eb430fb2e4937274446eaf68b95f8303e7e423ac1ef`

本地测试使用本仓库未修改的 `web/public/scratch3/player.html`、`player-bridge.js`、`lib.min.js` 和 `chunks/player.js`，以真实 `.sb3` 文件作为输入；未使用模拟 Scratch 引擎或模拟项目接口。`browser-validation.json` 记录播放器资源哈希、作品哈希和各项运行结果。静态结构检查见 `validation.json`。

- 小船：浏览器真实绿旗、鼠标移动、碰撞造型、回起点、停止后计时不变、绿旗重置计时、导出 `.sb3` 后重开再启动。
- 小船终点：使用真实播放器和真实颜色传感器，在原绿旗初始化后通过 VM 的 `boat.setXY(210,-135)` 将船放到终点附近，验证胜利及自动停止、绿旗重开。该检查只证明终点传感器与结束恢复，不等同于人工/自动鼠标走完整条赛道。
- 接点：浏览器真实左右键控制、接对一次得分、错色机会从 3 扣至 0、结束提示、自动停止、绿旗分数和机会重置、手动停止、导出重开后再启动、作者/许可注释保留及文件内最佳分数保留。
- 静态：ZIP CRC、资源 MD5、源资源逐字节保留、源积木 ID 保留、积木父子/输入引用、完整来源注释、扩展和云变量检查。

浏览器原始输出和截图保存在外层工作区 `output/playwright/showcase-five-scratch/`。保留测试夹具失败的原始证据：错误地按 `alt` 定位实际上使用 `title` 的绿旗、将 Scratch 数字字符串直接和数字比较、复用试玩最高分导致过强的相等断言，以及终点夹具早于绿旗初始化而被初始化覆盖。修正后的通过记录单独保留；这些调整没有删减实际游戏行为断言或修改最终 `.sb3`。

浏览器加载只出现播放器原有 Canvas/自动播放相关警告；最终候选的本地加载没有控制台错误。此处不声明网站上传、数据库记录、完整 SPA 详情页、生产发布或人工验收完成；这些由主 Agent 对最终集成候选另行验证。

## 重建和检查

1. 在本目录运行 `python3 adapt.py` 重建项目与来源 manifest。
2. 运行 `python3 validate.py` 检查 ZIP、媒体、积木和来源信息。
3. 运行 `python3 serve.py --port 18146`，打开 `/scratch3/player.html?workUrl=/showcase/boat-race.sb3` 或 `/scratch3/player.html?workUrl=/showcase/catch-the-dots.sb3`。
4. `check-*.browser.js` 是供 playwright-cli `run-code --filename=...` 运行的实际浏览器检查函数；`capture-covers.browser.js` 捕捉实际舞台封面。

静态本地服务仅用于隔离文件验证，不接入生产账号和生产数据库。
