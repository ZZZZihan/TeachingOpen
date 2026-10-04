# 冻结候选包的独立文件系统测试

测试对象是 `deploy/candidate_release.py` 的离线 create / verify。测试者只修改测试文件及本说明，不修改工具实现，不运行 Docker、数据库、HTTP、浏览器或现有生产数据。

测试输入是临时真实 Git 仓库。`CANDIDATE_TEST_SOURCE` 指向已冻结的集成 source，用其纯 helper、Nginx、模板、PasswordUtil 和自制素材构造测试仓库；原 SQL 先经 quote-aware extractor 提取 69 表结构，再加入一个明确合成的 INSERT 哨兵。测试仓库只使用局部 Git identity 设置。dist 是三个合成普通文件，JAR 是两个条目的合成 ZIP，不是可执行 TeachingOpen 应用。

正常创建路径使用 `CANDIDATE_TEST_JAVA_HOME` 指定的真实 Java 8 JDK 编译 FixturePassword / PasswordUtil 并生成五个账号的哈希。测试不以成功字符串或密码 stub 替代创建行为。这个步骤验证密码生成工具接入；它没有执行合成 JAR，也不证明真实 TeachingOpen JAR 在 Java 或 Linux 中运行。

运行方式：

```sh
PYTHONDONTWRITEBYTECODE=1 \
CANDIDATE_TEST_SOURCE=/absolute/path/to/integrated-source \
CANDIDATE_TEST_JAVA_HOME=/absolute/path/to/jdk8 \
python3 -m unittest discover -s deploy -p test_candidate_release.py -v
```

本次实际运行的 source 为 `.devspace/worktrees/product-candidate`，HEAD `8ad3f13db83fe7b48063c99c0f5d33ad42358c67`；JDK 为已有私有工具目录 `backend-runtime/tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home`。这两个环境变量是显式输入，测试不会替换成另一个 source、下载 Java、安装依赖或改全局 Git 配置。

最终结果：**66 个测试通过，0 失败、0 错误、0 跳过**，unittest 运行 7.670 秒。工具及测试文件在运行前后哈希相同：

- `deploy/candidate_release.py`：`ee6eae518411b09290c68a81ab76c40a43f55c83c7e3e80ce5bff2417beb1f67`。
- `deploy/test_candidate_release.py`：`a63b350d09ab699de2f01785d68f186eaa7df7aad4627283dfdc59cd133d7fb7`。

完整日志与结构化回执保存在本机 `.devspace/artifacts/release-candidate-20261005/tests/final.log` 和 `final.json`，前序 `round1` / `round2` / `round3`、`frozen64` 及 `frozen65` 日志与各轮源码哈希也保留。回执不含密码、初始化 SQL、用户数据或完整私有配置。

覆盖的具体行为：

- 正常 create / verify 使用真实文件复制和完整 SHA256 / bytes 库存；source 文件与 Git 状态保持原状。既有 untracked `.playwright-cli` / `output` 保留并排除，tracked dirty / staged dirty 与不在 commit 中的 helper 被拒绝。
- JAR / dist manifest 的显式期望哈希被检查；dist 缺失、新增、漂移、错误大小、重复 JSON key、未知 entry 字段、非规范或穿越路径、错误字段类型被拒绝。文件、目录、ancestor symlink 和 FIFO 均有真实文件系统测试；已有目录或文件不会被覆盖。
- 一项失败注入包裹真实 `write_file`：在它已经复制一个 dist 文件后改变源文件，实际后置检查拒绝该包，保留不完整目录且没有有效 manifest。没有 mock 成功返回值，也没有跳过 create / verify 的实际逻辑。
- schema 通过真实 quote-aware lexer确认 69 个 CREATE TABLE、零 INSERT；原 source SQL 的合成 INSERT 哨兵未进入 schema 或 fixture。生成的五账号 / 三角色 / 两班 / 三课程关系、独立随机盐、私有随机凭据格式和自制资源的完整字节库存一致。
- 配置恰好派生原模板 54 个键，没有重复、额外键或未解析 placeholder；每个值按容器派生规则比较，断言只报告出错的键名。权限按角色检查：顶层700、私有 config600、dist644 / 目录755、供官方容器读取的 init / 单个 secret 文件444。
- 私有 MySQL client 文件通过严格、不插值的 `ConfigParser` 分组检查：`[client]` 只提供 root 用户、私有密码、loopback host 与 TCP protocol，`[mysql]` 单独限定 `local-infile=0`。mysqladmin 健康命令保留私有 cnf；没有通过去掉凭据或放宽健康标准消除错误。
- Compose 被解析为结构化对象，只有 web 的 `127.0.0.1:18190` publish，API / DB / Redis 没有 publish。四服务均加入 `candidate` internal 网络；只有 web 同时加入明确 `driver=bridge, internal=false` 的 `ingress`。四服务固定 platform / digest、绑定范围、只读静态挂载和禁止 host / privileged / docker.sock / workspace 宽挂载均有检查。重新哈希库存后改成 broad publish、host bind 或 mutable image tag 仍被 verify 拒绝。
- 双网络契约的四项实际配置漂移测试：将 backend 网络改成 noninternal、将 ingress 改成 internal、让 API 加入 ingress、删除 web 的 ingress。各项均修改真实 compose 文件、重新计算文件库存，verify 仍拒绝。这证明生成与校验配置的固定约束，没有运行 Docker 或观察宿主端口映射。
- verify 拒绝冻结文件缺失、新增、漂移、链接、FIFO、权限变化、错误 kind / format、缺失 required 字段、重复或未知 JSON key、manifest path escape。即使重新哈希库存，必需 schema / fixture 被删除或新增外部 profile 仍拒绝。
- data 根必须是五个声明的普通直属目录；缺失、新增或 symlink 被拒绝。测试允许目录内部出现运行后的数据库页、上传和链接，确认 verify 不读取 mutable 数据或把运行状态当作静态包哈希失败。

