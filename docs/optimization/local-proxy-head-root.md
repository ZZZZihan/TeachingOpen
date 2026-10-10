# 本地代理 HEAD 的主 Agent 复核与组合验证

产品仅改本地工具，不改 Java、schema、前端 UI 或依赖。主 Agent 审查最终 diff，确认 GET/HEAD 共用静态回退，API HEAD 保留上游表示长度、完全不写正文；原WebSocket握手只接受GET，HEAD不能被该入口升级。CSP和普通HTTP原有行为保留。这是主Agent复核，与作者自检分开记录，没有额外第三方人工验收。

冻结代理 SHA256 `d765e08c8bcbb09b315e21e82d432d8f1938e037a93edee30d9fb7b23db33af2`，运行环境为专用`.devspace/unicode-media-1003`的18170代理，后端为#56精确JAR `95d9ad3ad4ada70897974071fec283a0c29bb703e2cdcb41397e80f77ebbd7c7`。此Java版本是组合验证环境，不是本工具PR的代码依赖；代码base是#49。

- 同一冻结中文媒体186项：旧代理下182/186，新代理183/186。代理HEAD从404变200，空正文且Content-Length=73、MIME/中文文件名/no-store/nosniff正确；同源GET、Range和cookie授权也通过。剩余3项仍是旧脚本误预设重复斜杠一律拒绝，保留退出1与原失败，不改断言冒称全部通过。
- 整理版补查CLI已真实运行：18/18重复斜杠的规范化权限与字节身份检查通过，全部业务行/表结构和附件清单恢复；ASCII媒体HEAD直连及代理均200/长度73/空正文。合法`%2B`引用匹配缺陷依旧保留，未混入本代理修复。
- 实际通知WebSocket经新代理44/44、Scratch云变量经新代理52/52，包含真实Java/Redis/MySQL与本地合成CLI身份。不是认证浏览器或真实用户试用。
- root第一次调用专项漏传必需`--label`，argparse退出2，未执行runtime操作；补参数后用新文件保存正式结果。没有覆盖第一次错误日志。

逐项数据与摘要见[root聚合](evidence/local-proxy-head/root/root-summary.json)。作者代理20/20与开发工具105通过/1跳过、旧版对照及首次故障探针超时都在[作者记录](local-proxy-head.md)。候选组合工具、三个持久本地代理切换和真实生产副本读取由总计划记录，不将本文件的合成结果当作生产验收。

本工具原GET仍把完整上游正文缓冲在内存，未作大媒体流式代理/容量优化。GitHub合并和生产部署不在本次操作中。
