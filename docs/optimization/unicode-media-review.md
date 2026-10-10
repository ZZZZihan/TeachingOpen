# 中文媒体路径独立审查

冻结候选的独立静态窄审与无服务 filter 矩阵未见当前范围内阻断。实际候选为 unicode-media-paths 的 JAR 95d9ad3ad4ada70897974071fec283a0c29bb703e2cdcb41397e80f77ebbd7c7；只核 filter/注册接缝和精确打包内容，不将合成代理请求称为容器路由、数据库授权、真实文件字节或浏览器验收。本轮没有启动、访问或停止任何 runtime，也没有登录或更改数据库、缓存、产品或测试。

只读 diff 确认：ShiroConfig 仅导入新类并在原 filters map 注册同名 invalidRequest，globalFilters、媒体第一匹配链、其余 JWT/anon 链和下载代码不变。新 filter 外层保留原默认实例；非直接媒体读调用原 super。例外必须是 REQUEST、GET/HEAD、raw URI 包含 contextPath+固定媒体前缀边界、decoded servletPath+pathInfo 同时包含固定前缀；三字段 ISOControl 检查后执行私有内层原 Shiro 校验。内层构造时一次设置 nonASCII=false、backslash=true，不在请求期间修改共享状态，不注册为独立 Spring/容器 filter，不二次 decode、不规范化 Unicode。

源码 SHA256 已独立核对：ShiroConfig 为 d4dc28a81d4b08c0e9594c48f917e47cc558bedb395b3aca2ca7116af6749af7，新 filter 为 a30e660b8bb3f7eb2b9a53e1c300af543cedfb2ad5fd26735ed969364c617814。与基线 bca9e5c8… 包比较，顶层应用类355→358，仅 ShiroConfig.class 修改，无删除；新增 LocalMediaInvalidRequestFilter、其 UnicodePathChecks 内类、Java8 编译器生成的 $1 访问标记类，共三个 class，均 major52。208 个外部嵌入 JAR 逐字相同；内部 common 的111个解包文件（含107个 class）逐字相同。因此包含内部 common 的应用类总数462→465；不要把顶层355与总数462混用，也不要将 $1 当作另一个产品逻辑修改。

私有矩阵由 Zulu Java8 1.8.0_504 编译/执行，候选三个 class 与所用 Shiro/Servlet/SLF4J 依赖均从精确 JAR 读取并记录单项 hash。JDK动态代理只提供 servlet 三路径字段、context、method、dispatcher 及有限 include 属性，通过反射调用真实候选和原1.13 filter 的 isAccessAllowed。没有 Spring context、HTTP服务器、磁盘媒体或身份环境。70/70 明确预设的双版本判据通过，退出0；另确认外层六个默认 guard 仍 true，以及继承拒绝入口仍 sendError400/returnfalse。无 per-request flag 切换；默认 blockBackslash 按原系统属性处理，新增媒体例外的内层明确禁止反斜线。

覆盖规范已编码中文目录/文件 GET、HEAD、空 context 和 servletPath/pathInfo 拆分，中文与空格/加号/百分号组合、全角斜线和组合字符的字面键；Unicode 非媒体、相似媒体前缀、raw/decoded 路由不一致、encoded 结构前缀、context 前缀混淆、非 GET/HEAD 和其它四个 dispatcher；三字段控制字符、分号/反斜线、dot segment、encoded dot/slash 的大小写及双编码。ASCII正常和危险路径分别与原 filter 对照，不把下游认证/授权判据塞进路径 filter。

需要精确保留三个 upstream 边界。重复分隔的 Unicode 媒体请求在本 filter 可通过，因为原结构检查也未拒绝重复分隔；实际容器/Shiro 可能规范化为同一键，必须仍经真实资源授权，不能声称本 filter 会拒绝所有重复斜线。INCLUDE 属性含中文、普通 getter 为 ASCII 的合成 case 两个 filter 都允许，因为原守卫只检查普通 getter；候选没有新增该放宽，不能把 REQUEST 例外表述成所有 include 中文必定拒绝。ASCII POST 的 filter 判定也与原版相同、允许继续，实际方法限制属于 MediaJwtFilter 的405及控制器。以上对照结果留在 JSON，不修改断言或产品让它们成为另一种行为。

证据文件为 [矩阵结果](evidence/unicode-media/filter-review/filter-matrix-final.json)，SHA256 b764c0e17338a187327e63e2b29b617d3edf3950bf3d24d11ec260f256034d5c。矩阵源 [矩阵源码](evidence/unicode-media/filter-review/UnicodeFilterMatrix.java) 的 SHA256 为 a76b5b994c8ba739437418cb62fca2bf907b611e778eae1bb1a632a4453b399c；离线启动脚本 私有启动脚本 `run-filter-matrix.py` 的 SHA256 为 c37f8b89299624d9b339b90b8a31c01c6f64180d2a9ef413a3fd9fceefbf234c。命令在仓库根执行 python3 .devspace/artifacts/unicode-media-root/run-filter-matrix.py；该脚本只向自身目录写入，核对固定候选 SHA，拒绝覆盖既有结果或提取目录。所用 javac/java 参数与嵌入输入列表可从启动脚本及结果复核。SLF4J在这份仅加载API的私有 classpath 使用 NOP logger 的提示保留于 filter-matrix-diagnostics.log，不冒充产品日志配置失败。

后续真实容器 baseline/candidate 对照、已授权中文文件字节及私有/跨用户/匿名/撤回/冻结/HEAD/Range 权限专项由 root 与测试 Agent 执行，本报告不抢占其环境；当前尚未汇入这些实际结果。初始官方依据、媒体路径边界与编码默认见 私有 `review-initial.md`。本结论仅针对冻结95d9ad3a…的静态接缝及上述合成 filter 行为，不能推广为全面路径安全、生产兼容或用户验收。

## 独立复现离线矩阵

从仓库根设置 `candidate_jar` 为上述精确候选 JAR，`matrix_java_home` 为 Java 8 JDK。以下只运行 servlet 动态代理矩阵，不访问 HTTP、数据库或生产。旧私有启动器哈希作为原始运行记录保留；下列等价手动命令未计作另一次通过。

```sh
probe_dir=$(mktemp -d)
unzip -q "$candidate_jar" 'BOOT-INF/classes/org/jeecg/modules/shiro/authc/aop/LocalMediaInvalidRequestFilter*.class' 'BOOT-INF/lib/shiro-*.jar' 'BOOT-INF/lib/tomcat-embed-core-*.jar' 'BOOT-INF/lib/slf4j-api-*.jar' -d "$probe_dir"
"$matrix_java_home/bin/javac" -encoding UTF-8 -source 8 -target 8 -cp "$probe_dir/BOOT-INF/classes:$probe_dir/BOOT-INF/lib/*" -d "$probe_dir" docs/optimization/evidence/unicode-media/filter-review/UnicodeFilterMatrix.java
"$matrix_java_home/bin/java" -cp "$probe_dir:$probe_dir/BOOT-INF/classes:$probe_dir/BOOT-INF/lib/*" UnicodeFilterMatrix
```

这份报告来自独立子 Agent 的代码审查与离线矩阵，不等于人工验收。最终真实 HTTP、附加观测、浏览器及组合状态见 [交付记录](unicode-media-pr.md)。
