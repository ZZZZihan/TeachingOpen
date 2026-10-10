# 三角色 UI 夹具素材来源

这里仅保存项目先前为编辑器/阅读器验收自制的小型素材，不含用户内容、学生作品、生产快照或外部下载。复制来源为 `product-candidate` 工作树提交 `0b89d854b4145115d51521ebf3741d507d66e5bf` 中的测试资源，按字节复用，不修改素材。

| 本目录文件 | 原仓库相对路径 | 字节 | SHA-256 |
| --- | --- | ---: | --- |
| lesson.mp4 | web/tests/reader-preview/assets/lesson.mp4 | 9948 | a13e04078b6d1a7aa52bec79aea4a8beeec7d5911d88c02931df84180b363dd0 |
| starter.sb3 | web/tests/scratch-preview/sample.sb3 | 1264 | 94b92bf01ca353f9853a56a027fe3351b6e64883b7e301a6f0e46f0fd05990d2 |
| starter.sjr | web/tests/scratchjr-preview/sample.sjr | 679 | 3db97173b9436df3ce8deacacbf3dd46ac60467044ea1650b14f7d250bf88147 |

MP4 为 10 秒无声自制教学画面；SB3 包含自制 SVG 背景和圆形角色，未使用扩展或远程素材；SJR 是空白单页项目及自制 PNG 缩略图，原生成器为 `web/tests/scratchjr-preview/generate_fixture.py`。

`role_flow_fixture.generated_assets()` 还用 Python 标准库在专用 runtime 内生成纯色 PNG 封面、两行 Python 起始代码、学习资料、教师教案和文件提交示例。所有文件都登记为本地 `sys_file`，课程/单元仅引用 `role-flow/` 相对路径。工具启动不依赖 ffmpeg、Pillow、前端测试目录或联网下载。

这些模板只提供真实格式的起始材料。验收作品必须由浏览器中的学生实际编辑、保存、重新打开和提交，工具不预造提交结果。
