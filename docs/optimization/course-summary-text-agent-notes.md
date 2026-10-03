# 课程卡片摘要修复记录

2026-10-03，独立工作树 `course-summary-text`，起点 `11e8958`。本记录为 UI Agent 自检，真实副本页面复验及用户验收由 root 另行记录。

实际原因：CourseCard 源码有三行截断，但既有生产产物 `app.5da12580.css` 缺少 `-webkit-box-orient:vertical`。用本项目 Autoprefixer 6.7.7 处理同一 Less 源码可复现删除；该版本也不支持 `ignore next`。修复仅在 `.course-summary` 规则内使用 `autoprefixer: off`，保留方向声明并加 `5.7em` 三行高度上限，不改变全局构建配置。

新增纯函数 `courseSummaryText`：移除原始标签、注释及 script/style 块后，一次解码常用命名实体和合法 Unicode 十进制/十六进制实体；未知及非法实体原样保留，`&amp;lt;` 保持为 `&lt;`。摘要仍使用 Vue 插值，不使用 DOM/HTML 执行路径。原卡片按钮继续传出原课程对象，完整介绍未被摘要转换或截断。

最终检查均退出 0：

- 新增 6 项自造文本回归，覆盖实体、单次解码、非法值、标签处理、实际 Vue 模板文本节点/原按钮事件，以及 Less + 项目 Autoprefixer 处理。
- 完整 `npm test`：285/285，无失败或跳过。
- 完整 `npm run build`：成功。最终 `app.984cef6e.css` 保留 scoped `box-orient:vertical`、`line-clamp:3` 和 `max-height:5.7em`。
- 两个产品文件执行 `eslint --no-ignore` 通过；`git diff --check` 通过。首次 lint 发现实体表属性换行格式问题，已仅修排版并重新执行上述完整检查。

构建保留既有 12 项 CSS 顺序/资源及入口体积警告，以及 caniuse-lite 过期提示；未改依赖。完整日志留在本工作树私有 `.devspace/course-summary-{tests,build,lint}-full.txt`，权限 600，不加入 Git。

没有使用生产课程内容编写代码或测试，没有读取原始 dump/附件，没有提交或推送。停止额外合成预览准备；本 Agent 不声明浏览器三行显示或完整介绍验收。三种尺寸的真实副本复验由 root 在合并候选执行。
