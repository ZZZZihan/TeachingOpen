# Scratch 云变量访问与数据保护

前置为 PR #35 `c41b8ba615bee4d17dec290035fc25da9cb77540`。最终产品代码 `c2a4cb7f11752e77a09f1bd4f18f11d679d82864`。本项修改服务端云变量处理、显式作品读取授权和合成验证脚本，不改变页面、数据库 schema、依赖版本或生产配置。

## 问题与结果

旧版真实复现匿名、其他学生、跨班教师读取私有作品云变量；没有握手即可匿名写入，任意项目 ID 能产生孤立 Redis 数据。退出登录和切换项目后仍留有旧订阅，删除作品仍能读取；原始消息中的完整令牌和变量值进入普通日志。作者新建变量还会因 Spring Bean 名称错误而失败。旧行为及清理检查 14/14 符合复现预期。

连接现在必须先握手，绑定一个实际存在、未删除的 Scratch 作品及经验证的身份。每次操作、广播接收及队列出队前重新核对当前令牌和作品读取范围：公开作品可匿名读取；私人作品仅作者、管理员/dev 或当前具有班级管理范围的教师可读。客户端显示名不决定身份，失效令牌不能退回匿名权限，切换身份或作品需要新连接。退出、撤回和班级变更在后续收发时拒绝；这不是主动推送注销事件，已发送字节不能收回。

保留共享云变量用途：**已登录且有读取权限的参与者可以更新已有变量值，只有作者可以新增、删除和重命名。** 匿名公开读者不能写入。Redis Lua 将存在性、数量检查与修改合并为一次原子操作，重命名不覆盖目标，重复创建不重置已有值。保留原 `scratch:cloud:<作品 ID>` 键和 JSON 值格式，没有迁移或清理历史云数据。

单作品最多 64 个变量，名称最多 128 个 Java 字符、值最多 1,024 个 Java 字符，入站文本最多 16 KiB。`create` 和 URL 不再作为项目 ID。握手前空闲 10 秒，握手后 90 秒；异步发送设 5 秒超时，以最多 128 条 / 524,288 个 Java 字符的有界队列串行发送。只返回通用关闭原因，不打印原始消息、令牌或变量。已有超限或非法数据会拒绝读取，不静默截断或删除。

## 实测证据

最终 JAR：`ba9a03697641afdb8ee1781ab20848e1865fdfa4ee4c1c1ac317156f7efcb72f`。隔离合成 `recovery-a` 经真实 Java / MySQL / Redis 和同源 WebSocket 测试：

- 云变量专项 **52/52**：公开/私人/删除/不存在/错误类型作品；匿名、作者、异用户、教师和管理员；预握手写入、身份与项目切换、退出、撤回及班级变更；两标签共享与单连接关闭；重复创建、重命名冲突、两连接竞争重命名、64 项快照与第 65 项拒绝；非法输入、Redis 错类型与数据库查询故障后的无写入及恢复；敏感消息不进入日志；原数据、附件和云键恢复。
- 相同最终 JAR 的相关回归 **469/469**：社区 235、作品管理 134、恢复后业务 29、通知 44、实际通知 JS helper 5、容器上传及协议 9、前端 HTTP/Cookie/媒体 Range/静态资源 13。合计新行为及回归 **521/521**，不是 521 个不同用户流程。
- 既有本地工具 Python 检查 **42/42**。三模块 Java 8 / Maven 干净构建成功；父 POM 跳过 Java 单元测试，不能称 Java 单元测试通过。没有重新构建前端或重复历史前端检查。
- JAR 内容对照只有三个应用 class 变化/新增。内嵌 common JAR 外部字节因重打包变化，解压后的全部内容摘要一致。没有引入其他依赖变更。
- 前端复用本地组合 `8881cbe` 的 4,884 项既有产物，实际构建代码为 `7a0fe01`。冻结最终包的 manifest 摘要为 `9a4b79ad972f17c61d082209c7bcd4e866a54e3be054021f9659da204ac242f6`；打包动作本身不作为编译证明。

中间验证没有隐藏：首版并行异步发送快照和 ack 会关闭连接，改成有界串行队列后修复；第二版仅非法 JSON 关闭码与契约不符，最终明确返回 1008 并重跑专项及全部列明回归。两个失败包和日志留在私有 `.devspace` 用于复现，不是可接受候选或推荐回退包。旧包 `candidate-websocket-proxy` 保留供必要的本地回退；它含已复现的旧云变量问题，不能作为安全版本发布。

数据保护、停机状态与准确候选见 [候选记录](evidence/scratch-cloud-access/candidate.json)，逐项结果见 [证据清单](evidence/scratch-cloud-access/manifest.json)。这都是当前 Agent 工程自检，没有其他 Agent 审查或人工验收。

## 重跑

在独立合成环境启动本 PR 最终 JAR 和支持 WebSocket 的前端代理，从仓库根执行；脚本会核对运行环境和实际 JAR，不允许对已有同名探针数据直接覆盖。

```sh
python3 api/dev/verify-scratch-cloud.py --runtime "$runtime" --jar "$jar" --output "$output/cloud.json"
python3 api/dev/verify-community-work.py --runtime "$runtime" --jar "$jar" --output "$output/community.json"
python3 api/dev/verify-work-management.py --runtime "$runtime" --jar "$jar" --java-home "$java_home" --output "$output/work.json"
python3 api/dev/verify-recovered-business.py --runtime "$runtime" --jar "$jar" --snapshot "$snapshot" --output "$output/recovered.json"
python3 api/dev/verify-notification-websocket.py --runtime "$runtime" --jar "$jar" --via-frontend --output "$output/notifications.json"
python3 api/dev/verify-notification-client.py --runtime "$runtime" --jar "$jar" --via-frontend --output "$output/client.json"
python3 api/dev/verify-container-http.py --runtime "$runtime" --jar "$jar" --via-frontend --output "$output/container.json"
python3 api/dev/verify-frontend-http.py --runtime "$runtime" --jar "$jar" --dist "$dist" --output "$output/http.json"
```

## 尚未验收的边界

本项原生协议验证不代表随产品发布的 Scratch 编辑器/播放器通过。当前页面使用 hostname 丢失端口，未保存项目使用共用 `create`，播放器没有完整会话身份接入，旧 provider 切换项目与重连的生命周期也需独立修复。下一 PR 处理真实客户端、未保存/案例项目、端口、退出和重连，不用原生探针替代它。

连接订阅仍在单 JVM 内，没有多实例广播、弱网长期运行或连接容量结论。有界队列只是明确资源上限，没有宣称慢消费者压力测试已完成。MySQL 权限检查与 Redis 修改不是跨存储事务；并发撤回与已经开始执行的修改之间仍有竞争窗口，已传出的数据不能撤回。重命名/删除保留原协议的确认行为，不向其他正在运行的项目热修改变量定义；重新握手读取当前快照。

历史非法/超限键、Redis 持久化策略及灾难恢复需单独盘点，当前数据库/附件备份工具并不包含云变量 Redis 数据。其他公告 REST 授权、完整角色浏览器、用户视觉评阅、其他编辑器及依赖维护仍待后续。远端合并和生产上线未执行。
