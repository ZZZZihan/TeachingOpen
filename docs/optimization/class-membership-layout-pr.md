# 班级成员布局与选人弹层

2026-10-05。独立分支 `fix/class-membership-layout`，基于 PR61 `fix/class-member-context`（`df4e707234c04d1c8932335e4f779e58be25835e`）。产品提交 `5192b9d`。根负责浏览器、全量测试和本地整合；用户指定的 GPT-6.1-sol / ultra 子 Agent 分别实施与独立审阅。未宣称不可配置的 Fast 参数已生效。

## 问题与结果

旧成员页在390px下 document宽411、body宽412，表格把页面撑宽；放在真实 DepartList 的卡片/页签中，document虽为390，右侧操作被父容器裁切。旧选人弹窗在768px仍宽1000，关闭按钮和分页越界。

两份组件移除负边距和固定栅格错排，查询与操作按容器宽换行，区分主操作和清空班级，使用现有天工紫与中性色。全部字段保留，920px可读表格在局部横滚；区域可聚焦，左右键只在区域自身聚焦时作用。编辑/更多改为可聚焦按钮，点击菜单支持窄屏操作。弹窗保留1000px上限并留32px视口余量，短屏内容纵滚，页脚留在可见范围；分页可换行。

独立 AST 比对：两份业务 script 除列宽与 PR61 完全相同。班级上下文、请求、选中、保存、导入、共享选择器对象/数组事件保持。没有更改父 DepartList、后端或 PR62 权限修复。

## 验证与证据

- 作者：SFC模板编译、脚本解析、methods字节比对及diff检查通过。
- 独立审阅：业务 AST、模板事件/disabled/ref契约核对；既有专项64/64。首次57/64的7项失败来自测试辅助函数只识别`@click`，本次改为`@click.prevent`后未被识别。只扩展一行正则接受修饰符，断言保留；同判据旧版仍13/64。原始失败保存在本机artifact。
- 根：分支完整前端561/561；本地组合581/581，均无跳过。组合构建退出0，保留12条既有CSS顺序/体积告警。
- 根浏览器：实际Vue/Antd组件，实际DepartList父SFC、common.less及相同主题；API内存化，外围部门编辑/上传/课程面板替代。独立与父页面在390/768/1440的document和body均与视口相同；表格在自身区域横滚，查询与分页无外溢。390父容器278px，横滚后编辑与更多分别处于197.5–241.5与245.5–309.5px，可操作。
- 768弹窗边界16–752px；390×650短屏关闭/确认底边610px。左右键使表头/表体同步滚到120px；父表能滚到最右端。正常选人添加、查询、失败禁用与刷新重试、多页长文本测试均通过。最终预览URL的console error/warn为空。
- 预览首轮树fixture遗漏value导致三条Antd undefined重复警告，最终fixture补齐value=key，未修改产品。最终旧/新使用同一harness；旧图与数据均保留。

可解析结果、日志与截图在 [evidence/class-membership-layout](evidence/class-membership-layout)。作者与独立审阅归属见 [author](class-membership-layout-author.md)、[review](class-membership-layout-review.md)。不把内存API预览、方法测试或服务健康等同于完整认证三角色流程、人工验收或生产交付。

## 本地组合与回退

组合测试提交`02f96115e8150d1876381b37546111f49cce51b3`。4893个构建文件共211629143字节，manifest SHA256 `0b38b4690bac046186f3f4127eb8dc666aada7e2a413216a1a1a917f4bf2d120`。三个本机代理18112/18142/18150的初始与变化资源各16项，共48/48实际GET与产物逐字节相同。18111/18141/18149三个API均200 UP；后端JAR保持PR62 `f03ac420301977cea26e14d9de0bab03f0d8a5c0e7ec92854363ad07347060c0`。

切换前校验发现组合vue.config已有关闭prefetch的改动，第一次严格全文件比对在任何切换前停止；审阅差异后确认只是既有prefetch配置，主题配置及所有7份实际布局输入保持相同。该差异保存于证据，未把branch全配置说成与组合完全一致。

旧dist4893文件/211568970字节与PR61清单一致，已完整保留本机`.devspace/artifacts/class-membership-layout/previous-dist`，新旧目录交换前后均核对全部字节。生产服务和数据库未改动。原始源码工作区及候选已有`.playwright-cli/`、`output/`保持。

## 复现与剩余范围

在web下运行`node --test tests/class-member-context.test.cjs`及`npm test`。预览：`NODE_OPTIONS=--openssl-legacy-provider node tests/class-membership-layout-preview/build.cjs OUTPUT`，将OUTPUT用loopback静态服务器提供。可设置`PREVIEW_SOURCE_ROOT`指向旧版web建立对照。预览开关提供真实父页面、长文本/分页、慢响应和失败；它不连接生产或真实API。完整构建`npm run build -- --dest OUTPUT`。

认证浏览器三角色验收仍待原有验证码步骤确认，未绕过。未做全站无障碍审计、触屏硬件验证或生产发布。父部门树、机构表单和其余弹窗布局不在本PR范围内。Z820数据的隔离副本继续用于只读真实内容检查；本次布局故障/写入操作使用可重置内存fixture。

根的临时18183预览已停止，PID退出且端口关闭；浏览器临时页已关闭并恢复视口。全部源码、预览产物和证据保留。
