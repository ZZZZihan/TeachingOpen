# 关闭第三方登录时正常启动

`justauth.enabled=false` 会让 JustAuth starter 不创建 `AuthRequestFactory`，原 `ThirdLoginController` 仍强制注入该 Bean，导致整个应用启动失败。控制器现在使用与已解析 JustAuth 1.3.2 工厂 Bean 一致的条件：明确为 `true` 或配置缺失时加载，设为 `false` 时不加载。

该 PR 基于 [构建修复 PR #2](https://github.com/ZZZZihan/TeachingOpen/pull/2)。GitHub base 是 `fix/backend-oracle-build`，因此本 PR 的业务代码差异仅为控制器加载条件；PR #2 合并后再将本 PR base 调整为 main。

## 实际验证

- 在独立工作区使用项目 Java 8、Maven 3.9.16 执行 `clean package`，三个 Reactor 项均 SUCCESS，退出码 0。父 POM 跳过 Java 测试，未声称其测试套件通过。
- 新增 `api/dev/check-disabled-third-login.py` 对打包产物执行真实启动探针。它核对本地配置、实际 MySQL 数据目录/端口及五个合成账号，使用空闲回环端口 18093，保留私有日志，结束时仅停止自己启动的进程。
- **修复前**：使用 PR #2 的构建产物，`justauth.enabled=false`，进程退出码 1，日志确认 `thirdLoginController` 缺少 `AuthRequestFactory`；未达到健康状态。[前置证据](evidence/third-login-disabled-before.json)
- **修复后**：使用本 PR 的构建产物，同一隔离配置和合成库，健康接口为 `UP`，公开课程接口返回成功。[修复后证据](evidence/third-login-disabled-after.json)
- 两次探针进程均停止。原本地演示后端 18091 仍为 `UP`。未启动生产服务或写入生产数据库。
- 对已解析 starter 的字节码注解做了检查，确认 `prefix=justauth`、`enabled`、`havingValue=true`、`matchIfMissing=true` 与本次注解一致；启用和默认分支的真实第三方认证尚未验证。

## 复现

前提是已有本任务的私有合成运行目录，包含 `config/application-localtest.properties`、五账号清单、独立 MySQL/Redis 和项目工具。环境准备工具作为后续独立 PR 交付，此 PR 不含环境安装或凭据。设置本机对应的 `TEACHING_RUNTIME`、`TEACHING_JAVA`、`TEACHING_MAVEN_SETTINGS` 和 `TEACHING_MAVEN` 后，在仓库根目录执行：

```sh
cd api
JAVA_HOME="$TEACHING_JAVA" "$TEACHING_MAVEN" -B -s "$TEACHING_MAVEN_SETTINGS" clean package
cd ..
python3 api/dev/check-disabled-third-login.py \
  --runtime "$TEACHING_RUNTIME" --java-home "$TEACHING_JAVA" \
  --jar api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar \
  --expect up --output "$TEACHING_RUNTIME/disabled-login-check.json"
```

对照时将 `--jar` 指向 PR #2 构建产物，使用 `--expect missing-factory`。不要把探针指向生产配置；脚本只支持此处约定的本地合成环境，验证结果不会输出口令、令牌或完整日志。

本变更不涉及数据库结构、原登录页面或角色权限；关闭第三方功能时控制器不加载，启用分支保留原行为。回退本提交会重新导致禁用配置下的启动失败。完整角色业务、真实第三方登录和上线验收不属于本 PR 的通过声明。
