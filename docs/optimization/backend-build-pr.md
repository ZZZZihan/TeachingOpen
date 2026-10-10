# 后端依赖解析修复

原父 POM 使用 `com.oracle:ojdbc6:11.2.0.3`。2026-10-02 对 Maven Central 的实际 HEAD 请求返回 404；改为 Oracle 发布的 `com.oracle.database.jdbc:ojdbc6:11.2.0.4` 后，对应 POM 返回 200，独立工作区的三个 Maven Reactor 项完成干净编译和打包。

本变更仅替换可选 Oracle JDBC 运行依赖的坐标及补丁版本，保留 Java 8、Spring Boot 2.1.3 和其他业务代码。未删除 Oracle 能力，也未连接 Oracle 数据库；实际 Oracle 数据库兼容性不在本次验证范围。

## 验证

- 独立分支基于 `2e0c1831a234c138c4c6873b56f5060e3a80aec8`，未带入其他后端修复。
- 使用现有项目内 Java 8 和 Maven 3.9.16，以及项目私有 Maven 设置与依赖缓存，在 `api/` 执行 `mvn -B -s "$TEACHING_MAVEN_SETTINGS" clean package`，实际退出码 0。
- 三个模块均 `SUCCESS`，构建完成时间为 2026-10-02 22:10:47 +08:00。父 POM 跳过 Java 测试，不能把构建成功写成测试套件通过。
- 实测来源、文件和产物摘要见 [构建证据](evidence/oracle-build.json)。此次沿用已有依赖缓存，未声称验证全新空缓存的所有上游下载可用性。

本 PR 不包含第三方登录禁用时的启动修复、隔离环境工具或授权修复，也不宣称应用已经可启动或可上线。回退该提交会恢复旧依赖解析问题，不需要数据库回退。
