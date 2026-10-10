# 冻结候选的容器验证后续记录

2026-10-05。继续产品化目标；用户明确允许生产来源数据用于测试，已有私有副本继续用于真实课程与媒体检查。本轮解决候选产物与运行环境难以复现的问题，未重新访问 Z820，也未把合成容器测试说成生产数据或生产环境验证。

[PR #68](https://github.com/ZZZZihan/TeachingOpen/pull/68) 基于 #66，最终分支 `1e93ef2c932dccfae19916ae046e421aa2aae83c`，OPEN/非Draft、已附加当前任务，查询时无已报告 GitHub CI。按用户要求，GPT-6.1-sol / ultra 子 Agent 分别完成离线打包工具、独立测试、运行探针、官方镜像核对和独立审阅；根 Agent 审查并真实执行。接口没有独立 Fast 参数。

工具以明确可信、tracked-clean 的集成 source 为输入，复制冻结JAR、4893个完整dist文件及#66 Nginx；抽取69表空schema并生成五账号、两班、三课程的自制夹具，每包新随机私有凭据。Compose固定官方Linux/arm64镜像与限定挂载，后端内部网络，只有Nginx额外接入口bridge并发布loopback端口。create/verify自身离线；真实启动、API和数据检查由另一探针完成。没有重建产品，也不提供源码到产物的构建签名。

独立离线工具66/66；报告父目录8/8独立回归。根最终fresh05真实45/45：精确网络/实际端口/镜像/挂载、健康与静态原字节，五账号三角色API登录和菜单，同班允许/跨班拒绝，管理员课程和单元POST/PUT/DELETE及API+数据库重读、学生写入拒绝后字段不变，公私媒体GET/HEAD/Range与摘要，中文路径multipart上传、个人Python草稿持久化/重读及越权拒绝，媒体Cookie限制、WebSocket、退出后旧token与cookie撤销。运行前后generator/probe哈希相同；独立审阅重新计数45个不同case并核对原报告/收据摘要，没有再次执行容器。

初次尝试与修复完整保留：离线format布尔接受、mysqladmin共享配置分组、只有internal网络导致请求的端口映射未实际生效、探针chmod已有父目录。最终修复保持强验证，没有放松检查来获得成功。失败bundle与数据/日志私有保留。初期测试parser与placeholder判断错误另记为测试侧修正。

测量source为8ad3f13d，最终本地集成 `0cc8e06d9b9049ef803abe91ca65f735931e2fcd`；后者只增加deploy工具和证据文档，api/web输入无diff，工具与PR最终字节相同。集成工具再次verify最终包通过，没有重复冒称另一次容器运行。冻结JAR仍9eb18d42，dist仍4893文件/211629143字节，全部哈希与既有清单相同。已知untracked .playwright-cli/和output/保留。

五个尝试项目均无剩余容器或网络，18190关闭，私有data保留。原18111/18141/18149健康UP，18142真实副本入口HTTP200。没有重启或切换旧服务，也没有远端合并、上线或生产修改。

本次Mac上的Linux/arm64 MySQL8.4.6使用宿主bind，lower_case_table_names实际2；不证明大小写敏感Linux下0值行为或Z820架构/文件系统。合成API登录读取自有Redis对应挑战值，不是普通浏览器登录；个人Python草稿的API写入不是完整编辑器保存/执行/最终交作业；媒体字节检查不是浏览器全程播放。TLS、正式三角色编辑器全链、用户视觉评阅及目标环境仍待完成，Goal继续active。

完整源文件、独立记录与运行证据已随[PR交付说明](https://github.com/ZZZZihan/TeachingOpen/blob/1e93ef2c932dccfae19916ae046e421aa2aae83c/docs/optimization/candidate-release-pr.md)提交；本规划分支保存[组合记录](evidence/product-candidate/candidate-release.json)，不包含私有凭据、生产配置或原始业务资料。
