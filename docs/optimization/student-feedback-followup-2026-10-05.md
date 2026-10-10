# 2026-10-05 学生作品反馈与最终组合回归

[PR #71](https://github.com/ZZZZihan/TeachingOpen/pull/71) 已推送、OPEN/非Draft并附加任务，基于 #70。表格与实际个人中心卡片共用只读反馈组件，明确零分/未评分，提供可键盘操作的全文弹窗与窄屏局部滚动，保持天工主题。产品提交 f8071b1b，最终分支 f0980ce2。实现及前后截图见[完整说明](https://github.com/ZZZZihan/TeachingOpen/blob/f0980ce2d8c8a06e635bf09aca3a8b7d16edbcb7/docs/optimization/student-feedback-readable-pr.md)。

按用户指定使用GPT-6.1-sol/ultra作者与独立审阅Agent并行；工具没有单独Fast参数。作者专项13/13、分支597/597，独立真实Vue/SFC20/20，根组合617/617。新文件显式lint零错误/警告；两旧父组件77错误/227警告仍存在（原82/227），不声明整页lint通过。正式构建成功并保留12条既有告警。根CUA实际组件与只读合成HTTP的390/768/1440、键盘开关、零分/仅评语、纯文本、长内容滚至末尾及两真实入口接线通过；保留真实Index卡片映射。认证外壳与教师写入后的整链仍未验收。

最终本地候选49d8c32aaa74b2dcb300f7aaa4b2653d7dd9929e，相对实际测试构建69002a1450306e73f13c7d0763d026dad7b8c335只增加交付文档/截图，api/web无差异。JAR沿用67568eea，本次后端没有修改或重启。新dist4894份、211848370bytes，完整manifest SHA83656f53e6674ab211b1754087cd5110cebd93fca7560bff9643d8f175be27ca；最后再次重算全部文件相同。

这份最新组合在全新私有合成Linux/arm64容器包中实际45/45通过，覆盖镜像/网络/挂载、启动、五账号角色API、课程单元持久化与拒绝、媒体/附件、中文Python草稿、WebSocket和退出撤销。不是沿用#68旧产物结果；同一冻结工具和probe未改。API探针读取自有Redis挑战，不等同普通浏览器登录，未验证大小写敏感Linux或Z820目标运行。bundle manifest b4fd5be5。三个本机代理本地初始资源24/24字节匹配，外部errlog未检查。

新dist已切换，旧dist完整留存在私有student-feedback-20261005/previous-dist。真实课程副本18142仍可打开，三个既有后端健康UP、PID和JAR身份不变。临时18304/18305/18306/18307/18190均关闭，自有容器及网络移除，数据保留。没有远端合并、生产修改或部署。

失败记录如实保留：初次Less原生min函数提前求值、草稿关闭重开竞态、预览漏全局过滤器、首次bundle输出位于输入目录被拒绝、静态解析只处理带引号URL而漏资源。分别修复并复核；初次Less日志已被覆盖，仅保留事实说明，不冒充日志仍在。

[聚合证据](evidence/product-candidate/student-feedback-readable-candidate.json)绑定提交、产物及私有原始报告摘要。Goal active；普通认证三角色、三编辑器完整链路、用户审美认可和目标部署继续待完成。

记录修正：首次保存本轮聚合证据时遇到与早期#25记录同名的路径；随后追加提交恢复旧文件原始字节，本轮改用student-feedback-readable-candidate.json，保留早期证据及其原链接，不改写已推送历史。
