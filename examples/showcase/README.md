# TeachingOpen 开放学习示例

这五个作品用于创作社区的公开精选展示。原作者保持原有署名，TeachingOpen 是适配与发布方；适配版本均采用 **CC BY-SA 4.0**。

| 作品 | 文件 | 原作者与原作 |
| --- | --- | --- |
| 小船竞速 | [boat-race.sb3](scratch/boat-race.sb3) | Raspberry Pi Foundation · [Boat race](https://projects.raspberrypi.org/en/projects/boat-race) |
| 缤纷接点 | [catch-the-dots.sb3](scratch/catch-the-dots.sb3) | Raspberry Pi Foundation · [Catch the Dots](https://projects.raspberrypi.org/en/projects/catch-the-dots) |
| 彩虹螺旋 | [rainbow_spiral.py](python/rainbow_spiral.py) | Raspberry Pi Foundation · [Turtley Amazing](https://projects.raspberrypi.org/en/projects/turtley-amazing/0) |
| 缤纷雪花 | [colourful_snowflakes.py](python/colourful_snowflakes.py) | Carrie Anne Philbin / Geek Gurl Diaries + Raspberry Pi Foundation · [原代码](https://github.com/raspberrypilearning/turtle-snowflakes/blob/e80a75fdcbc35b94bf20c52b064aec54a6716d78/code/snowflake.py) |
| 海龟赛跑 | [turtle_race.py](python/turtle_race.py) | Raspberry Pi Foundation · [原代码](https://github.com/raspberrypilearning/turtle-race/blob/8aa4a42fa3cc7460e00776c7d1bcb8818a5b7f21/en/resources/turtle-race-finished-turtle-race.py) |

Scratch 点击绿旗开始，小船跟随鼠标，接点游戏使用左右方向键。Python 使用平台已有 Turtle 播放器，点击“运行”即可，无需安装额外包。三份 Python 均有限执行，可再次运行；赛跑每次可能有不同胜者。

## 来源、许可与封面

`scratch/manifest.json` 和 `python/manifest.json` 保存固定的上游提交、原文件及许可原文、适配说明、程序与封面的 SHA-256。各子目录 README 说明具体改动和测试范围。

上游许可文件中的部分文字标签与其链接名称不一致，原文已经保留。适配版本遵循其中明确指向的 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 条款，保留署名、来源、改动说明和相同方式共享许可。

五张封面均为本次候选文件在网站实际播放器中的截图。Scratch 使用工程内的中文开始画面，Python 使用最终绘图画面。源码注释、Scratch 舞台注释及可见画面保留署名；Python 终端同时显示完整来源链接。

## 发布与后续维护

`catalog.json` 是网站来源展示和这五个作品发布资料的共同清单，包含固定作品 ID、类型、程序/封面路径与 hash。详情页明确区分“发布者”与“原作者”，并提供原作与许可链接。

来源展示仅匹配固定作品 ID、类型及 `showcase/20261014/<slug>/<程序SHA256>/` 目录。这个目录是版本命名，不是内容验证；发布时必须实际下载并比对 hash。普通编辑器另存的其他版本不会误继承这份来源说明。更新作品时，应重新确认署名与许可、更新候选 hash 和版本目录，并一起验证页面与文件。

发布使用正常管理员上传、文件登记和作品接口，不向作品所有人字段写入原作者身份，不关联课程、班级或作业。上传各阶段保留收据，固定作品 ID 防止重试生成重复作品；未知上传结果应先核对再继续。站点部署及生产收据保存在本次工作区证据目录，不含登录令牌。