失败与修复记录：

1. 首轮 60 个测试：59 通过、1 测试侧 ERROR。测试 parser 误将工具复用的 `CONVERT(X'hex' USING utf8mb4)` 文本编码当作单 token literal，修为只接受这个固定表达式并在本机解码；没有改变产品工具。
2. 第二轮 63 个测试：62 通过、1 真实 FAIL。`format: true` 被 Python `True == 1` 接受。作者修为精确整数类型及版本匹配；最后两轮覆盖 `true` 和 `1.0` 均被拒绝。
3. 第三轮 64 个测试：63 通过、1 测试侧 FAIL。新增配置测试误把模板邮箱里的 `@` 当作 placeholder，修为匹配 `@[A-Z_]+@`；没有改变产品工具。
4. 相同工具哈希下完整重跑 64 个测试，全部通过。该回执保留为 `frozen64`：工具哈希 `6e5d1388c1973ed8d296962c2d5313134107334ef5b1f54ac061beb736a7cdaf`，测试哈希 `bdcb06bb1cde308e39d8c60a10a5262a14fbc7d9a834197a2cd5a8c5e7d971b6`。
5. root 的实际 Docker 运行随后反馈 mysqladmin 健康检查错误：MySQL 已初始化，但共享 `[client]` 组中的 `local-infile=0` 令 mysqladmin 报未知选项。作者将该选项移到 `[mysql]`，保留通用身份项；测试者未自行启动或检查这些服务，只按反馈新增分组契约测试。
6. 修复后的新工具哈希下完整运行 65 个独立测试，全部通过。回执保存为 `frozen65`，工具哈希 `58616f5446901168fad20855f034feee20f8261a74d69226e88ba900080417f0`、测试哈希 `077891656280ddacba356de17f91efb21f782de49b9548db09305f141bcfb9a8`。这个新增文件格式回归测试并不替代 root 在 fresh bundle 上实际重跑 mysqladmin / MySQL 的结果。
7. root 随后反馈 bundle03 四服务正常、DB healthy，但 web 仅加入 internal 网络，实际 `NetworkSettings.Ports` 的 `80/tcp` 映射为空，宿主无法访问。作者据此增加只给 web 使用的非内部 bridge ingress，保留四服务内部网络和唯一 loopback publish；这项发现来自 root 的真实 Docker 运行，测试者没有自行观察或启动服务。
8. 双网络新冻结版本完整重跑 66 个独立测试，全部通过。配置及网络漂移测试与 root 对 fresh bundle 的实际端口映射、HTTP 和隔离行为核验分别记账；静态配置通过不声称宿主网络已经恢复可用。

静态源码审阅阶段反馈的重复 JSON 路径、required manifest / 静态文件闭包缺口，由作者在首轮实跑前修复并受这些测试覆盖；root 另外发现并推动修复重复 submission 写、helper tracked 约束与五个 mutable 边界目录。此处如实区分代码审阅反馈、测试失败和根协调证据。

本测试报告只证明这份离线工具在合成输入上的文件系统行为，以及真实 Java 8 fixture 密码 helper 的接入。小 dist 不是正式 4893 文件库存，小 JAR 未执行；Linux / Docker / 实际 TeachingOpen JAR / API / MySQL / Redis / 浏览器和人工验收属于 root 另行执行并绑定实际候选字节的证据。manifest SHA256 用于调用者冻结外部期望值；verify 不宣称阻止攻击者同时重写整个包和 manifest。
